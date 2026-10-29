# /// script
# requires-python = ">=3.12"
#
# [tool.orcaslicer.plugin]
# name = "ACE Spool Mapper"
# description = "Pick which ACE Pro spool prints each OrcaSlicer filament. A panel shows your printer's live ACE spools; when you send or export, the choice is written into the G-code as ACE_SET_TOOL_MAP (acepro-any-klipper driver)."
# author = "ducati1198"
# version = "0.1.3"
# ///
"""ACE Spool Mapper for OrcaSlicer 2.5 + acepro-any-klipper.

Two capabilities in one plugin:

* "ACE Spools" (Script): run it from the Plugins dialog. It docks a panel beside the 3D view
  listing every project filament with a dropdown of the printer's live ACE spools (read from
  Moonraker at the printer preset's print host). "Auto" picks the best spool (same material,
  closest color, each spool used once where possible); you can pin any filament to a spool or
  to "as sliced".

* "ACE Spool Map" (Slicing Pipeline, G-code post-process step): enable it once in
  Process > Others > Slicing Pipeline Plugin. Every time the G-code is exported or uploaded
  it inserts, before the start G-code:

      ACE_SET_TOOL_MAP MAP=0:4,1:2 FILE="name.gcode" KEEP_EXISTING=1

  The driver then sends sliced T0 to ACE slot T4, T1 to T2, ... for that print only.
  This step never opens UI (Orca forbids UI calls from slicing hooks); it uses the panel's
  choices, else auto-matches against the spools it can read from the printer.
"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import orca

SLOTS_PER_ACE = 4
DEFAULT_TIMEOUT_S = 3.0
# Your printer (Moonraker). Change it in Plugins > ACE Spool Mapper > Config, or leave it empty to use
# the printer preset's print host.
DEFAULT_PRINTER_URL = ""  # empty = use the printer preset's print host

# Shared between the panel (UI thread) and the post-process step (slicing worker thread).
STATE = {
    "spools": [],          # last spools read from the printer
    "spools_base": "",     # Moonraker base URL they came from
    "spools_time": 0.0,
    "choices": {},         # str(filament index) -> "auto" | "sliced" | "<ace tool number>"
    "signature": [],       # [(colour, type)] per filament when choices were made
    "enabled": True,       # write the map into exported G-code
    "last_written": "",    # human readable summary of the last post-process
}


# --------------------------------------------------------------------------------------
# Pure helpers (no orca dependency, unit-testable)
# --------------------------------------------------------------------------------------

def parse_config_list(value):
    """Parse an Orca serialized vector option into a list of strings.

    Handles '#AA0000;#00FF00', '"AF LGX Sunlu PLA";"PETG Basic"', and escaped quotes."""
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    items, cur, in_q, esc, quoted = [], [], False, False, False
    for ch in text:
        if esc:
            cur.append(ch)
            esc = False
        elif ch == "\\" and in_q:
            esc = True
        elif ch == '"':
            in_q = not in_q
            quoted = True
        elif ch == ";" and not in_q:
            items.append("".join(cur).strip() if not quoted else "".join(cur))
            cur, quoted = [], False
        else:
            cur.append(ch)
    items.append("".join(cur).strip() if not quoted else "".join(cur))
    return items


def moonraker_base(print_host, override=""):
    host = (override or print_host or "").strip()
    if not host:
        return ""
    if "://" not in host:
        host = "http://" + host
    return host.rstrip("/")


def normalize_material(value):
    text = re.sub(r"[\s_]+", "", (value or "").upper())
    return re.sub(r"^PA(?=$|[-+])", "NYLON", text)


def hex_to_rgb(value):
    m = re.match(r"^#?([0-9a-fA-F]{6})", (value or "").strip())
    if not m:
        return None
    v = int(m.group(1), 16)
    return ((v >> 16) & 255, (v >> 8) & 255, v & 255)


def color_distance(a, b):
    ca, cb = hex_to_rgb(a), hex_to_rgb(b)
    if not ca or not cb:
        return 400.0
    r_mean = (ca[0] + cb[0]) / 2
    dr, dg, db = ca[0] - cb[0], ca[1] - cb[1], ca[2] - cb[2]
    return ((2 + r_mean / 256) * dr * dr + 4 * dg * dg + (2 + (255 - r_mean) / 256) * db * db) ** 0.5


def rgb_to_hex(rgb):
    try:
        r, g, b = (max(0, min(255, int(c))) for c in list(rgb)[:3])
        return "#%02X%02X%02X" % (r, g, b)
    except (TypeError, ValueError):
        return "#808080"


def project_filaments(colours, types, names):
    count = max(len(colours), len(types), len(names))

    def pick(lst, i):
        if i < len(lst):
            return lst[i]
        return lst[0] if len(lst) == 1 else ""

    return [
        {"index": i, "colour": pick(colours, i), "type": pick(types, i), "name": pick(names, i)}
        for i in range(count)
    ]


def spools_from_status(status, instance_count):
    spools = []
    for unit in range(instance_count):
        inst = status.get(f"ace_instance_{unit}") or {}
        slots = inst.get("slots") or []
        for local in range(SLOTS_PER_ACE):
            slot = next((s for s in slots if s.get("index") == local), {}) or {}
            tool = slot.get("tool", unit * SLOTS_PER_ACE + local)
            status_text = slot.get("status") or "unknown"
            material = slot.get("custom_name") or slot.get("material") or ""
            spools.append({
                "tool": int(tool),
                "unit": unit,
                "slot": local,
                "status": status_text,
                "ready": status_text != "empty",
                "material": material if status_text != "empty" else "",
                "colour": rgb_to_hex(slot.get("color") or [128, 128, 128]),
                "temp": slot.get("temp") or 0,
                "rfid": bool(slot.get("rfid")),
            })
    return spools


def fetch_spools(base, api_key="", timeout=DEFAULT_TIMEOUT_S):
    """Read the ACE spools from Moonraker. Raises on network/HTTP problems."""
    headers = {"Accept": "application/json"}
    if api_key:
        headers["X-Api-Key"] = api_key

    def query(objects):
        qs = "&".join(urllib.parse.quote(o, safe="") for o in objects)
        req = urllib.request.Request(f"{base}/printer/objects/query?{qs}", headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))["result"]["status"]

    manager = query(["ace"]).get("ace") or {}
    if "ace_instances" not in manager:
        raise RuntimeError("printer has no ACE driver object ('ace')")
    count = max(1, int(manager.get("ace_instances") or 1))
    status = query([f"ace_instance_{i}" for i in range(count)])
    return spools_from_status(status, count), manager


def auto_match(filaments, spools, only=None):
    """Best spool per filament: same material, closest colour, spools used once when possible."""
    ready = [s for s in spools if s.get("ready")]
    result, used = {}, set()
    for fil in filaments:
        if only is not None and fil["index"] not in only:
            continue
        if not ready:
            result[fil["index"]] = fil["index"]
            continue

        def score(spool):
            same = (not fil["type"]) or normalize_material(fil["type"]) == normalize_material(spool["material"])
            s = (0 if same else 1000) + (color_distance(fil["colour"], spool["colour"]) if fil["colour"] else 0)
            if spool["tool"] in used:
                s += 500
            if spool["tool"] == fil["index"]:
                s -= 1
            return s

        best = min(ready, key=score)
        result[fil["index"]] = best["tool"]
        used.add(best["tool"])
    return result


def resolve_mapping(filaments, spools, choices, only=None):
    """Combine panel choices with auto-match. Returns {sliced tool: ace tool}."""
    pinned = {}
    for fil in filaments:
        if only is not None and fil["index"] not in only:
            continue
        choice = str(choices.get(str(fil["index"]), "auto"))
        if choice == "sliced":
            pinned[fil["index"]] = fil["index"]
        elif choice.isdigit():
            pinned[fil["index"]] = int(choice)
    auto_for = [f for f in filaments if f["index"] not in pinned and (only is None or f["index"] in only)]
    taken = set(pinned.values())
    remaining = [s for s in spools if s["tool"] not in taken] or spools
    mapping = dict(pinned)
    mapping.update(auto_match(auto_for, remaining))
    return mapping


def tools_in_gcode(lines):
    used = set()
    tool_re = re.compile(r"^\s*T(\d+)\s*(?:;.*)?$")
    start_re = re.compile(r"\bTOOL=(\d+)\b", re.IGNORECASE)
    for line in lines:
        m = tool_re.match(line)
        if m:
            used.add(int(m.group(1)))
            continue
        if "START_PRINT" in line.upper() and not line.lstrip().startswith(";"):
            m = start_re.search(line)
            if m:
                used.add(int(m.group(1)))
    return sorted(used)


def gcode_param(value):
    text = str(value)
    if re.fullmatch(r"[A-Za-z0-9._/\-]+", text):
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def map_lines(mapping, output_name, summary):
    pairs = ",".join(f"{a}:{b}" for a, b in sorted(mapping.items()) if a != b)
    cmd = f"ACE_SET_TOOL_MAP MAP={pairs}"
    if output_name:
        cmd += f" FILE={gcode_param(output_name)}"
    cmd += " KEEP_EXISTING=1"
    return [f"; ACE Spool Mapper: {summary}\n", cmd + "\n"]


def insert_before_first_command(lines, new_lines):
    """Insert after the leading comment/thumbnail header, before the first real command."""
    idx = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith(";"):
            idx = i
            break
    else:
        idx = len(lines)
    return lines[:idx] + new_lines + lines[idx:]


def describe(mapping, filaments, spools):
    by_tool = {s["tool"]: s for s in spools}
    parts = []
    for a, b in sorted(mapping.items()):
        sp = by_tool.get(b)
        label = f"T{b}" + (f" {sp['material']}" if sp and sp["material"] else "")
        parts.append(f"T{a}->{label}" if a != b else f"T{a} as sliced")
    return ", ".join(parts) if parts else "no filaments"


# --------------------------------------------------------------------------------------
# Orca glue
# --------------------------------------------------------------------------------------

def _bundle_value(key):
    try:
        return orca.host.preset_bundle().full_config_value(key)
    except Exception:
        return None


def _current_project():
    colours = parse_config_list(_bundle_value("filament_colour"))
    types = parse_config_list(_bundle_value("filament_type"))
    names = parse_config_list(_bundle_value("filament_settings_id"))
    return project_filaments(colours, types, names)


def _signature(filaments):
    return [[f["colour"], f["type"]] for f in filaments]


def _prune_choices(filaments):
    """Forget pinned choices for filaments whose colour/type changed since they were made."""
    old = STATE.get("signature") or []
    new = _signature(filaments)
    for key in list(STATE["choices"].keys()):
        i = int(key)
        if i >= len(new) or i >= len(old) or old[i] != new[i]:
            STATE["choices"].pop(key, None)
    STATE["signature"] = new


def _config(cap):
    try:
        cfg = json.loads(cap.get_config() or "{}")
    except (AttributeError, TypeError, ValueError):
        cfg = {}
    return cfg if isinstance(cfg, dict) else {}


PANEL_HTML = r"""
<style>
  body { margin: 0; padding: 10px; font-size: 13px; }
  h3 { margin: 0 0 2px; font-size: 14px; }
  .muted { color: var(--orca-muted); font-size: 12px; }
  .bar { display: flex; gap: 6px; align-items: center; margin: 8px 0; flex-wrap: wrap; }
  .row { display: grid; grid-template-columns: 18px 1fr; gap: 6px 8px; align-items: center;
         padding: 7px 0; border-top: 1px solid var(--orca-border); }
  .dot { width: 16px; height: 16px; border-radius: 50%; border: 1px solid var(--orca-border); }
  .name { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .dd { grid-column: 2; position: relative; }
  .dd-btn { width: 100%; display: flex; align-items: center; gap: 6px; text-align: left; padding: 4px 6px;
            background: var(--orca-bg); color: var(--orca-fg); border: 1px solid var(--orca-border); border-radius: 4px; }
  .dd-btn .lbl { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .dd-btn .caret { opacity: .6; font-size: 10px; }
  .dd-list { display: none; position: absolute; left: 0; right: 0; top: 100%; z-index: 10; margin-top: 2px;
             max-height: 260px; overflow-y: auto; background: var(--orca-bg); color: var(--orca-fg);
             border: 1px solid var(--orca-border); border-radius: 4px; box-shadow: 0 4px 14px rgba(0,0,0,.35); }
  .dd.open .dd-list { display: block; }
  .dd-opt { display: flex; align-items: center; gap: 6px; padding: 5px 6px; cursor: pointer; }
  .dd-opt:hover { background: var(--orca-accent); color: var(--orca-accent-fg); }
  .dd-opt.sel { font-weight: 600; }
  .dd-opt.off { opacity: .45; cursor: default; }
  .dd-opt.off:hover { background: none; color: inherit; }
  .sw { flex: none; width: 14px; height: 14px; border-radius: 3px; border: 1px solid var(--orca-border); }
  .sw.none { background: repeating-linear-gradient(45deg, transparent 0 3px, var(--orca-border) 3px 5px); }
  .hint { grid-column: 2; font-size: 12px; color: var(--orca-muted); }
  .warn { color: #e0a030; }
  .err { color: #e05050; margin-top: 6px; }
  label.chk { display: flex; gap: 6px; align-items: center; margin-top: 10px; }
</style>
<h3>ACE spools</h3>
<div class="muted" id="host">Printer: …</div>
<div class="bar">
  <button type="button" id="refresh">Refresh spools</button>
  <button type="button" id="reset" class="quiet">All auto</button>
</div>
<div id="rows"></div>
<label class="chk"><input type="checkbox" id="enabled"> Write this map into G-code when sending</label>
<div class="muted" style="margin-top:6px">Needs “ACE Spool Map” in Process › Others › Slicing Pipeline Plugin.</div>
<div class="muted" id="last"></div>
<div class="err" id="error"></div>
<script>
(function () {
  var state = null;
  function esc(v) { var s = document.createElement("span"); s.textContent = v == null ? "" : String(v); return s.innerHTML; }
  function spoolLabel(s) {
    var where = state.units > 1 ? " (ACE " + (s.unit + 1) + ")" : "";
    if (!s.ready) return "T" + s.tool + " · empty" + where;
    return "T" + s.tool + " · " + (s.material || "?") + (s.temp ? " · " + s.temp + "°C" : "") + where;
  }
  function swatch(c) {
    return c ? '<span class="sw" style="background:' + esc(c) + '"></span>' : '<span class="sw none"></span>';
  }
  function closeAll() {
    Array.prototype.forEach.call(document.querySelectorAll(".dd.open"), function (d) { d.classList.remove("open"); });
  }
  document.addEventListener("click", closeAll);
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeAll(); });
  function render() {
    if (!state) return;
    document.getElementById("host").textContent = "Printer: " + (state.host || "no print host set in the printer preset") +
      (state.refreshed ? " · read " + state.refreshed : "");
    document.getElementById("enabled").checked = !!state.enabled;
    document.getElementById("error").textContent = state.error || "";
    document.getElementById("last").textContent = state.last ? "Last G-code: " + state.last : "";
    var html = "";
    if (!state.filaments.length) html = '<div class="muted">No filaments in this project.</div>';
    state.filaments.forEach(function (f) {
      var choice = state.choices[String(f.index)] || "auto";
      var target = state.resolved[String(f.index)];
      var sp = state.spools.filter(function (s) { return s.tool === target; })[0];
      var asSliced = state.spools.filter(function (s) { return s.tool === f.index; })[0];
      var items = [{ value: "auto", colour: sp && sp.ready ? sp.colour : "", label: "Auto" + (sp ? " → " + spoolLabel(sp) : "") },
                   { value: "sliced", colour: asSliced && asSliced.ready ? asSliced.colour : "", label: "As sliced (T" + f.index + ")" }];
      state.spools.forEach(function (s) {
        items.push({ value: String(s.tool), colour: s.ready ? s.colour : "", label: spoolLabel(s), off: !s.ready });
      });
      var cur = items.filter(function (it) { return it.value === choice; })[0] || items[0];
      var list = items.map(function (it) {
        return '<div class="dd-opt' + (it.value === choice ? ' sel' : '') + (it.off ? ' off' : '') + '" data-value="' + esc(it.value) + '">' +
               swatch(it.colour) + '<span>' + esc(it.label) + '</span></div>';
      }).join("");
      var dd = '<div class="dd" data-index="' + f.index + '"><button type="button" class="dd-btn">' + swatch(cur.colour) +
               '<span class="lbl">' + esc(cur.label) + '</span><span class="caret">▼</span></button>' +
               '<div class="dd-list">' + list + '</div></div>';
      var warn = "";
      if (sp && f.type && sp.material && f.type.toUpperCase().replace(/\s/g, "") !== sp.material.toUpperCase().replace(/\s/g, ""))
        warn = '<div class="hint warn">Sliced for ' + esc(f.type) + ', spool is ' + esc(sp.material) + '</div>';
      html += '<div class="row"><div class="dot" style="background:' + esc(f.colour || "#888") + '"></div>' +
              '<div class="name">Filament ' + (f.index + 1) + ' · ' + esc(f.type || "?") +
              (f.name ? ' <span class="muted">' + esc(f.name) + '</span>' : '') + '</div>' +
              dd +
              (sp ? '<div class="hint"><span class="dot" style="display:inline-block;width:10px;height:10px;vertical-align:middle;background:' +
                    esc(sp.colour) + '"></span> prints from ' + esc(spoolLabel(sp)) + '</div>' : '') + warn + '</div>';
    });
    document.getElementById("rows").innerHTML = html;
    Array.prototype.forEach.call(document.querySelectorAll(".dd"), function (dd) {
      dd.querySelector(".dd-btn").addEventListener("click", function (e) {
        e.stopPropagation();
        var wasOpen = dd.classList.contains("open");
        closeAll();
        if (!wasOpen) dd.classList.add("open");
      });
      Array.prototype.forEach.call(dd.querySelectorAll(".dd-opt"), function (opt) {
        opt.addEventListener("click", function (e) {
          e.stopPropagation();
          if (opt.classList.contains("off")) return;
          closeAll();
          orca.postMessage({ command: "set", index: Number(dd.getAttribute("data-index")), choice: opt.getAttribute("data-value") });
        });
      });
    });
  }
  orca.onMessage(function (m) { if (m && m.command === "state") { state = m; render(); } });
  document.getElementById("refresh").addEventListener("click", function () { orca.postMessage({ command: "refresh" }); });
  document.getElementById("reset").addEventListener("click", function () { orca.postMessage({ command: "reset" }); });
  document.getElementById("enabled").addEventListener("change", function (e) {
    orca.postMessage({ command: "enable", value: e.target.checked });
  });
  orca.postMessage({ command: "refresh" });
})();
</script>
"""


class AceSpoolsPanel(orca.script.ScriptPluginCapabilityBase):
    panel = None
    error = ""

    def get_name(self):
        return "ACE Spools"

    def get_default_config(self):
        return {"printer_url": DEFAULT_PRINTER_URL, "timeout_s": DEFAULT_TIMEOUT_S, "open_on_start": True}

    # Orca's supported way to show a pane at startup: create it from on_load; the host waits until
    # the main window is on screen before docking it.
    def on_load(self):
        try:
            if _config(self).get("open_on_start", True):
                self._open()
        except Exception:  # noqa: BLE001 - never block the plugin from loading
            pass

    def execute(self):
        if self._open():
            return orca.ExecutionResult.success("ACE Spools panel opened.")
        return orca.ExecutionResult.success("ACE Spools panel is already open.")

    def _open(self):
        if self.panel is not None and self.panel.is_open():
            self.panel.show()
            return False
        self.panel = orca.host.ui.create_dock_panel(
            html=PANEL_HTML, title="ACE Spools", width=330, height=520,
            on_message=self.on_message, on_close=self.on_close, dock="right")
        return True

    def on_close(self):
        self.panel = None

    def _base(self):
        cfg = _config(self)
        return moonraker_base(_bundle_value("print_host"), cfg.get("printer_url", ""))

    def _refresh(self):
        self.error = ""
        base = self._base()
        if not base:
            self.error = "Set the printer's host (Printer settings › Connection / print host) or printer_url in the plugin settings."
            return
        cfg = _config(self)
        try:
            spools, _ = fetch_spools(base, _bundle_value("printhost_apikey") or "",
                                     float(cfg.get("timeout_s", DEFAULT_TIMEOUT_S)))
            STATE.update(spools=spools, spools_base=base, spools_time=time.time())
        except PermissionError as e:
            self.error = f"OrcaSlicer blocked the network request ({e}). Allow it when asked, then Refresh."
        except Exception as e:  # noqa: BLE001 - shown to the user
            self.error = f"Could not read ACE spools from {base}: {e}"

    def _push(self):
        if self.panel is None:
            return
        filaments = _current_project()
        _prune_choices(filaments)
        resolved = resolve_mapping(filaments, STATE["spools"], STATE["choices"])
        self.panel.post({
            "command": "state",
            "host": STATE["spools_base"] or self._base(),
            "refreshed": time.strftime("%H:%M:%S", time.localtime(STATE["spools_time"])) if STATE["spools_time"] else "",
            "filaments": filaments,
            "spools": STATE["spools"],
            "units": len({s["unit"] for s in STATE["spools"]}) or 1,
            "choices": STATE["choices"],
            "resolved": {str(k): v for k, v in resolved.items()},
            "enabled": STATE["enabled"],
            "error": self.error,
            "last": STATE["last_written"],
        })

    # Runs on the UI thread.
    def on_message(self, message):
        message = message or {}
        command = message.get("command")
        if command == "refresh":
            self._refresh()
        elif command == "set":
            STATE["choices"][str(int(message.get("index", 0)))] = str(message.get("choice", "auto"))
        elif command == "reset":
            STATE["choices"].clear()
        elif command == "enable":
            STATE["enabled"] = bool(message.get("value"))
        self._push()


class AceSpoolMap(orca.slicing.SlicingPipelineCapabilityBase):
    """G-code post-process: write ACE_SET_TOOL_MAP. Never touches orca.host.ui (worker thread)."""

    def get_name(self):
        return "ACE Spool Map"

    def get_default_config(self):
        return {"printer_url": DEFAULT_PRINTER_URL, "timeout_s": DEFAULT_TIMEOUT_S, "live_lookup": True}

    def execute(self, ctx):
        if ctx.step != orca.slicing.Step.psGCodePostProcess:
            return orca.ExecutionResult.success()
        if not ctx.gcode_path:
            return orca.ExecutionResult.success("ACE Spool Map: no G-code path")
        if not STATE["enabled"]:
            return orca.ExecutionResult.success("ACE Spool Map: disabled in the ACE Spools panel")

        cfg = _config(self)
        filaments = project_filaments(
            parse_config_list(ctx.config_value("filament_colour")),
            parse_config_list(ctx.config_value("filament_type")),
            parse_config_list(ctx.config_value("filament_settings_id")))

        with open(ctx.gcode_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        if any(line.startswith("ACE_SET_TOOL_MAP") for line in lines[:400]):
            return orca.ExecutionResult.success("ACE Spool Map: already present")
        used = tools_in_gcode(lines) or [0]

        spools = []
        base = moonraker_base(ctx.config_value("print_host"), cfg.get("printer_url", "")) or STATE["spools_base"]
        if base and cfg.get("live_lookup", True):
            try:
                # Network access to the printer is granted once when the plugin loads
                # (register_capabilities); without it this call fails and the cached spools are used.
                spools, _ = fetch_spools(base, ctx.config_value("printhost_apikey") or "",
                                         float(cfg.get("timeout_s", DEFAULT_TIMEOUT_S)))
                STATE.update(spools=spools, spools_base=base, spools_time=time.time())
            except Exception:  # noqa: BLE001
                spools = []
        if not spools and STATE["spools"] and (not base or STATE["spools_base"] == base):
            spools = STATE["spools"]

        sig_ok = STATE.get("signature") == _signature(filaments)
        choices = STATE["choices"] if sig_ok else {}
        if not spools and not any(str(c).isdigit() for c in choices.values()):
            STATE["last_written"] = "no ACE spool data – printed as sliced"
            new_lines = [
                "; ACE Spool Mapper: no ACE spool data (open the ACE Spools panel and Refresh) - as sliced\n",
                "ACE_SET_TOOL_MAP MAP=" + (f" FILE={gcode_param(ctx.output_name)}" if ctx.output_name else "")
                + " KEEP_EXISTING=1\n",
            ]
        else:
            mapping = resolve_mapping(filaments, spools, choices, only=set(used))
            for t in used:
                mapping.setdefault(t, t)
            summary = describe(mapping, filaments, spools)
            STATE["last_written"] = f"{ctx.output_name or 'G-code'}: {summary}"
            new_lines = map_lines(mapping, ctx.output_name, summary)

        lines = insert_before_first_command(lines, new_lines)
        with open(ctx.gcode_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        return orca.ExecutionResult.success("ACE Spool Map: " + STATE["last_written"])


@orca.plugin
class AceSpoolMapperPlugin(orca.base):
    def register_capabilities(self):
        orca.register_capability(AceSpoolsPanel)
        orca.register_capability(AceSpoolMap)
        # Ask for network access to the printer once, when Orca loads the plugin. The grant covers
        # the whole host, so later lookups (panel Refresh and the post-process step at print start)
        # never pop a permission dialog.
        request = getattr(orca, "request_permissions", None)
        if request is None:
            return
        hosts = []
        for candidate in (_safe_bundle_host(), DEFAULT_PRINTER_URL):
            base = moonraker_base(candidate) if candidate else ""
            if base and base not in hosts:
                hosts.append(base)
        try:
            request(network=hosts)
        except ValueError:  # an odd print_host value; fall back to the default printer
            request(network=[moonraker_base(DEFAULT_PRINTER_URL)])


def _safe_bundle_host():
    try:
        return str(_bundle_value("print_host") or "").strip().strip('"')
    except Exception:  # noqa: BLE001
        return ""

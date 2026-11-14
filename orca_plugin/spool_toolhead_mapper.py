# /// script
# requires-python = ">=3.12"
#
# [tool.orcaslicer.plugin]
# name = "Spool and Toolhead Mapper"
# description = "One plugin for two printers: ACE Pro (acepro-any-klipper) and WonderMaker ZR Ultra-S toolheads. It asks the printer which one it is, shows the spools or toolheads in a panel, and writes the choice into the G-code (ACE_SET_TOOL_MAP or WM_SET_TOOL_MAP)."
# author = "ducati1198"
# version = "0.7.1"
# ///
"""Spool and Toolhead Mapper for OrcaSlicer 2.5.

Combines "ACE Spool Mapper" (acepro-any-klipper, ACE Pro) and "WM Toolhead Mapper" (WonderMaker ZR Ultra-S,
wm-ultra-fluidd-acepro-panel). NOT YET TESTED IN ORCASLICER (the helper functions are tested outside it).

The printer is detected through Moonraker each time the panel refreshes or G-code is written:

  * the printer has filament_switch_sensor filament0..3            -> kind "wm"  (the four WonderMaker toolheads)
  * otherwise the printer has the Klipper object "ace"             -> kind "ace" (ACE Pro spools T0..T3, T4..T7 ...)
  * anything else                                                   -> nothing is written into the G-code

A WonderMaker printer that also has an ACE Pro (both exist) is a "wm" printer: WM_SET_TOOL_MAP is the map that matters
there. To force one side, set printer_kind to "wm" or "ace" in Plugins > Spool and Toolhead Mapper > Config
(default "auto").

Two capabilities:

* "Spools and Toolheads" (Script): docks a panel beside the 3D view listing every project filament with a dropdown
  of the printer's live spools or toolheads. "Auto" picks the best one (same material, closest colour, each used
  once where possible); you can pin any filament to a spool/toolhead or to "as sliced".

* "Spool and Toolhead Map" (Slicing Pipeline, G-code post-process step): enable it once in
  Process > Others > Slicing Pipeline Plugin. When G-code is exported or uploaded it inserts, before the start G-code:

      ACE_SET_TOOL_MAP MAP=0:4,1:2 FILE="name.gcode" KEEP_EXISTING=1                 (ACE Pro)
      WM_SET_TOOL_MAP MAP=0:2,1:3,2:2,3:3 FILE="name.gcode" KEEP_EXISTING=1          (WonderMaker, always all four)

  ACE Pro printers can also get the purge length per tool change (panel section "Purge length", off by default):
  Orca's flush volumes are written as ACE_SET_PURGE_AMOUNT PURGELENGTH=<mm> PURGESPEED=<mm/min> before each T<n>.

  This step never opens UI (Orca forbids UI calls from slicing hooks); it uses the panel's choices, else
  auto-matches against what it can read from the printer.
"""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import orca

SLOTS_PER_ACE = 4
HEADS = 4
COLOUR_WARN = 300   # colour_distance above this (e.g. blue vs light blue) is shown as a warning
SAVE_FILE = os.path.join(os.path.expanduser("~"), ".spool_toolhead_mapper.json")
KINDS = {"ace": "ACE_SET_TOOL_MAP", "wm": "WM_SET_TOOL_MAP"}
LOG_FILE = os.path.join(os.path.expanduser("~"), ".spool_toolhead_mapper.log")   # what the panel did, for troubleshooting
DEFAULT_TIMEOUT_S = 3.0
RE_READ_S = 30          # the open panel reads the printer again when its data is older than this many seconds
# Your printer (Moonraker). Change it in Plugins > Spool and Toolhead Mapper > Config, or leave it empty to use
# the printer preset's print host.
DEFAULT_PRINTER_URL = ""  # empty = use the printer preset's print host

# Shared between the panel (UI thread) and the post-process step (slicing worker thread).
STATE = {
    "spools": [],          # last spools read from the printer
    "spools_base": "",     # Moonraker base URL they came from
    "kind": "",            # "ace", "wm" or "" (not known): what that printer is
    "spools_time": 0.0,
    "choices": {},         # str(filament index) -> "auto" | "sliced" | "<ace tool number>"
    "signature": [],       # [(colour, type)] per filament when choices were made
    "enabled": True,       # write the map into exported G-code
    "last_written": "",    # human readable summary of the last post-process
    "saved": None,         # picks kept between Orca sessions: {printer base URL: {"signature": ..., "choices": ...}}
    "purge": None,         # purge settings (see PURGE_DEFAULTS); loaded from SAVE_FILE on first use
    "last_purge": "",      # human readable summary of the last purge step
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
    host = str(override or print_host or "").strip().strip("\"'").strip()
    if not host:
        return ""
    if "://" not in host:
        host = "http://" + host
    return host.rstrip("/")


def log_line(text, path=None):
    """Append one line to the log file. Never raises."""
    try:
        with open(path or LOG_FILE, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + str(text) + "\n")
    except Exception:  # noqa: BLE001
        pass


def clean_printer_id(value):
    """The printer preset name as Orca returns it, without quote marks."""
    return str(value or "").strip().strip("\"'").strip()


def pick_host(override, saved_host, orca_host):
    """Which address to use: the plugin setting, else the one typed in the panel for this printer, else Orca's print host."""
    return override or saved_host or orca_host or ""


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


# WonderMaker touchscreen colours and materials (tmt1.ini: colorN / materialN are indexes into these lists).
ZR_COLOURS = [
    "#FFFFFF", "#F3E8C8", "#9A6738", "#C7D5DF", "#000000", "#00DDE3", "#13A7E8", "#0B4BD8", "#16E900",
    "#00A84F", "#FFF200", "#FF5A1F", "#DDBFDE", "#E72DBE", "#FF1C2E", "#006EFF", "#D9A520", "#B86B44",
    "#AFC0CC", "#C060C0", "#D5E8EE",
]
ZR_MATERIALS = [
    ("PLA", 210), ("PLA Silk", 215), ("ABS", 250), ("PETG", 240), ("PLA Matte", 210), ("PLA Metal", 215),
    ("ABS Matte", 250), ("PETG Matte", 240), ("PVA", 200), ("TPE", 225), ("Marble", 210), ("HIPS", 235),
    ("TPU", 225), ("PET", 240), ("Wood", 200), ("ASA", 255),
    # added at the end by the ZR Tools screen (same order as its touchscreen list)
    ("PLA+", 215), ("PLA-CF", 220), ("PETG-CF", 250), ("PA", 270), ("PA-CF", 280),
    ("PC", 270), ("ABS-CF", 260), ("PA-GF", 280), ("PC-ABS", 260), ("PP", 230), ("BVOH", 210),
]
# The ZR Tools screen (KlipperScreen) keeps its own material list; zr_t<N>_mat in saved_variables is an index into it.
ZR_TOOLS_MATERIALS = [
    ("Empty", 0), ("PLA", 210), ("PLA+", 215), ("PLA Silk", 215), ("PLA Matte", 210), ("PLA-CF", 220), ("PETG", 240),
    ("PETG-CF", 245), ("ABS", 250), ("ASA", 255), ("TPU", 220), ("PA / Nylon", 270), ("PC", 270), ("PVA", 195),
    ("HIPS", 235), ("Other", 220),
]


def parse_tmt1_slots(text):
    """[slot] colorN / materialN from tmt1.ini -> [{'color': idx|None, 'material': idx|None}] x 4."""
    slots = [{"color": None, "material": None} for _ in range(HEADS)]
    section = ""
    for raw in str(text or "").splitlines():
        line = raw.strip()
        sec = re.match(r"^\[(.+)\]$", line)
        if sec:
            section = sec.group(1).strip().lower()
            continue
        if section != "slot":
            continue
        m = re.match(r"^(color|material)([0-3])\s*=\s*(-?\d+)\s*$", line, re.IGNORECASE)
        if m:
            key, head, value = m.group(1).lower(), int(m.group(2)), int(m.group(3))
            limit = len(ZR_COLOURS) if key == "color" else len(ZR_MATERIALS)
            slots[head][key] = value if 0 <= value < limit else None
    return slots


def _as_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def heads_from_data(slots, sensors, temps=None, variables=None):
    """Four toolheads as 'spools': tool = toolhead number (0-3). `sensors` = {head: filament_detected or None}.

    Same priority as the ZR Tools screen: material = zr_t<N>_mat (saved_variables, index in the ZR Tools list) when set,
    else the tmt1.ini material; colour = tmt1.ini colour when set, else zr_t<N>_color (0xRRGGBB integer)."""
    variables = variables if isinstance(variables, dict) else {}
    heads = []
    for i in range(HEADS):
        slot = slots[i] if i < len(slots) else {"color": None, "material": None}
        detected = sensors.get(i)
        mat = None            # (name, default temperature) or None when unknown
        zr_mat = _as_int(variables.get(f"zr_t{i}_mat"))
        if zr_mat is not None and 0 <= zr_mat < len(ZR_TOOLS_MATERIALS):
            mat = ZR_TOOLS_MATERIALS[zr_mat] if zr_mat > 0 else ("", 0)      # 0 = Empty on the ZR Tools screen
        elif slot["material"] is not None:
            mat = ZR_MATERIALS[slot["material"]]
        if slot["color"] is not None:
            colour = ZR_COLOURS[slot["color"]]
        else:
            rgb = _as_int(variables.get(f"zr_t{i}_color"))
            colour = "#%06X" % (rgb & 0xFFFFFF) if rgb is not None and variables.get(f"zr_t{i}_color") is not None else "#808080"
        has_mat = bool(mat and mat[0])
        ready = detected is not False and has_mat
        temp = _as_int(variables.get(f"zr_t{i}_temp")) or (temps or {}).get(i) or (mat[1] if mat else 0)
        heads.append({
            "tool": i,
            "unit": 0,
            "slot": i,
            "status": "empty" if detected is False else ("ready" if ready else "unknown"),
            "ready": bool(ready),
            "material": mat[0] if (has_mat and detected is not False) else "",
            "colour": colour,
            "temp": temp,
            "rfid": False,
        })
    return heads


def _http_get(url, api_key="", timeout=DEFAULT_TIMEOUT_S):
    headers = {"Accept": "application/json"}
    if api_key:
        headers["X-Api-Key"] = api_key
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _query(base, objects, api_key="", timeout=DEFAULT_TIMEOUT_S):
    qs = "&".join(urllib.parse.quote(o, safe="") for o in objects)
    return json.loads(_http_get(f"{base}/printer/objects/query?{qs}", api_key, timeout))["result"]["status"]


def detect_kind(objects, prefer="auto"):
    """Which printer is this? `objects` = the Klipper object names from /printer/objects/list.

    `prefer` = "auto" (WonderMaker toolheads win when both exist), "wm" or "ace" (force that side when the printer has it)."""
    names = set(objects or [])
    has_wm = any(f"filament_switch_sensor filament{i}" in names for i in range(HEADS))
    has_ace = "ace" in names
    prefer = str(prefer or "auto").strip().lower()
    if prefer == "ace" and has_ace:
        return "ace"
    if prefer == "wm" and has_wm:
        return "wm"
    if has_wm:
        return "wm"
    if has_ace:
        return "ace"
    return ""


def fetch_spools_ace(base, api_key="", timeout=DEFAULT_TIMEOUT_S):
    """Read the ACE spools from Moonraker. Raises on network/HTTP problems."""
    def query(objects):
        return _query(base, objects, api_key, timeout)

    manager = query(["ace"]).get("ace") or {}
    if "ace_instances" not in manager:
        raise RuntimeError("printer has no ACE driver object ('ace')")
    count = max(1, int(manager.get("ace_instances") or 1))
    status = query([f"ace_instance_{i}" for i in range(count)])
    return spools_from_status(status, count), manager


def fetch_spools_wm(base, api_key="", timeout=DEFAULT_TIMEOUT_S):
    """Read the four WonderMaker toolheads (tmt1.ini + filament sensors). Raises on network/HTTP problems."""
    ini = _http_get(f"{base}/server/files/config/tmt1.ini", api_key, timeout)
    status = _query(base, [f"filament_switch_sensor filament{i}" for i in range(HEADS)] + ["save_variables"], api_key, timeout)
    variables = (status.get("save_variables") or {}).get("variables") or {}
    sensors = {}
    for i in range(HEADS):
        v = (status.get(f"filament_switch_sensor filament{i}") or {}).get("filament_detected")
        sensors[i] = v if isinstance(v, bool) else None
    if all(v is None for v in sensors.values()):
        raise RuntimeError("printer has no filament0..3 sensors (is this a ZR Ultra-S with Klipper running?)")
    return heads_from_data(parse_tmt1_slots(ini), sensors, None, variables), {}


def fetch_spools(base, api_key="", timeout=DEFAULT_TIMEOUT_S, prefer="auto"):
    """Detect the printer and read its spools or toolheads. Returns (spools, kind). Raises when it is neither."""
    listing = json.loads(_http_get(f"{base}/printer/objects/list", api_key, timeout))["result"]["objects"]
    kind = detect_kind(listing, prefer)
    if kind == "ace":
        return fetch_spools_ace(base, api_key, timeout)[0], kind
    if kind == "wm":
        return fetch_spools_wm(base, api_key, timeout)[0], kind
    raise RuntimeError("this printer has neither an ACE Pro ('ace') nor the WonderMaker filament sensors")


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
    """Combine panel choices with auto-match. Returns {sliced tool: ACE tool or WonderMaker toolhead}."""
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


def map_lines(mapping, output_name, summary, kind="ace"):
    if kind == "wm":    # the WonderMaker macro always gets all four print tools (a map from an earlier print is never reused)
        full = {t: t for t in range(HEADS)}
        full.update({a: b for a, b in mapping.items() if 0 <= a < HEADS and 0 <= b < HEADS})
        pairs = ",".join(f"{a}:{b}" for a, b in sorted(full.items()))
    else:
        pairs = ",".join(f"{a}:{b}" for a, b in sorted(mapping.items()) if a != b)
    cmd = f"{KINDS.get(kind, KINDS['ace'])} MAP={pairs}"
    if output_name:
        cmd += f" FILE={gcode_param(output_name)}"
    cmd += " KEEP_EXISTING=1"
    return [f"; Spool and Toolhead Mapper ({kind}): {summary}\n", cmd + "\n"]


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


def describe(mapping, filaments, spools, kind="ace"):
    by_tool = {s["tool"]: s for s in spools}
    parts = []
    for a, b in sorted(mapping.items()):
        sp = by_tool.get(b)
        label = (f"Toolhead {b + 1}" if kind == "wm" else f"T{b}") + (f" {sp['material']}" if sp and sp["material"] else "")
        parts.append(f"T{a}->{label}" if a != b else f"T{a} as sliced")
    return ", ".join(parts) if parts else "no filaments"


# --------------------------------------------------------------------------------------
# Purge length (ACE Pro only): Orca flush volumes -> ACE_SET_PURGE_AMOUNT before each tool change
# --------------------------------------------------------------------------------------

PURGE_DEFAULTS = {
    "enabled": False,     # off until you tick it in the panel
    "multiplier": 1.0,    # scales Orca's flush volumes (done here, NOT with purge_multiplier in the printer config)
    "speed": 300.0,       # mm/min, written as PURGESPEED
    "min_mm": 20.0,       # shortest purge written (mm of filament)
    "max_mm": 400.0,      # longest purge written (mm of filament)
    "reset_mm": 50.0,     # must equal default_color_change_purge_length in acepro_setting.cfg
    "reset_lines": True,  # also write ACE_SET_PURGE_AMOUNT <reset_mm> at the start and end of the file
}
PURGE_MARK = "; Spool and Toolhead Mapper purge"
_PURGE_LIMITS = {"multiplier": (0.0, 20.0), "speed": (30.0, 3000.0), "min_mm": (0.0, 1000.0),
                 "max_mm": (0.0, 2000.0), "reset_mm": (0.0, 1000.0)}


def clean_purge(values, base=None):
    """Return a complete, valid purge settings dict from partial or untrusted values."""
    out = dict(base or PURGE_DEFAULTS)
    values = values if isinstance(values, dict) else {}
    for key, (lo, hi) in _PURGE_LIMITS.items():
        if key in values:
            try:
                v = float(values[key])
            except (TypeError, ValueError):
                continue
            if v == v:   # not NaN
                out[key] = min(max(v, lo), hi)
    for key in ("enabled", "reset_lines"):
        if key in values:
            out[key] = bool(values[key])
    if out["max_mm"] < out["min_mm"]:
        out["max_mm"] = out["min_mm"]
    return out


def parse_number_list(value):
    """Floats from an Orca vector option; ';' and ',' both separate (flush matrices use ',')."""
    out = []
    for part in re.split(r"[;,]", str(value or "")):
        part = part.strip().strip('"')
        if not part:
            continue
        try:
            out.append(float(part))
        except ValueError:
            return []
    return out


def flush_matrix(value, n):
    """n x n flush volumes (mm3), row = from filament, column = to filament; None if the option does not fit."""
    nums = parse_number_list(value)
    if n < 1 or len(nums) < n * n or len(nums) % (n * n):
        return None
    return [nums[r * n:(r + 1) * n] for r in range(n)]   # first block only (a multi-extruder printer repeats it)


def purge_mm(volume_mm3, diameter, multiplier, min_mm, max_mm):
    """Flush volume (mm3) -> mm of filament, scaled and limited."""
    d = diameter if diameter and diameter > 0 else 1.75
    mm = (volume_mm3 / (3.141592653589793 * (d / 2.0) ** 2)) * multiplier
    return round(min(max(mm, min_mm), max_mm), 1)


def purge_table(matrix, diameters, flush_mult, settings):
    """{(from, to): mm of filament} for every pair of different filaments."""
    n = len(matrix)
    table = {}
    for a in range(n):
        for b in range(n):
            if a != b:
                d = diameters[b] if b < len(diameters) else (diameters[0] if diameters else 1.75)
                table[(a, b)] = purge_mm(matrix[a][b] * flush_mult, d, settings["multiplier"],
                                         settings["min_mm"], settings["max_mm"])
    return table


def purge_command(mm, speed, label=""):
    cmd = f"ACE_SET_PURGE_AMOUNT PURGELENGTH={mm:.1f} PURGESPEED={speed:g}"
    return cmd + (f" ; {label}" if label else "") + "\n"


def insert_purge_lines(lines, table, settings):
    """Put ACE_SET_PURGE_AMOUNT before every tool change T<n> (the sliced tool numbers). Returns (lines, count).

    The first tool of the file is not a change (the printer loads it with the default purge length)."""
    tool_re = re.compile(r"^\s*T(\d+)\s*(?:;.*)?$")
    start_re = re.compile(r"\bTOOL=(\d+)\b", re.IGNORECASE)
    out, current, count = [], None, 0
    for line in lines:
        stripped = line.lstrip()
        if current is None and "START_PRINT" in stripped.upper() and not stripped.startswith(";"):
            m = start_re.search(line)
            if m:
                current = int(m.group(1))
        m = tool_re.match(line)
        if m:
            n = int(m.group(1))
            if current is None:
                current = n
            elif n != current:
                mm = table.get((current, n))
                if mm is not None:
                    out.append(purge_command(mm, settings["speed"], f"T{current}->T{n}"))
                    count += 1
                current = n
        out.append(line)
    return out, count


def reset_lines(settings):
    return [purge_command(settings["reset_mm"], settings["speed"], "reset to the default purge length")]


def apply_purge(lines, matrix, diameters, flush_mult, settings):
    """All purge edits for one G-code file: per-change lines plus the optional reset at start and end.

    Returns (lines, summary). `lines` is unchanged when there is nothing to do."""
    if any(line.startswith(PURGE_MARK) for line in lines[:400]):
        return lines, "already present"
    if matrix is None:
        return lines, "flush volumes not found - purge left to the printer's default"
    table = purge_table(matrix, diameters, flush_mult, settings)
    lines, count = insert_purge_lines(lines, table, settings)
    head = [f"{PURGE_MARK}: {count} tool change(s), x{settings['multiplier']:g}, {settings['speed']:g} mm/min, "
            f"{settings['min_mm']:g}-{settings['max_mm']:g} mm\n"]
    if settings["reset_lines"]:
        head += reset_lines(settings)
        if lines and not lines[-1].endswith("\n"):
            lines = lines[:-1] + [lines[-1] + "\n"]
        lines = lines + reset_lines(settings)
    lines = insert_before_first_command(lines, head)
    return lines, f"{count} change(s) x{settings['multiplier']:g}"


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


def warnings_for(filaments, spools, resolved, kind="ace"):
    """Hints shown under each filament: {filament index: [text]}. Never blocks anything."""
    by_tool = {s["tool"]: s for s in spools}
    name = (lambda t: f"Toolhead {t + 1}") if kind == "wm" else (lambda t: f"T{t}")
    users = {}
    for f in filaments:
        t = resolved.get(f["index"])
        if t is not None:
            users.setdefault(t, []).append(f["index"])
    out = {}
    for f in filaments:
        t = resolved.get(f["index"])
        sp = by_tool.get(t)
        msgs = []
        if t is not None and len(users.get(t, [])) > 1:
            others = ", ".join(str(i + 1) for i in users[t] if i != f["index"])
            msgs.append(f"{name(t)} is also used by filament {others}")
        if sp is not None and not sp.get("ready") and kind == "wm":
            msgs.append(f"{name(t)} shows empty: load filament before you start")
        if sp is not None and sp.get("ready") and f.get("colour") and sp.get("colour") \
                and color_distance(f["colour"], sp["colour"]) > COLOUR_WARN:
            msgs.append(f"colour differs from {name(t)}")
        if msgs:
            out[f["index"]] = msgs
    return out


def load_saved(path=None):
    """Picks kept from an earlier session. Never raises: a missing or unreadable file means no saved picks."""
    try:
        with open(path or SAVE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_picks(base, signature, choices, path=None):
    """Remember the picks for this printer. Best effort: Orca may not allow writing a file, then picks last for the session."""
    saved = STATE.get("saved")
    if saved is None:
        saved = STATE["saved"] = load_saved(path)
    if choices:
        saved[base or ""] = {"signature": signature, "choices": dict(choices)}
    else:
        saved.pop(base or "", None)
    try:
        with open(path or SAVE_FILE, "w", encoding="utf-8") as f:
            json.dump(saved, f)
    except OSError:
        pass


def restore_picks(base, filaments, path=None):
    """Put back this printer's saved picks when the project's filaments are the same as when they were made."""
    saved = STATE.get("saved")
    if saved is None:
        saved = STATE["saved"] = load_saved(path)
    entry = saved.get(base or "") or {}
    sig = _signature(filaments)
    if entry.get("signature") == sig and isinstance(entry.get("choices"), dict):
        STATE["choices"], STATE["signature"] = dict(entry["choices"]), sig
        return True
    return False


def load_purge(path=None):
    """Purge settings from STATE, else from the save file (key "_purge"), else the defaults."""
    if STATE.get("purge") is None:
        saved = STATE.get("saved")
        if saved is None:
            saved = STATE["saved"] = load_saved(path)
        STATE["purge"] = clean_purge(saved.get("_purge"))
    return STATE["purge"]


def save_purge(values, path=None):
    STATE["purge"] = clean_purge(values, load_purge(path))
    saved = STATE.get("saved")
    if saved is None:
        saved = STATE["saved"] = load_saved(path)
    saved["_purge"] = dict(STATE["purge"])
    try:
        with open(path or SAVE_FILE, "w", encoding="utf-8") as f:
            json.dump(saved, f)
    except OSError:
        pass
    return STATE["purge"]


def saved_host(printer_id, path=None):
    """The address typed in the panel for this printer preset ('' when none)."""
    saved = STATE.get("saved")
    if saved is None:
        saved = STATE["saved"] = load_saved(path)
    hosts = saved.get("_hosts")
    return str((hosts or {}).get(clean_printer_id(printer_id), "")) if isinstance(hosts, dict) else ""


def save_host(printer_id, value, path=None):
    """Remember the address for this printer preset. An empty value forgets it."""
    saved = STATE.get("saved")
    if saved is None:
        saved = STATE["saved"] = load_saved(path)
    hosts = saved.get("_hosts") if isinstance(saved.get("_hosts"), dict) else {}
    key, value = clean_printer_id(printer_id), str(value or "").strip()
    if value:
        hosts[key] = value
    else:
        hosts.pop(key, None)
    saved["_hosts"] = hosts
    try:
        with open(path or SAVE_FILE, "w", encoding="utf-8") as f:
            json.dump(saved, f)
    except OSError:
        pass


def purge_inputs(value_of, n):
    """(matrix, diameters, flush multiplier) from project settings; value_of(key) reads one option."""
    matrix = flush_matrix(value_of("flush_volumes_matrix"), n)
    diameters = parse_number_list(value_of("filament_diameter"))
    mult = parse_number_list(value_of("flush_multiplier"))
    return matrix, diameters, (mult[0] if mult else 1.0)


def purge_preview():
    """Rows for the panel: mm of filament purged for every from -> to pair of the current project."""
    filaments = _current_project()
    matrix, diameters, fm = purge_inputs(_bundle_value, len(filaments))
    if matrix is None:
        return None
    table = purge_table(matrix, diameters, fm, load_purge())
    n = len(matrix)
    return [[None if a == b else table[(a, b)] for b in range(n)] for a in range(n)]


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
  .pgrid { display: grid; grid-template-columns: 1fr 90px; gap: 5px 8px; align-items: center; margin-top: 8px; }
  .pgrid input { width: 90px; }
  table.pv { border-collapse: collapse; margin-top: 4px; }
  table.pv td, table.pv th { border: 1px solid var(--orca-border); padding: 2px 6px; text-align: right; font-weight: normal; }
</style>
<h3 id="title">Spools and toolheads</h3>
<div class="muted" id="host">Printer: …</div>
<div class="bar">
  <input type="text" id="host_in" placeholder="Printer address, e.g. 10.11.88.77" style="flex:1; min-width:120px">
  <button type="button" id="host_save">Save address</button>
</div>
<div class="bar">
  <button type="button" id="refresh">Refresh</button>
  <button type="button" id="reset" class="quiet">All auto</button>
</div>
<div class="muted" id="status"></div>
<div id="rows"></div>
<label class="chk"><input type="checkbox" id="enabled"> Write this map into G-code when sending</label>
<div class="muted" style="margin-top:6px" id="what">When ticked, your picks are written as one line near the top of the G-code, so the printer uses them at print start. Untick it to send the file as sliced.</div>
<div class="muted" style="margin-top:6px"><b>One-time setup:</b> switch Orca to Advanced mode, open Process › Others › Slicing Pipeline Plugin, add “Spool and Toolhead Map” and save the process preset (for each process preset you print with). Without this step nothing is written, even when the box is ticked.</div>
<div class="muted" id="last"></div>
<div id="purgebox" style="display:none">
  <h3 style="margin-top:14px">Purge length (ACE Pro)</h3>
  <label class="chk"><input type="checkbox" id="p_enabled"> Write purge lengths into G-code</label>
  <div class="muted" style="margin-top:4px">Orca's flush volumes become <code>ACE_SET_PURGE_AMOUNT</code> before each tool change. Needs <code>purge_multiplier: 1.0</code> in acepro_setting.cfg.</div>
  <div class="pgrid">
    <label>Multiplier</label><input type="number" step="0.1" min="0" id="p_multiplier">
    <label>Speed (mm/min)</label><input type="number" step="10" min="30" id="p_speed">
    <label>Min (mm)</label><input type="number" step="1" min="0" id="p_min_mm">
    <label>Max (mm)</label><input type="number" step="10" min="0" id="p_max_mm">
    <label>Reset length (mm)</label><input type="number" step="1" min="0" id="p_reset_mm">
  </div>
  <label class="chk"><input type="checkbox" id="p_reset_lines"> Reset to this length at the start and end of the file</label>
  <div class="muted" style="margin-top:4px">Reset length must equal <code>default_color_change_purge_length</code> in acepro_setting.cfg.</div>
  <div class="muted" style="margin-top:8px"><b>Preview</b> (mm of filament, from row to column)</div>
  <div id="p_preview" class="muted"></div>
  <div class="muted" id="p_last"></div>
</div>
<div class="err" id="error"></div>
<script>
(function () {
  var state = null;
  function esc(v) { var s = document.createElement("span"); s.textContent = v == null ? "" : String(v); return s.innerHTML; }
  function slotName(s) { return state.kind === "wm" ? "Toolhead " + (s.tool + 1) : "T" + s.tool; }
  function spoolLabel(s) {
    var where = (state.kind !== "wm" && state.units > 1) ? " (ACE " + (s.unit + 1) + ")" : "";
    if (!s.ready) return slotName(s) + " · empty" + where;
    return slotName(s) + " · " + (s.material || "?") + (s.temp ? " · " + s.temp + "°C" : "") + where;
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
    document.getElementById("host").textContent = "Printer " + (state.printer_id ? "“" + state.printer_id + "” " : "") + ": " +
      (state.host || "no address yet (type it below)") + (state.refreshed ? " · read " + state.refreshed : "");
    var hin = document.getElementById("host_in");
    if (document.activeElement !== hin) hin.value = state.host_saved || "";
    document.getElementById("title").textContent = state.kind === "wm" ? "WonderMaker toolheads" :
      (state.kind === "ace" ? "ACE Pro spools" : "Spools and toolheads");
    document.getElementById("enabled").checked = !!state.enabled;
    var macro = state.kind === "wm" ? "WM_SET_TOOL_MAP" : (state.kind === "ace" ? "ACE_SET_TOOL_MAP" : "WM_SET_TOOL_MAP or ACE_SET_TOOL_MAP");
    document.getElementById("what").textContent = "When ticked, your picks are written as one line (" + macro +
      ") near the top of the G-code, so the printer uses them at print start. Untick it to send the file as sliced.";
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
                   { value: "sliced", colour: asSliced && asSliced.ready ? asSliced.colour : "", label: "As sliced (" + (state.kind === "wm" ? "Toolhead " + (f.index + 1) : "T" + f.index) + ")" }];
      state.spools.forEach(function (s) {
        items.push({ value: String(s.tool), colour: s.ready ? s.colour : "", label: spoolLabel(s), off: !s.ready && state.kind !== "wm" });
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
        warn = '<div class="hint warn">Sliced for ' + esc(f.type) + ', ' + (state.kind === "wm" ? "toolhead holds " : "spool is ") + esc(sp.material) + '</div>';
      html += '<div class="row"><div class="dot" style="background:' + esc(f.colour || "#888") + '"></div>' +
              '<div class="name">Filament ' + (f.index + 1) + ' · ' + esc(f.type || "?") +
              (f.name ? ' <span class="muted">' + esc(f.name) + '</span>' : '') + '</div>' +
              dd +
              ((state.warnings[String(f.index)] || []).map(function (w) { return '<div class="hint warn">' + esc(w) + '</div>'; }).join('')) +
              (sp ? '<div class="hint"><span class="dot" style="display:inline-block;width:10px;height:10px;vertical-align:middle;background:' +
                    esc(sp.colour) + '"></span> prints from ' + esc(spoolLabel(sp)) + '</div>' : '') + warn + '</div>';
    });
    document.getElementById("rows").innerHTML = html;
    renderPurge();
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
          send({ command: "set", index: Number(dd.getAttribute("data-index")), choice: opt.getAttribute("data-value") });
        });
      });
    });
  }
  var PKEYS = ["multiplier", "speed", "min_mm", "max_mm", "reset_mm"];
  function renderPurge() {
    var box = document.getElementById("purgebox");
    box.style.display = state.kind === "ace" && state.purge ? "block" : "none";
    if (!state.purge) return;
    document.getElementById("p_enabled").checked = !!state.purge.enabled;
    document.getElementById("p_reset_lines").checked = !!state.purge.reset_lines;
    PKEYS.forEach(function (k) {
      var el = document.getElementById("p_" + k);
      if (document.activeElement !== el) el.value = state.purge[k];
    });
    var pv = state.purge_preview, t = "";
    if (!pv) t = "Flush volumes not found for this project.";
    else {
      // colour of the spool each filament prints from (the live colour read from the printer), else the project colour
      var cols = (state.filaments || []).map(function (f) {
        var target = state.resolved[String(f.index)];
        var sp = state.spools.filter(function (x) { return x.tool === target; })[0];
        return sp && sp.ready && sp.colour ? sp.colour : (f.colour || "");
      });
      function head(i) { return '<span class="sw" style="display:inline-block;vertical-align:middle;margin-right:4px;background:' + esc(cols[i] || "#888") + '"></span>T' + i; }
      t = '<table class="pv"><tr><th></th>' + pv.map(function (r, i) { return "<th>" + head(i) + "</th>"; }).join("") + "</tr>" +
        pv.map(function (row, a) {
          return "<tr><th>" + head(a) + "</th>" + row.map(function (v) { return "<td>" + (v == null ? "·" : v) + "</td>"; }).join("") + "</tr>";
        }).join("") + "</table>";
    }
    document.getElementById("p_preview").innerHTML = t;
    document.getElementById("p_last").textContent = state.purge_last ? "Last G-code: " + state.purge_last : "";
  }
  function sendPurge() {
    var v = { enabled: document.getElementById("p_enabled").checked, reset_lines: document.getElementById("p_reset_lines").checked };
    PKEYS.forEach(function (k) { v[k] = Number(document.getElementById("p_" + k).value); });
    send({ command: "purge", values: v });
  }
  ["p_enabled", "p_reset_lines"].concat(PKEYS.map(function (k) { return "p_" + k; })).forEach(function (id) {
    document.getElementById(id).addEventListener("change", sendPurge);
  });
  var waiting = null;
  function stamp() { var d = new Date(); return ("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2) + ":" + ("0" + d.getSeconds()).slice(-2); }
  function status(t) { document.getElementById("status").textContent = t; }
  function send(msg) {
    status("Sent " + msg.command + " at " + stamp() + " …");
    if (waiting) clearTimeout(waiting);
    waiting = setTimeout(function () {
      status("No answer from the plugin to " + msg.command + " (sent " + stamp() + "). The message did not arrive or the plugin is stuck.");
    }, 6000);
    orca.postMessage(msg);
  }
  orca.onMessage(function (m) {
    if (!m) return;
    if (m.command === "state") { if (waiting) { clearTimeout(waiting); waiting = null; } status("Answer received " + stamp()); state = m; render(); }
    if (m.command === "plugin_error") { if (waiting) { clearTimeout(waiting); waiting = null; } status(""); document.getElementById("error").textContent = m.error || ""; }
  });
  document.getElementById("refresh").addEventListener("click", function () { send({ command: "refresh" }); });
  document.getElementById("host_save").addEventListener("click", function () {
    send({ command: "set_host", value: document.getElementById("host_in").value });
  });
  document.getElementById("host_in").addEventListener("keydown", function (e) {
    if (e.key === "Enter") send({ command: "set_host", value: this.value });
  });
  document.getElementById("reset").addEventListener("click", function () { send({ command: "reset" }); });
  document.getElementById("enabled").addEventListener("change", function (e) {
    send({ command: "enable", value: e.target.checked });
  });
  send({ command: "refresh" });
  setInterval(function () { orca.postMessage({ command: "tick" }); }, 3000);   // notices a printer switch
})();
</script>
"""


class SpoolsPanel(orca.script.ScriptPluginCapabilityBase):
    panel = None
    error = ""

    def get_name(self):
        return "Spools and Toolheads"

    def get_default_config(self):
        return {"printer_url": DEFAULT_PRINTER_URL, "timeout_s": DEFAULT_TIMEOUT_S, "open_on_start": True, "printer_kind": "auto"}

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
            return orca.ExecutionResult.success("Spools and Toolheads panel opened.")
        return orca.ExecutionResult.success("Spools and Toolheads panel is already open.")

    def _open(self):
        if self.panel is not None and self.panel.is_open():
            self.panel.show()
            return False
        self.panel = orca.host.ui.create_dock_panel(
            html=PANEL_HTML, title="Spools and Toolheads", width=330, height=520,
            on_message=self.on_message, on_close=self.on_close, dock="right")
        return True

    def on_close(self):
        self.panel = None

    def _printer_id(self):
        return clean_printer_id(_bundle_value("printer_settings_id"))

    def _base(self):
        cfg = _config(self)
        host = pick_host(cfg.get("printer_url", ""), saved_host(self._printer_id()), clean_printer_id(_bundle_value("print_host")))
        return moonraker_base(host)

    def _refresh(self):
        self.error = ""
        old_base, old_kind = STATE["spools_base"], STATE["kind"]
        base = self._base()
        STATE["printer_key"] = (self._printer_id(), base)
        if not base:
            pid = self._printer_id()
            self.error = ("No address for printer" + (f" “{pid}”" if pid else "") +
                          ". Type it in the box at the top (for example 10.11.88.77) and press Save address.")
            return
        cfg = _config(self)
        try:
            spools, kind = fetch_spools(base, _bundle_value("printhost_apikey") or "",
                                        float(cfg.get("timeout_s", DEFAULT_TIMEOUT_S)), cfg.get("printer_kind", "auto"))
            STATE.update(spools=spools, spools_base=base, spools_time=time.time(), kind=kind)
            log_line(f"read {base} printer={self._printer_id()!r} kind={kind}: " +
                     "; ".join(f"T{x['tool']} {x['status']} {x['material'] or '-'} {x['colour']}" for x in spools))
            if (base, kind) != (old_base, old_kind):    # another printer: its picks, not the last one's
                STATE["choices"], STATE["signature"] = {}, []
                restore_picks(base, _current_project())
        except PermissionError as e:
            self.error = f"OrcaSlicer blocked the network request ({e}). Allow it when asked, then Refresh."
            log_line(f"read {base} printer={self._printer_id()!r} BLOCKED: {e}")
        except Exception as e:  # noqa: BLE001 - shown to the user
            self.error = f"Could not read the spools or toolheads from {base}: {e}"
            log_line(f"read {base} printer={self._printer_id()!r} FAILED: {type(e).__name__}: {e}")

    def _push(self):
        if self.panel is None:
            return
        filaments = _current_project()
        if not STATE["choices"] and not STATE["signature"]:
            restore_picks(STATE["spools_base"] or self._base(), filaments)
        _prune_choices(filaments)
        resolved = resolve_mapping(filaments, STATE["spools"], STATE["choices"])
        line = ("show printer=%r kind=%s project=[%s] picks=%s -> %s" % (
            self._printer_id(), STATE["kind"], ", ".join(f"{f['index']}:{f['type'] or '?'} {f['colour']}" for f in filaments),
            STATE["choices"], resolved))
        if line != STATE.get("last_show"):
            STATE["last_show"] = line
            log_line(line)
        self.panel.post({
            "command": "state",
            "printer_id": self._printer_id(),
            "host_saved": saved_host(self._printer_id()),
            "host": self._base() or STATE["spools_base"],
            "refreshed": time.strftime("%H:%M:%S", time.localtime(STATE["spools_time"])) if STATE["spools_time"] else "",
            "filaments": filaments,
            "spools": STATE["spools"],
            "kind": STATE["kind"],
            "warnings": {str(k): v for k, v in warnings_for(filaments, STATE["spools"], resolved, STATE["kind"]).items()},
            "units": len({s["unit"] for s in STATE["spools"]}) or 1,
            "choices": STATE["choices"],
            "resolved": {str(k): v for k, v in resolved.items()},
            "enabled": STATE["enabled"],
            "error": self.error,
            "last": STATE["last_written"],
            "purge": load_purge(),
            "purge_preview": purge_preview(),
            "purge_last": STATE["last_purge"],
        })

    # Runs on the UI thread.
    def on_message(self, message):
        message = message if isinstance(message, dict) else {}
        command = message.get("command")
        if command != "tick":
            log_line(f"panel message: {command}")
        try:
            self._handle(message, command)
        except Exception as e:  # noqa: BLE001 - show it in the panel instead of failing silently
            import traceback
            log_line("panel error: " + traceback.format_exc().replace("\n", " | "))
            self.error = f"Plugin error in '{command}': {type(e).__name__}: {e}"
            try:
                if self.panel is not None:
                    self.panel.post({"command": "plugin_error", "error": self.error})
            except Exception:  # noqa: BLE001
                pass

    def _handle(self, message, command):
        if command == "refresh":
            self._refresh()
        elif command == "set_host":
            save_host(self._printer_id(), message.get("value", ""))
            self._refresh()
        elif command == "tick":
            key = (self._printer_id(), self._base())
            if key != STATE.get("printer_key"):            # another printer preset or address: read the new printer
                STATE["printer_key"] = key
                STATE["choices"], STATE["signature"] = {}, []
                STATE["spools"], STATE["kind"] = [], ""
                self._refresh()
            else:
                sig = json.dumps(_signature(_current_project()))
                if sig != STATE.get("project_sig"):               # filaments added or recoloured in Orca: redraw
                    STATE["project_sig"] = sig
                elif time.time() - STATE["spools_time"] > RE_READ_S and self._base():   # printer may have changed: read it again
                    self._refresh()
                else:
                    return
        elif command == "set":
            STATE["choices"][str(int(message.get("index", 0)))] = str(message.get("choice", "auto"))
            save_picks(STATE["spools_base"], STATE["signature"], STATE["choices"])
        elif command == "reset":
            STATE["choices"].clear()
            save_picks(STATE["spools_base"], STATE["signature"], STATE["choices"])
        elif command == "purge":
            save_purge(message.get("values"))
        elif command == "enable":
            STATE["enabled"] = bool(message.get("value"))
        self._push()


class SpoolToolheadMap(orca.slicing.SlicingPipelineCapabilityBase):
    """G-code post-process: write ACE_SET_TOOL_MAP (ACE Pro) or WM_SET_TOOL_MAP (WonderMaker). Never touches orca.host.ui (worker thread)."""

    def get_name(self):
        return "Spool and Toolhead Map"

    def get_default_config(self):
        return {"printer_url": DEFAULT_PRINTER_URL, "timeout_s": DEFAULT_TIMEOUT_S, "live_lookup": True, "printer_kind": "auto"}

    def execute(self, ctx):
        if ctx.step != orca.slicing.Step.psGCodePostProcess:
            return orca.ExecutionResult.success()
        if not ctx.gcode_path:
            return orca.ExecutionResult.success("Spool and Toolhead Map: no G-code path")
        if not STATE["enabled"]:
            return orca.ExecutionResult.success("Spool and Toolhead Map: disabled in the Spools and Toolheads panel")

        cfg = _config(self)
        filaments = project_filaments(
            parse_config_list(ctx.config_value("filament_colour")),
            parse_config_list(ctx.config_value("filament_type")),
            parse_config_list(ctx.config_value("filament_settings_id")))

        with open(ctx.gcode_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        if any(line.startswith(m) for line in lines[:400] for m in KINDS.values()):
            return orca.ExecutionResult.success("Spool and Toolhead Map: already present")
        used = tools_in_gcode(lines) or [0]

        spools, kind = [], ""
        host = pick_host(cfg.get("printer_url", ""), saved_host(ctx.config_value("printer_settings_id")),
                         clean_printer_id(ctx.config_value("print_host")))
        base = moonraker_base(host) or STATE["spools_base"]
        if base and cfg.get("live_lookup", True):
            try:
                # Network access to the printer is granted once when the plugin loads
                # (register_capabilities); without it this call fails and the cached data is used.
                spools, kind = fetch_spools(base, ctx.config_value("printhost_apikey") or "",
                                            float(cfg.get("timeout_s", DEFAULT_TIMEOUT_S)), cfg.get("printer_kind", "auto"))
                STATE.update(spools=spools, spools_base=base, spools_time=time.time(), kind=kind)
            except Exception:  # noqa: BLE001
                spools, kind = [], ""
        if not spools and STATE["spools"] and (not base or STATE["spools_base"] == base):
            spools, kind = STATE["spools"], STATE["kind"]
        if not kind and base and STATE["spools_base"] == base:
            kind = STATE["kind"]
        if kind not in KINDS:
            # Unknown printer: write nothing. A macro the printer does not have would stop the print.
            STATE["last_written"] = "printer not recognised (no ACE Pro, no WonderMaker sensors) - G-code left as sliced"
            return orca.ExecutionResult.success("Spool and Toolhead Map: " + STATE["last_written"])
        name = {"ace": "ACE", "wm": "WonderMaker"}[kind]

        if not STATE["choices"] and not STATE["signature"]:
            restore_picks(base, filaments)
        sig_ok = STATE.get("signature") == _signature(filaments)
        choices = STATE["choices"] if sig_ok else {}
        if not spools and not any(str(c).isdigit() for c in choices.values()):
            STATE["last_written"] = f"no {name} data - printed as sliced"
            ident = ",".join(f"{t}:{t}" for t in range(HEADS)) if kind == "wm" else ""
            new_lines = [
                f"; Spool and Toolhead Mapper: no {name} data (open the Spools and Toolheads panel and Refresh) - as sliced\n",
                f"{KINDS[kind]} MAP={ident}" + (f" FILE={gcode_param(ctx.output_name)}" if ctx.output_name else "")
                + " KEEP_EXISTING=1\n",
            ]
        else:
            mapping = resolve_mapping(filaments, spools, choices, only=set(used))
            for t in used:
                mapping.setdefault(t, t)
            summary = describe(mapping, filaments, spools, kind)
            STATE["last_written"] = f"{ctx.output_name or 'G-code'}: {summary}"
            new_lines = map_lines(mapping, ctx.output_name, summary, kind)

        lines = insert_before_first_command(lines, new_lines)
        purge = load_purge()
        if kind == "ace" and purge["enabled"]:
            try:
                matrix, diameters, fm = purge_inputs(ctx.config_value, len(filaments))
                lines, STATE["last_purge"] = apply_purge(lines, matrix, diameters, fm, purge)
            except Exception as e:  # noqa: BLE001 - never lose the map because of the purge step
                STATE["last_purge"] = f"purge step failed: {e}"
        with open(ctx.gcode_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        extra = f"; purge: {STATE['last_purge']}" if STATE["last_purge"] and kind == "ace" and purge["enabled"] else ""
        return orca.ExecutionResult.success("Spool and Toolhead Map: " + STATE["last_written"] + extra)


@orca.plugin
class SpoolToolheadMapperPlugin(orca.base):
    def register_capabilities(self):
        orca.register_capability(SpoolsPanel)
        orca.register_capability(SpoolToolheadMap)
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

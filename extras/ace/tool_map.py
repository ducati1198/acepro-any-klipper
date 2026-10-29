"""
Per-print tool map for ACE Pro.

Lets the G-code's tool numbers (T0, T1, ... as sliced) be sent to any
physical ACE slot without re-slicing. Fluidd's print-start spool picker sets
the map just before the print starts:

    ACE_SET_TOOL_MAP MAP=0:5,1:2 FILE="benchy.gcode"

Rules:
- The map is only applied while a print is running or paused, and only
  while that print is the file the map was made for (when FILE= is given).
  Outside a print, T<n> and ACE_CHANGE_TOOL always mean the physical slot.
- The map is cleared when the print ends, is cancelled or errors (the
  driver's print-state monitor calls on_print_state_change), at
  _ACE_HANDLE_PRINT_END, and is replaced by the next ACE_SET_TOOL_MAP.
- Only T<n> goes through the map. ACE_CHANGE_TOOL TOOL=<n> always means
  the physical slot (used by RESUME to reload the real spool).
- When endless spool swaps a physical slot for another one, every G-code
  tool that pointed at the old slot is pointed at the new one.
"""

import logging

from .config import SLOTS_PER_ACE

STATE_KEY = "ace_tool_map"
ACTIVE_PRINT_STATES = ("printing", "paused")


def parse_map_string(raw):
    """Parse '0:5,1:2' (also '0=5 1=2') into {0: 5, 1: 2}."""
    mapping = {}
    text = str(raw or "").replace(";", ",").replace(" ", ",")
    for item in text.split(","):
        item = item.strip()
        if not item:
            continue
        sep = ":" if ":" in item else "="
        if sep not in item:
            raise ValueError(f"Bad map entry '{item}' (expected FROM:TO)")
        left, right = item.split(sep, 1)
        src = int(left.strip().lstrip("Tt"))
        dst = int(right.strip().lstrip("Tt"))
        if src < 0 or dst < 0:
            raise ValueError(f"Negative tool in '{item}'")
        mapping[src] = dst
    return mapping


class ToolMap:
    def __init__(self, manager):
        self.manager = manager
        self.printer = manager.printer

    # ---------- storage ----------

    def _load(self):
        raw = self.manager.state.get(STATE_KEY, None)
        if not isinstance(raw, dict):
            return {"file": "", "map": {}}
        tool_map = {}
        for key, value in dict(raw.get("map") or {}).items():
            try:
                tool_map[int(key)] = int(value)
            except (TypeError, ValueError):
                continue
        return {"file": str(raw.get("file") or ""), "map": tool_map}

    def _save(self, file_name, tool_map):
        payload = {
            "file": file_name or "",
            "map": {str(k): int(v) for k, v in sorted(tool_map.items())},
        }
        self.manager.state.set_and_save(STATE_KEY, payload)

    # ---------- print context ----------

    def _print_stats(self):
        print_stats = self.printer.lookup_object("print_stats", None)
        if print_stats is None:
            return {}
        try:
            return print_stats.get_status(self.printer.get_reactor().monotonic())
        except Exception:
            return {}

    @staticmethod
    def _same_file(a, b):
        a = (a or "").strip("/")
        b = (b or "").strip("/")
        return a == b or a.endswith("/" + b) or b.endswith("/" + a)

    def is_active(self):
        data = self._load()
        if not data["map"]:
            return False
        stats = self._print_stats()
        if stats.get("state") not in ACTIVE_PRINT_STATES:
            return False
        if data["file"] and not self._same_file(data["file"], stats.get("filename", "")):
            return False
        return True

    def max_tool(self):
        return max(1, len(getattr(self.manager, "instances", []) or [])) * SLOTS_PER_ACE - 1

    # ---------- public API ----------

    def set(self, tool_map, file_name=""):
        limit = self.max_tool()
        for src, dst in tool_map.items():
            if dst > limit:
                raise ValueError(f"T{src} -> T{dst}: only T0-T{limit} exist")
        cleaned = {src: dst for src, dst in tool_map.items() if src != dst}
        self._save(file_name, cleaned)
        return cleaned

    def clear(self):
        data = self._load()
        if data["map"] or data["file"]:
            self._save("", {})
            return True
        return False

    def has_selection_for(self, file_name):
        """True when a choice (spool map or explicit 'as sliced') was already made for file_name."""
        data = self._load()
        return bool(file_name) and bool(data["file"]) and self._same_file(data["file"], file_name)

    def resolve(self, tool, gcmd=None):
        """Return the physical tool for a G-code tool number."""
        if tool is None or tool < 0 or not self.is_active():
            return tool
        target = self._load()["map"].get(tool, tool)
        if target != tool:
            message = f"ACE: Tool map T{tool} -> T{target}"
            logging.info(message)
            if gcmd is not None:
                gcmd.respond_info(message)
        return target

    def redirect(self, from_tool, to_tool):
        """Endless spool replaced physical from_tool with to_tool."""
        stats = self._print_stats()
        if stats.get("state") not in ACTIVE_PRINT_STATES:
            return
        data = self._load()
        tool_map = dict(data["map"])
        changed = False
        for gcode_tool in range(self.max_tool() + 1):
            if tool_map.get(gcode_tool, gcode_tool) == from_tool:
                tool_map[gcode_tool] = to_tool
                changed = True
        if changed:
            file_name = data["file"] or stats.get("filename", "")
            self._save(file_name, {k: v for k, v in tool_map.items() if k != v})
            logging.info(f"ACE: Tool map redirected T{from_tool} -> T{to_tool}")

    def on_print_state_change(self, old_state, new_state):
        """Clear the map once a print is over (complete, cancelled, error, standby)."""
        if old_state in ACTIVE_PRINT_STATES and new_state not in ACTIVE_PRINT_STATES:
            if self.clear():
                logging.info(f"ACE: Tool map cleared (print {old_state} -> {new_state})")
                return True
        return False

    def status(self):
        data = self._load()
        return {
            "tool_map": {str(k): v for k, v in sorted(data["map"].items())},
            "tool_map_file": data["file"],
            "tool_map_active": self.is_active(),
        }

    def describe(self):
        data = self._load()
        if not data["map"]:
            return "ACE: No tool map set (tools print as sliced)"
        pairs = ", ".join(f"T{k}->T{v}" for k, v in sorted(data["map"].items()))
        where = f" for {data['file']}" if data["file"] else ""
        state = "active" if self.is_active() else "waiting for print"
        return f"ACE: Tool map{where}: {pairs} ({state})"

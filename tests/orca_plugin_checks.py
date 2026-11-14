"""Tests for the pure helpers of orca_plugin/spool_toolhead_mapper.py (WonderMaker and ACE Pro) (OrcaSlicer itself is stubbed).
Run:  python3 -I tests/test_orca_plugin.py"""
import importlib.util, os, sys, types

HERE = os.path.dirname(os.path.abspath(__file__))
orca = types.ModuleType("orca")
class _Base:  # stand-ins for Orca's capability base classes
    pass
orca.script = types.SimpleNamespace(ScriptPluginCapabilityBase=_Base)
orca.slicing = types.SimpleNamespace(SlicingPipelineCapabilityBase=_Base, Step=types.SimpleNamespace(psGCodePostProcess=1))
orca.plugin = lambda c: c
orca.base = object
orca.host = types.SimpleNamespace()
orca.ExecutionResult = types.SimpleNamespace(success=lambda *a: a)
orca.register_capability = lambda c: None
sys.modules["orca"] = orca
spec = importlib.util.spec_from_file_location("stm", os.path.join(HERE, "..", "orca_plugin", "spool_toolhead_mapper.py"))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

PASS = FAIL = 0
def check(desc, cond):
    global PASS, FAIL
    if cond: PASS += 1; print("  ok   ", desc)
    else: FAIL += 1; print("  FAIL ", desc)

INI = "[other]\ncolor0=5\n[slot]\ncolor0=14\nmaterial0=0\ncolor1=4\nmaterial1=3\ncolor2=9\nmaterial2=0\ncolor3=-1\nmaterial3=99\n"
slots = m.parse_tmt1_slots(INI)
check("tmt1 slot colours parsed", [s["color"] for s in slots] == [14, 4, 9, None])
check("out-of-range material ignored", slots[3]["material"] is None and slots[1]["material"] == 3)
check("only the [slot] section is read", slots[0]["color"] == 14)

heads = m.heads_from_data(slots, {0: True, 1: True, 2: False, 3: None})
check("four toolheads", [h["tool"] for h in heads] == [0, 1, 2, 3])
check("empty sensor means not ready", heads[2]["ready"] is False and heads[2]["material"] == "")
check("colour and material from tmt1", heads[0]["colour"] == "#FF1C2E" and heads[0]["material"] == "PLA" and heads[1]["material"] == "PETG")
check("unknown material is not ready", heads[3]["ready"] is False)

fil = m.project_filaments(["#FF0000", "#101010"], ["PLA", "PETG"], ["a", "b"])
auto = m.auto_match(fil, heads)
check("auto: red PLA -> toolhead 0, black PETG -> toolhead 1", auto == {0: 0, 1: 1})
fil2 = m.project_filaments(["#101010", "#FF0000"], ["PETG", "PLA"], ["a", "b"])
check("auto swaps when the slicer order differs", m.auto_match(fil2, heads) == {0: 1, 1: 0})
res = m.resolve_mapping(fil2, heads, {"0": "sliced"})
check("pinned 'as sliced' is kept", res[0] == 0)

lines = m.map_lines({0: 1, 1: 0}, "benchy.gcode", "x", "wm")
check("full map written", lines[1].strip() == "WM_SET_TOOL_MAP MAP=0:1,1:0,2:2,3:3 FILE=benchy.gcode KEEP_EXISTING=1")
check("identity map still written", "MAP=0:0,1:1,2:2,3:3" in m.map_lines({}, "", "s", "wm")[1])
check("file name with spaces is quoted", 'FILE="my part.gcode"' in m.map_lines({}, "my part.gcode", "s", "wm")[1])

g = ["; header\n", "; thumb\n", "M104 S0\n", "T1\n"]
out = m.insert_before_first_command(g, ["X\n"])
check("inserted before the first command", out.index("X\n") == 2)
check("tools found in the G-code", m.tools_in_gcode(["T0\n", "T2 ; x\n", "G1 X1\n"]) == [0, 2])
check("describe names toolheads from 1", m.describe({0: 2}, fil, heads, "wm").startswith("T0->Toolhead 3"))
check("ACE printer: only changed tools, ACE macro", m.map_lines({0: 0, 1: 3}, "f.gcode", "s", "ace")[1].startswith("ACE_SET_TOOL_MAP MAP=1:3 "))
check("printer kind: ace object -> ace", m.detect_kind(["configfile", "ace"]) == "ace")
check("printer kind: filament0..3 sensors -> wm", m.detect_kind(["filament_switch_sensor filament0"]) == "wm")
check("printer kind: WonderMaker with an ACE Pro added is still the four toolheads (wm)", m.detect_kind(["ace", "filament_switch_sensor filament0", "filament_switch_sensor filament3"]) == "wm")
check("printer kind: anything else -> nothing written", m.detect_kind(["configfile"]) == "")

w = m.warnings_for(m.project_filaments(["#FF0000", "#FF0000"], ["PLA", "PLA"], ["a", "b"]), heads, {0: 1, 1: 1}, "wm")
check("warning when two filaments use one toolhead", "also used by filament 2" in w[0][0])
check("warning when the chosen toolhead shows empty", any("shows empty" in x for x in m.warnings_for(fil, heads, {0: 2, 1: 1}, "wm").get(0, [])))
check("no warning for a good match", m.warnings_for(fil, heads, {0: 0, 1: 1}, "wm") == {})

# --- plugin 0.7: printer address per preset, ZR Tools values, forced printer kind ---
import tempfile
check("kind: forcing ace on a printer that has both", m.detect_kind(["ace", "filament_switch_sensor filament0"], "ace") == "ace")
check("kind: forcing wm without sensors is ignored", m.detect_kind(["ace"], "wm") == "ace")
check("address: quote marks removed", m.moonraker_base('"10.11.88.77"') == "http://10.11.88.77")
check("address: port and path kept, slash removed", m.moonraker_base("http://k1:7125/") == "http://k1:7125")
check("address: plugin setting wins, then the one typed in the panel, then Orca's print host",
      m.pick_host("a", "b", "c") == "a" and m.pick_host("", "b", "c") == "b" and m.pick_host("", "", "c") == "c")
tmp = os.path.join(tempfile.mkdtemp(), "s.json")
m.STATE["saved"] = None
m.save_host('"ZR Ultra-S"', "10.11.88.77", tmp); m.save_host("K1", "10.11.88.30", tmp)
m.STATE["saved"] = None
check("address saved per printer preset and read back", m.saved_host("ZR Ultra-S", tmp) == "10.11.88.77" and m.saved_host("K1", tmp) == "10.11.88.30")
m.save_host("K1", "", tmp)
check("empty address forgets it", m.saved_host("K1", tmp) == "")
zr_slots = m.parse_tmt1_slots("[slot]\ncolor0=0\nmaterial0=2\ncolor1=4\nmaterial1=19\ncolor2=7\nmaterial2=0\ncolor3=14\nmaterial3=0\n")
zr = m.heads_from_data(zr_slots, {0: True, 1: True, 2: False, 3: None}, None, {"zr_t0_mat": 11, "zr_t0_temp": 250})
check("ZR Tools material (zr_tN_mat) wins over tmt1.ini", zr[0]["material"] == "PA / Nylon" and zr[0]["temp"] == 250)
check("tmt1.ini material beyond the first 16 is known", zr[1]["material"] == "PA")
check("tmt1.ini colour is kept", zr[0]["colour"] == "#FFFFFF" and zr[3]["colour"] == "#FF1C2E")
only_vars = m.heads_from_data(m.parse_tmt1_slots(""), {}, None, {"zr_t2_color": 16711680, "zr_t2_mat": 6})
check("colour and material from saved variables when tmt1.ini has none", only_vars[2]["colour"] == "#FF0000" and only_vars[2]["material"] == "PETG")
check("Empty on the ZR Tools screen means not ready", not m.heads_from_data(zr_slots, {}, None, {"zr_t3_mat": 0})[3]["ready"])

print(f"\npassed: {PASS}  failed: {FAIL}")
sys.exit(1 if FAIL else 0)

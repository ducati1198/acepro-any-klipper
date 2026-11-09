import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "extras"))
from ace import setup_tools as st  # noqa: E402

CFG = """[gcode_macro _ACE_VARS]
variable_cut_full_x: 33 #34             # end of the cut
variable_cut_full_y:304 #303
variable_poop_x: 180.5
variable_positions_confirmed: False
gcode:
    M117 x

[gcode_macro OTHER]
variable_poop_x: 1
"""


def test_replaces_value_and_keeps_comments():
    out = st.set_variables_in_text(CFG, {"cut_full_x": "30.5", "cut_full_y": "299"})
    assert "variable_cut_full_x: 30.5 #34             # end of the cut" in out
    assert "variable_cut_full_y:299 #303" in out


def test_only_touches_ace_vars_section():
    out = st.set_variables_in_text(CFG, {"poop_x": "200"})
    assert "variable_poop_x: 200" in out
    assert "[gcode_macro OTHER]\nvariable_poop_x: 1" in out


def test_unknown_variable_raises():
    try:
        st.set_variables_in_text(CFG, {"nope": "1"})
    except KeyError as exc:
        assert "nope" in str(exc)
    else:
        raise AssertionError("expected KeyError")


def test_confirm():
    assert "variable_positions_confirmed: True" in st.set_variables_in_text(CFG, {"positions_confirmed": "True"})


def test_fmt():
    assert st.fmt(33.0) == "33"
    assert st.fmt(180.499) == "180.5"
    assert st.fmt(12.345) == "12.35" or st.fmt(12.345) == "12.34"


class Gcmd:
    class error(Exception):
        pass

    def __init__(self, **p):
        self.p, self.out = p, []

    def get(self, k, d=None):
        return self.p.get(k, d)

    def respond_info(self, m):
        self.out.append(m)


class FakePrinter:
    def __init__(self, cfgdir, pos=(12.3456, 301.0, 0), homed="xy"):
        self.cfgdir, self.pos, self.homed, self.ran = cfgdir, pos, homed, []
        me = self

        class TH:
            def get_status(self, t):
                return {"homed_axes": me.homed}

            def get_position(self):
                return list(me.pos)

        class GC:
            def run_script_from_command(self, s):
                me.ran.append(s)

        class R:
            def monotonic(self):
                return 0

        self.objs = {"toolhead": TH(), "gcode": GC(), "reactor": R()}

    def get_start_args(self):
        return {"config_file": os.path.join(self.cfgdir, "printer.cfg")}

    def lookup_object(self, name, default=None):
        return self.objs.get(name, default)

    def get_reactor(self):
        return self.objs["reactor"]


def commands(tmp_path, **kw):
    (tmp_path / "acepro_macros.cfg").write_text(CFG)
    pr = FakePrinter(str(tmp_path), **kw)
    return pr, {n: h for n, h, _ in st.make_commands(lambda: pr)}


def test_save_writes_file_and_updates_macro(tmp_path):
    pr, cmds = commands(tmp_path)
    cmds["ACE_SETUP_SAVE"](Gcmd(POINT="cut_full"))
    text = (tmp_path / "acepro_macros.cfg").read_text()
    assert "variable_cut_full_x: 12.35" in text or "variable_cut_full_x: 12.34" in text
    assert "variable_cut_full_y:301 #303" in text
    assert (tmp_path / "acepro_macros.cfg.before-setup").read_text() == CFG
    assert any("VARIABLE=cut_full_x" in r for r in pr.ran)


def test_save_needs_homing(tmp_path):
    pr, cmds = commands(tmp_path, homed="")
    try:
        cmds["ACE_SETUP_SAVE"](Gcmd(POINT="poop"))
    except Gcmd.error as exc:
        assert "home" in str(exc)
    else:
        raise AssertionError("expected an error")
    assert (tmp_path / "acepro_macros.cfg").read_text() == CFG


def test_confirm(tmp_path):
    pr, cmds = commands(tmp_path)
    cmds["ACE_SETUP_CONFIRM"](Gcmd())
    assert "variable_positions_confirmed: True" in (tmp_path / "acepro_macros.cfg").read_text()


def test_selftest_reports_and_changes_nothing(tmp_path):
    from ace.config import ACE_INSTANCES
    pr, cmds = commands(tmp_path)

    class Serial:
        def __init__(self, ok):
            self.ok = ok

        def get_connection_status(self):
            return {"connected": self.ok, "port": "/dev/ttyACM0"}

    class Obj:
        def __init__(self, st=None, variables=None):
            self.st, self.variables = st or {}, variables or {}

        def get_status(self, t):
            return self.st

    ACE_INSTANCES.clear()
    ACE_INSTANCES[0] = types.SimpleNamespace(serial_mgr=Serial(True))
    ACE_INSTANCES[1] = types.SimpleNamespace(serial_mgr=Serial(False))
    pr.objs["temperature_sensor acepro_temp_1"] = Obj({"temperature": 31.5})
    pr.objs["filament_switch_sensor filament_runout_nozzle"] = Obj({"filament_detected": True})
    pr.objs["gcode_macro _ACE_VARS"] = Obj(variables={"positions_confirmed": False})
    pr.objs["output_pin ACE_Pro"] = Obj({"value": 1})
    g = Gcmd()
    try:
        cmds["ACE_SELFTEST"](g)
    finally:
        ACE_INSTANCES.clear()
    text = g.out[0]
    assert "PASS  ACE[0] connected" in text
    assert "FAIL  ACE[1] is not connected" in text
    assert "WARN  no temperature sensor acepro_temp_2" in text
    assert "WARN  positions not confirmed" in text
    assert "switch ACE_Pro is ON" in text
    assert "Nothing was changed" in text
    assert pr.ran == []
    assert (tmp_path / "acepro_macros.cfg").read_text() == CFG


def test_selftest_uses_configured_sensor_names(tmp_path):
    from ace.config import ACE_INSTANCES
    pr, cmds = commands(tmp_path)

    class Serial:
        def get_connection_status(self):
            return {"connected": True, "port": "x"}

    class Obj:
        def __init__(self, st=None, variables=None):
            self.st, self.variables = st or {}, variables or {}

        def get_status(self, t):
            return self.st

    ACE_INSTANCES.clear()
    ACE_INSTANCES[0] = types.SimpleNamespace(
        serial_mgr=Serial(), filament_runout_sensor_name_nozzle="my_nozzle",
        filament_runout_sensor_name_rdm="my_rdm")
    pr.objs["filament_switch_sensor my_nozzle"] = Obj({"filament_detected": False})
    pr.objs["filament_switch_sensor my_rdm"] = Obj({"filament_detected": True})
    g = Gcmd()
    try:
        cmds["ACE_SELFTEST"](g)
    finally:
        ACE_INSTANCES.clear()
    text = g.out[0]
    assert "PASS  toolhead sensor present (filament not detected)" in text
    assert "PASS  RDM sensor present" in text
    assert "FAIL  no toolhead filament sensor" not in text

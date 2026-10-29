"""Per-print tool map (ACE_SET_TOOL_MAP) - local addition for the Fluidd spool
picker and the OrcaSlicer ACE Spool Mapper plugin."""
import unittest
from unittest.mock import Mock, patch

import ace.commands
from ace.config import ACE_INSTANCES, INSTANCE_MANAGERS
from ace.manager import AceManager
from ace.tool_map import ToolMap, parse_map_string


class FakeState:
    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set_and_save(self, key, value):
        self.data[key] = value


class FakeManager:
    def __init__(self, state="printing", filename="benchy.gcode", instances=2):
        self.state = FakeState()
        self.instances = [object()] * instances
        self.print_stats = {"state": state, "filename": filename}
        self.printer = Mock()
        stats = Mock()
        stats.get_status = Mock(side_effect=lambda t: dict(self.print_stats))
        self.printer.lookup_object = Mock(
            side_effect=lambda name, default=None: stats if name == "print_stats" else default)
        self.printer.get_reactor = Mock(return_value=Mock(monotonic=Mock(return_value=1.0)))


class TestParse(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(parse_map_string("0:5,1:2"), {0: 5, 1: 2})
        self.assertEqual(parse_map_string("T0=T5 T1=T2"), {0: 5, 1: 2})
        self.assertEqual(parse_map_string(""), {})

    def test_bad(self):
        with self.assertRaises(ValueError):
            parse_map_string("0-5")


class TestToolMap(unittest.TestCase):
    def test_resolve_only_for_matching_running_print(self):
        m = FakeManager()
        tm = ToolMap(m)
        tm.set({0: 5, 1: 1}, "benchy.gcode")
        self.assertEqual(tm.resolve(0), 5)
        self.assertEqual(tm.resolve(1), 1)
        self.assertEqual(tm.resolve(3), 3)
        m.print_stats["filename"] = "other.gcode"
        self.assertEqual(tm.resolve(0), 0)
        m.print_stats.update(state="standby", filename="benchy.gcode")
        self.assertEqual(tm.resolve(0), 0)

    def test_subfolder_file_matches(self):
        m = FakeManager(filename="parts/benchy.gcode")
        tm = ToolMap(m)
        tm.set({0: 4}, "parts/benchy.gcode")
        self.assertEqual(tm.resolve(0), 4)

    def test_rejects_missing_slot(self):
        tm = ToolMap(FakeManager(instances=1))
        with self.assertRaises(ValueError):
            tm.set({0: 4}, "x.gcode")

    def test_clears_when_print_ends(self):
        m = FakeManager()
        tm = ToolMap(m)
        tm.set({0: 5}, "benchy.gcode")
        self.assertFalse(tm.on_print_state_change("printing", "paused"))
        self.assertTrue(tm.on_print_state_change("paused", "cancelled"))
        self.assertEqual(tm.status()["tool_map"], {})
        self.assertEqual(tm.status()["tool_map_file"], "")

    def test_keep_existing_selection(self):
        tm = ToolMap(FakeManager())
        self.assertFalse(tm.has_selection_for("benchy.gcode"))
        tm.set({}, "benchy.gcode")          # "as sliced" chosen in Fluidd
        self.assertTrue(tm.has_selection_for("benchy.gcode"))
        self.assertFalse(tm.has_selection_for("other.gcode"))

    def test_endless_spool_redirect(self):
        m = FakeManager()
        tm = ToolMap(m)
        tm.set({0: 5}, "benchy.gcode")
        tm.redirect(5, 6)                   # slot 5 ran out, endless spool took 6
        tm.redirect(2, 3)                   # unmapped tool 2 now prints from 3
        self.assertEqual(tm.resolve(0), 6)
        self.assertEqual(tm.resolve(2), 3)


class TestCommands(unittest.TestCase):
    def setUp(self):
        self.manager = Mock()
        self.manager.tool_map = ToolMap(FakeManager())
        INSTANCE_MANAGERS[0] = self.manager
        self.gcmd = Mock()
        self.gcmd.error = Mock(side_effect=lambda msg: Exception(msg))

    def tearDown(self):
        INSTANCE_MANAGERS.clear()
        ACE_INSTANCES.clear()

    def _params(self, **p):
        self.gcmd.get = Mock(side_effect=lambda k, d=None: p.get(k, d))
        self.gcmd.get_int = Mock(side_effect=lambda k, d=None: int(p.get(k, d)))

    def test_set_get_clear(self):
        self._params(MAP="0:5", FILE="benchy.gcode")
        ace.commands.cmd_ACE_SET_TOOL_MAP(self.gcmd)
        self.assertEqual(self.manager.tool_map.resolve(0), 5)
        ace.commands.cmd_ACE_CLEAR_TOOL_MAP(self.gcmd)
        self.assertEqual(self.manager.tool_map.resolve(0), 0)

    def test_keep_existing_does_not_override_fluidd_choice(self):
        self._params(MAP="0:1", FILE="benchy.gcode")
        ace.commands.cmd_ACE_SET_TOOL_MAP(self.gcmd)          # Fluidd picker
        self._params(MAP="0:7", FILE="benchy.gcode", KEEP_EXISTING=1)
        ace.commands.cmd_ACE_SET_TOOL_MAP(self.gcmd)          # line from Orca
        self.assertEqual(self.manager.tool_map.resolve(0), 1)

    def test_bad_map_is_a_gcode_error(self):
        self._params(MAP="0:99", FILE="benchy.gcode")
        with self.assertRaises(Exception):
            ace.commands.cmd_ACE_SET_TOOL_MAP(self.gcmd)

    def test_commands_registered(self):
        names = [c[0] for c in ace.commands.ACE_COMMANDS]
        for name in ("ACE_SET_TOOL_MAP", "ACE_CLEAR_TOOL_MAP", "ACE_GET_TOOL_MAP"):
            self.assertIn(name, names)


class TestSetSlotPresetName(unittest.TestCase):
    def tearDown(self):
        INSTANCE_MANAGERS.clear()
        ACE_INSTANCES.clear()

    def test_filament_settings_id_saved(self):
        inst = Mock()
        inst.SLOT_COUNT = 4
        inst.instance_num = 0
        inst.inventory = [{} for _ in range(4)]
        ACE_INSTANCES[0] = inst
        INSTANCE_MANAGERS[0] = Mock()
        gcmd = Mock()
        params = {"INSTANCE": "0", "INDEX": "1", "COLOR": "255,0,0", "MATERIAL": "PLA",
                  "TEMP": "210", "FILAMENT_SETTINGS_ID": "Bambu PLA Matte"}
        gcmd.get_command_parameters = Mock(return_value=params)
        gcmd.get = Mock(side_effect=lambda k, d=None: params.get(k, d))
        gcmd.get_int = Mock(side_effect=lambda k, d=None: int(params.get(k, d)) if params.get(k, d) is not None else None)
        gcmd.error = Mock(side_effect=lambda msg: Exception(msg))
        with patch("ace.commands.ace_get_instance_and_slot", return_value=(inst, 1)):
            ace.commands.cmd_ACE_SET_SLOT(gcmd)
        self.assertEqual(inst.inventory[1]["custom_name"], "Bambu PLA Matte")
        self.assertEqual(inst.inventory[1]["material"], "PLA")


class TestManagerTMacro(unittest.TestCase):
    """The auto-registered T<n> commands go through the tool map."""

    def test_t_macro_uses_tool_map(self):
        printer = Mock()
        gcode = Mock()
        registered = {}
        gcode.register_command = Mock(side_effect=lambda name, fn, desc=None: registered.__setitem__(name, fn))
        save_vars = Mock()
        save_vars.allVariables = {"ace_global_enabled": True}

        def lookup(name, *a):
            if name == "gcode":
                return gcode
            if name == "save_variables":
                return save_vars
            if name.startswith("gcode_macro T"):
                return None
            return Mock()
        printer.lookup_object = Mock(side_effect=lookup)
        config = Mock()
        config.get_printer = Mock(return_value=printer)
        ace_config = {
            "ace_count": 1, "baud": 115200, "toolhead_retraction_speed": 10.0,
            "toolhead_retraction_length": 50.0, "runout_reload_length": 0.0,
            "default_color_change_purge_length": 100.0, "default_color_change_purge_speed": 400.0,
            "purge_max_chunk_length": 50.0, "pre_cut_retract_length": 2.0,
            "ace_connection_supervision": True, "register_tool_macros": True,
        }

        def make_instance(*a, **k):
            inst = Mock()
            inst.instance_num = 0
            inst.tool_offset = 0
            inst.SLOT_COUNT = 4
            inst.inventory = [{"status": "empty"} for _ in range(4)]
            return inst

        with patch("ace.manager.AceInstance", side_effect=make_instance), \
             patch("ace.manager.EndlessSpool"), patch("ace.manager.RunoutMonitor"), \
             patch("ace.manager.read_ace_config", return_value=ace_config):
            manager = AceManager(config, dummy_ace_count=1)
        self.assertIsInstance(manager.tool_map, ToolMap)
        manager.register_tool_macros(0)
        self.assertIn("T0", registered)
        manager.tool_map.resolve = Mock(return_value=3)
        with patch("ace.commands.cmd_ACE_CHANGE_TOOL") as change:
            registered["T0"](Mock())
        self.assertEqual(change.call_args[0][2], 3)
        status = manager.get_status(0)
        self.assertIn("tool_map", status)
        self.assertIn("tool_map_active", status)


if __name__ == "__main__":
    unittest.main()

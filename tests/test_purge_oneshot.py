"""ACE_SET_PURGE_AMOUNT is one-shot: it arms purge_override_pending; the manager
restores the config defaults after the tool change that used it."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import ace.commands


def fake_manager():
    return SimpleNamespace(
        default_color_change_purge_length=50.0, default_color_change_purge_speed=300.0,
        toolchange_purge_length=50.0, toolchange_purge_speed=300.0,
        purge_override_pending=False)


class PurgeOneShot(unittest.TestCase):
    def test_command_arms_override(self):
        m = fake_manager()
        gcmd = Mock()
        gcmd.get_float = Mock(side_effect=lambda k, d=None: {"PURGELENGTH": 80.0}.get(k, d))
        gcmd.get_int = Mock(return_value=0)
        with patch("ace.commands.ace_get_manager", return_value=m):
            ace.commands.cmd_ACE_SET_PURGE_AMOUNT(gcmd)
        self.assertEqual(m.toolchange_purge_length, 80.0)
        self.assertEqual(m.toolchange_purge_speed, 300.0)
        self.assertTrue(m.purge_override_pending)

    def test_manager_source_restores_defaults(self):
        import inspect
        import ace.manager as mgr
        src = inspect.getsource(mgr.AceManager)
        self.assertIn("self.purge_override_pending = False", src)
        i = src.index("if self.purge_override_pending:")
        self.assertIn("default_color_change_purge_length", src[i:i + 300])


if __name__ == "__main__":
    unittest.main()

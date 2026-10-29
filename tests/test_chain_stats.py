"""Endless spool chains and usage counters - local additions for the Fluidd panel."""
import unittest
from unittest.mock import Mock

import ace.commands as commands
from ace.config import ACE_INSTANCES, INSTANCE_MANAGERS, SLOTS_PER_ACE
from ace.endless_spool import EndlessSpool
from ace.manager import AceManager


class FakeState:
    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value

    def set_and_save(self, key, value):
        self.data[key] = value


def make_spool():
    manager = Mock()
    manager.state = FakeState()
    reactor = Mock()
    printer = Mock()
    printer.get_reactor = Mock(return_value=reactor)
    es = EndlessSpool(printer, Mock(), manager)
    manager.endless_spool = es
    ACE_INSTANCES.clear()
    for i in range(2):
        inst = Mock()
        inst.instance_num = i
        inst.tool_offset = i * SLOTS_PER_ACE
        inst.SLOT_COUNT = SLOTS_PER_ACE
        inst.inventory = [{"material": "PLA", "color": [1, 2, 3], "status": "ready"}
                          for _ in range(SLOTS_PER_ACE)]
        ACE_INSTANCES[i] = inst
    return manager, es


class TestChains(unittest.TestCase):
    def tearDown(self):
        ACE_INSTANCES.clear()

    def test_set_get_and_clean(self):
        _, es = make_spool()
        self.assertEqual(es.set_chain(0, [4, 4, 0, 5, -1]), [4, 5])
        self.assertEqual(es.get_chains(), {0: [4, 5]})

    def test_empty_next_removes(self):
        _, es = make_spool()
        es.set_chain(0, [4])
        es.set_chain(0, [])
        self.assertEqual(es.get_chains(), {})

    def test_clear_one_and_all(self):
        _, es = make_spool()
        es.set_chain(0, [4])
        es.set_chain(1, [5])
        es.clear_chains(0)
        self.assertEqual(es.get_chains(), {1: [5]})
        es.clear_chains()
        self.assertEqual(es.get_chains(), {})

    def test_garbage_in_storage_is_ignored(self):
        manager, es = make_spool()
        manager.state.data["ace_endless_chain"] = {"x": [1], "2": "no", "3": ["a", 4, 3]}
        self.assertEqual(es.get_chains(), {3: [4]})

    def test_chain_wins_over_match_mode(self):
        manager, es = make_spool()
        manager.state.data["ace_endless_spool_match_mode"] = "exact"
        # T1 would match first by order; the chain says T6
        es.set_chain(0, [6])
        self.assertEqual(es.find_exact_match(0), 6)

    def test_chain_skips_not_ready_then_next(self):
        _, es = make_spool()
        ACE_INSTANCES[1].inventory[0]["status"] = "empty"      # T4
        es.set_chain(0, [4, 5])
        self.assertEqual(es.find_exact_match(0), 5)

    def test_chain_all_unavailable_falls_back_to_mode(self):
        manager, es = make_spool()
        manager.state.data["ace_endless_spool_match_mode"] = "next"
        ACE_INSTANCES[1].inventory[0]["status"] = "empty"
        es.set_chain(0, [4])
        self.assertEqual(es.find_exact_match(0), 1)             # next ready slot

    def test_no_chain_behaves_as_before(self):
        _, es = make_spool()
        self.assertEqual(es.find_exact_match(0), 1)


class TestStats(unittest.TestCase):
    def make(self):
        m = AceManager.__new__(AceManager)
        m.state = FakeState()
        return m

    def test_record_and_status(self):
        m = self.make()
        m.record_stat("cuts")
        m.record_stat("cuts")
        m.record_stat("tool_changes")
        m.record_stat("purge_mm", 50.25)
        m.record_stat("purge_mm", 50.25)
        self.assertEqual(m.stats_status(), {"tool_changes": 1, "purge_mm": 100.5, "cuts": 2})

    def test_unknown_counter_ignored(self):
        m = self.make()
        m.record_stat("nope", 5)
        self.assertEqual(m.stats_status(), {"tool_changes": 0, "purge_mm": 0, "cuts": 0})

    def test_reset_command(self):
        m = self.make()
        m.record_stat("cuts", 3)
        m.record_stat("tool_changes", 2)
        gcmd = Mock()
        gcmd.get = Mock(side_effect=lambda k, d=None: "cuts" if k == "WHAT" else d)
        INSTANCE_MANAGERS.clear()
        INSTANCE_MANAGERS[0] = m
        try:
            commands.cmd_ACE_RESET_STATS(gcmd)
        finally:
            INSTANCE_MANAGERS.clear()
        self.assertEqual(m.stats_status()["cuts"], 0)
        self.assertEqual(m.stats_status()["tool_changes"], 2)


class TestChainCommands(unittest.TestCase):
    def test_set_command(self):
        manager, es = make_spool()
        gcmd = Mock()
        gcmd.get_int = Mock(return_value=0)
        gcmd.get = Mock(return_value="T4, 5")
        INSTANCE_MANAGERS.clear()
        INSTANCE_MANAGERS[0] = manager
        try:
            commands.cmd_ACE_SET_ENDLESS_CHAIN(gcmd)
        finally:
            INSTANCE_MANAGERS.clear()
            ACE_INSTANCES.clear()
        self.assertEqual(es.get_chains(), {0: [4, 5]})


if __name__ == "__main__":
    unittest.main()

"""Runs the checks of the OrcaSlicer plugin (orca_plugin/spool_toolhead_mapper.py) with Orca itself stubbed."""
import os
import subprocess
import sys
import unittest


class OrcaPluginChecks(unittest.TestCase):
    def test_plugin_helpers(self):
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "orca_plugin_checks.py")
        run = subprocess.run([sys.executable, "-I", script], capture_output=True, text=True, timeout=120)
        self.assertEqual(run.returncode, 0, run.stdout[-2000:] + run.stderr[-2000:])


if __name__ == "__main__":
    unittest.main()

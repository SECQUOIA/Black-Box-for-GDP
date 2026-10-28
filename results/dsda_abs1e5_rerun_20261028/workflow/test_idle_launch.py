"""Validate fresh sealed CPU selection and refusal of unsafe stale selection."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run
import select_dsda_cpu


class IdleAllocationTests(unittest.TestCase):
    def record(self, directory, age=0):
        path = directory / "CPU_SELECTION.json"
        value = dict(
            selected_cpu=1,
            physical_core_observed_idle=True,
            rounds=[
                dict(
                    utc=(
                        datetime.now(timezone.utc) - timedelta(seconds=age)
                    ).isoformat()
                )
            ],
        )
        path.write_text(json.dumps(value))
        (directory / "SHA256SUMS.json").write_text(
            json.dumps({path.name: run.sha(path)})
        )
        return path

    def test_fresh_sealed_selection_is_used(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = self.record(root)
            with (
                patch.object(run, "ROOT", root),
                patch.dict(run.os.environ, {"DSDA_CPU_SELECTION_RECORD": str(path)}),
                patch.object(
                    run.os, "sched_getaffinity", return_value={1}, create=True
                ),
                patch.object(run.os, "sched_setaffinity", create=True) as pin,
            ):
                result = run.allocate_idle_cpu()
            pin.assert_called_once_with(0, {1})
            self.assertEqual(result["effective_cpus"], [1])
            self.assertEqual(
                result["execution_mode"], "observed_idle_physical_core_then_pinned"
            )
            self.assertFalse(result["exclusive_reservation"])

    def test_stale_observation_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = self.record(root, age=120)
            with (
                patch.object(run, "ROOT", root),
                patch.dict(run.os.environ, {"DSDA_CPU_SELECTION_RECORD": str(path)}),
                self.assertRaisesRegex(RuntimeError, "stale"),
            ):
                run.allocate_idle_cpu()

    def test_idle_smt_on_busy_core_is_rejected(self):
        value = dict(selected_cpu=2, physical_core_observed_idle=False)
        with (
            patch.dict(run.os.environ, {"DSDA_CPU_SELECTION_RECORD": ""}),
            patch.object(select_dsda_cpu, "select", return_value=value),
            self.assertRaisesRegex(RuntimeError, "fully idle physical core"),
        ):
            run.allocate_idle_cpu()


if __name__ == "__main__":
    unittest.main(verbosity=2)

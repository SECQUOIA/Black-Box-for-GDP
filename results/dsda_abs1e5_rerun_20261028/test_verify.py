"""Exercise repeat-audit exclusions against actual records and changed evidence."""

from copy import deepcopy
import json
import unittest
from zipfile import ZipFile

import verify


class RepeatAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with ZipFile(verify.ARCHIVE) as new, ZipFile(verify.PREVIOUS_ARCHIVE) as old:
            jobs = json.loads(new.read(verify.PREFIX + "reproduction/inputs/jobs.json"))
            job = next(j for j in jobs if j["spec"]["scope"] == "grid")
            name = "runs/" + job["spec"]["job_id"] + "/"
            cls.result = json.loads(new.read(verify.PREFIX + name + "result.json"))
            cls.previous = json.loads(
                old.read(verify.PREVIOUS_PREFIX + name + "result.json")
            )
            cls.events = [
                json.loads(line)
                for line in new.read(
                    verify.PREFIX + name + "callbacks.jsonl"
                ).splitlines()
            ]
            cls.previous_events = [
                json.loads(line)
                for line in old.read(
                    verify.PREVIOUS_PREFIX + name + "callbacks.jsonl"
                ).splitlines()
            ]

    def test_real_repeat_accepts_only_timing_and_affinity_changes(self):
        row = verify.compare_repeat(
            self.previous, self.result, self.previous_events, self.events
        )
        self.assertTrue(row["objective_and_outcome_identical"])

    def test_changed_nested_algorithm_objective_is_rejected(self):
        changed = deepcopy(self.result)
        changed["algorithm_result"]["result_record"]["best_value"] = -123456789
        with self.assertRaisesRegex(ValueError, "search result differs"):
            verify.compare_repeat(
                self.previous, changed, self.previous_events, self.events
            )

    def test_changed_movement_path_is_rejected(self):
        changed = deepcopy(self.result)
        changed["path"].append([999, 999])
        with self.assertRaisesRegex(ValueError, "search result differs"):
            verify.compare_repeat(
                self.previous, changed, self.previous_events, self.events
            )

    def test_missing_objective_timing_entry_is_rejected(self):
        changed = deepcopy(self.result)
        changed["algorithm_result"]["objective_wall_times"].pop()
        with self.assertRaisesRegex(ValueError, "search result differs"):
            verify.compare_repeat(
                self.previous, changed, self.previous_events, self.events
            )

    def test_changed_callback_response_is_rejected(self):
        changed = deepcopy(self.events)
        changed[0]["raw_objective"] = -123456789
        with self.assertRaisesRegex(ValueError, "callback responses or paths differ"):
            verify.compare_repeat(
                self.previous, self.result, self.previous_events, changed
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Shared execution stays on one allowed CPU without an occupancy gate."""

import unittest
from unittest.mock import patch

import run


class SharedCPUTests(unittest.TestCase):
    def test_cpu_two_preferred_even_when_all_cpus_are_shared(self):
        with (
            patch.object(
                run.os,
                "sched_getaffinity",
                side_effect=[set(range(48)), {2}],
                create=True,
            ),
            patch.object(run.os, "sched_setaffinity", create=True) as pin,
        ):
            result = run.pin_shared_cpu()
        pin.assert_called_once_with(0, {2})
        self.assertEqual(result["effective_cpus"], [2])
        self.assertFalse(result["requires_idle_cpu"])
        self.assertEqual(result["occupancy_wait_seconds"], 0)

    def test_fallback_respects_allowed_cpus(self):
        with (
            patch.object(
                run.os, "sched_getaffinity", side_effect=[{17, 9}, {9}], create=True
            ),
            patch.object(run.os, "sched_setaffinity", create=True) as pin,
        ):
            result = run.pin_shared_cpu()
        pin.assert_called_once_with(0, {9})
        self.assertEqual(result["cpu"], 9)

    def test_affinity_failure_is_not_silently_ignored(self):
        with (
            patch.object(
                run.os, "sched_getaffinity", side_effect=[{2, 3}, {2, 3}], create=True
            ),
            patch.object(run.os, "sched_setaffinity", create=True),
            self.assertRaisesRegex(RuntimeError, "exactly one CPU"),
        ):
            run.pin_shared_cpu()

    def test_threads_remain_one(self):
        for name in (
            "OMP_NUM_THREADS",
            "OMP_THREAD_LIMIT",
            "OPENBLAS_NUM_THREADS",
            "MKL_NUM_THREADS",
            "BLIS_NUM_THREADS",
            "NUMEXPR_NUM_THREADS",
            "VECLIB_MAXIMUM_THREADS",
            "GOTO_NUM_THREADS",
            "NUMEXPR_MAX_THREADS",
        ):
            self.assertEqual(run.THREADS[name], "1")


if __name__ == "__main__":
    unittest.main(verbosity=2)

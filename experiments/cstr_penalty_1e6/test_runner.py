"""Protocol checks; no optimizers or auxiliary/NLP solvers are started."""
import copy
import json
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import runner
core = runner.core
ROOT = runner.ROOT


class ProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = core.read(ROOT / 'plan.json')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)

    def oracle(self, spec, table):
        self.path.joinpath('callbacks.jsonl').unlink(missing_ok=True)
        return core.Oracle(spec, table, self.path)

    def test_120_slots_inputs_and_penalty_range(self):
        self.assertEqual(runner.check(ROOT)['planned_runs'], 120)

    def test_all_lookup_responses_and_original_acceptance(self):
        for case in core.CASES:
            table, _ = runner.lookup_table(ROOT, case)
            for method in ('dsda', 'rbfopt'):
                spec = copy.deepcopy(next(j['spec'] for j in self.plan if j['spec']['case'] == case and j['spec']['method'] == method))
                spec['budget'] = 10000
                # Preserve the first-three callback contract for arbitrary test points.
                for point, row in table.items():
                    spec['starts'] = [list(point)] * 3
                    oracle = self.oracle(spec, table)
                    value = oracle(point)
                    accepted = row['accepted'] == 'True'
                    self.assertEqual(oracle.events[0]['accepted'], accepted)
                    self.assertEqual(value, float(row['objective']) if accepted else 1e6)
                    self.assertEqual(oracle.events[0]['penalty_applied'], not accepted)
                    self.assertEqual(oracle.events[0]['source_row'], row)

    def test_no_override_and_explicit_infinity_preserved(self):
        spec = copy.deepcopy(self.plan[0]['spec'])
        table, _ = runner.lookup_table(ROOT, spec['case'])
        for policy in (None, '+inf'):
            spec.pop('unaccepted_response', None)
            if policy:
                spec['unaccepted_response'] = policy
            oracle = self.oracle(spec, table)
            self.assertTrue(math.isinf(oracle(spec['starts'][0])))
            self.assertFalse(oracle.events[0]['accepted'])

    def test_ordered_starts_all_120_jobs(self):
        designs = {}
        for job in self.plan:
            spec = job['spec']
            table, _ = runner.lookup_table(ROOT, spec['case'])
            oracle = self.oracle(spec, table)
            for point in spec['starts']:
                oracle(point)
            baseline = core.jsonl(ROOT / 'baseline' / spec['job_id'] / 'callbacks.jsonl')
            self.assertEqual([e['point'] for e in oracle.events], [e['point'] for e in baseline[:3]])
            key = spec['case'], spec['seed']
            self.assertEqual(designs.setdefault(key, spec['starts']), spec['starts'])
        self.assertEqual(len(designs), 60)

    def test_terminal_observation_and_no_budget_overcharge(self):
        spec = copy.deepcopy(self.plan[0]['spec'])
        table, _ = runner.lookup_table(ROOT, spec['case'])
        spec['starts'] = [[1, 2], [1, 3], [1, 4]]
        oracle = self.oracle(spec, table)
        for p in spec['starts'] + [[1, 2]] * (spec['budget'] - 4):
            self.assertEqual(oracle(p), 1e6)
        with self.assertRaises(core.BudgetStop):
            oracle([5, 5])
        result, _ = runner.metrics(ROOT, spec, oracle.events, {'status': 'budget_completed', 'dfo_wall_s': 1})
        self.assertTrue(result['target_hit'])
        self.assertEqual(result['first_target_evaluation'], spec['budget'])
        self.assertEqual(result['best_point'], [5, 5])
        self.assertFalse(oracle.events[-1]['value_returned_to_optimizer'])
        with self.assertRaises(ValueError):
            oracle([5, 5])
        result, _ = runner.metrics(ROOT, spec, oracle.events, {'status': 'execution_failed', 'dfo_wall_s': 1})
        self.assertEqual(result['charged_evaluations'], spec['budget'])
        self.assertFalse(result['target_hit'])
        self.assertTrue(result['target_observed_even_if_failed'])

    def test_finite_penalties_do_not_make_an_incumbent(self):
        spec = copy.deepcopy(self.plan[0]['spec'])
        spec['starts'] = [[1, 2], [1, 3], [1, 4]]
        table, _ = runner.lookup_table(ROOT, spec['case'])
        oracle = self.oracle(spec, table)
        for p in spec['starts']:
            oracle(p)
        result, _ = runner.metrics(ROOT, spec, oracle.events, {'status': 'completed', 'dfo_wall_s': 1})
        self.assertIsNone(result['best_accepted_objective'])
        self.assertIsNone(result['best_point'])
        self.assertFalse(result['target_hit'])
        self.assertLess(result['target'], 1e6)

    def test_missing_and_invalid_are_errors_not_penalties(self):
        spec = copy.deepcopy(self.plan[0]['spec'])
        spec['starts'] = [[5, 5]] * 3
        oracle = self.oracle(spec, {})
        with self.assertRaises(core.MissingEvaluation):
            oracle([5, 5])
        self.assertFalse(oracle.events[-1]['penalty_applied'])
        oracle = self.oracle(spec, {})
        with self.assertRaises(ValueError):
            oracle([99, 99])
        self.assertFalse(oracle.events[-1]['penalty_applied'])

    def test_cstr30_logical_exclusion_uses_same_penalty(self):
        spec = copy.deepcopy(next(j['spec'] for j in self.plan if j['spec']['case'] == 'cstr_30'))
        spec['starts'] = [[1, 30]] * 3
        table, _ = runner.lookup_table(ROOT, 'cstr_30')
        oracle = self.oracle(spec, table)
        self.assertEqual(oracle([1, 30]), 1e6)
        self.assertEqual(oracle.events[0]['evaluation_state'], 'logical_exclusion_unmeasured')
        self.assertFalse(oracle.events[0]['accepted'])

    def test_override_scope_and_other_method_unchanged(self):
        spec = copy.deepcopy(self.plan[0]['spec'])
        table, _ = runner.lookup_table(ROOT, spec['case'])
        spec['method'] = 'bam'
        with self.assertRaises(ValueError):
            self.oracle(spec, table)
        spec.pop('unaccepted_response')
        self.assertTrue(math.isnan(self.oracle(spec, table)(spec['starts'][0])))
        spec['method'] = 'fmqa_sa'
        self.assertTrue(math.isinf(self.oracle(spec, table)(spec['starts'][0])))
        spec.update(method='dsda', case='column', unaccepted_response=1e6)
        with self.assertRaises(ValueError):
            self.oracle(spec, table)

    def test_repeated_costs_and_missing_costs(self):
        spec = self.plan[0]['spec']
        events = core.jsonl(ROOT / 'baseline' / spec['job_id'] / 'callbacks.jsonl')
        result, ledger = runner.metrics(ROOT, spec, events, {'status': 'completed', 'dfo_wall_s': 1})
        self.assertAlmostEqual(result['estimated_completion_s'], 1 - sum(e['lookup_wall_s'] for e in events) + sum(e['historical_point_cost_s'] for e in ledger))
        with patch.object(runner, 'cost_table', return_value={}):
            result, _ = runner.metrics(ROOT, spec, events, {'status': 'completed', 'dfo_wall_s': 1})
        self.assertIsNone(result['estimated_completion_s'])
        self.assertEqual(len(result['missing_cost_keys']), len(events))

    def test_primary_settings_are_genetic_and_dsda_unchanged(self):
        for job in self.plan:
            spec = job['spec']
            if spec['method'] == 'rbfopt':
                self.assertEqual(spec['settings'], {'algorithm': 'MSRSM', 'global_search_method': 'genetic', 'rbf': 'auto', 'num_cpus': 1})
                self.assertEqual(job['reference_settings']['function_scaling'], 'auto')
                self.assertEqual(job['reference_settings']['dynamism_clipping'], 'auto')
            else:
                self.assertEqual(spec['settings'], {'diagonal': True, 'tie_break': 'first', 'tol': 1e-12})

    def test_legacy_no_override_is_byte_identical_for_events(self):
        # Compare source before the patch, with clocks/IO controlled. Every method
        # outside the override must retain precisely the same event and response.
        namespace = {'__file__': str(ROOT / 'ipopt_dfo_cstr.py'), '__name__': 'legacy_core'}
        exec((ROOT / 'provenance/original_ipopt_dfo_cstr.py.txt').read_text(), namespace)
        spec = copy.deepcopy(self.plan[0]['spec'])
        spec.pop('unaccepted_response')
        table, _ = runner.lookup_table(ROOT, spec['case'])
        for method in ('dsda', 'rbfopt', 'bam', 'fmqa_sa'):
            spec['method'] = method
            with patch('time.perf_counter', return_value=1):
                old = namespace['Oracle'](spec, table, self.path)
                new = self.oracle(spec, table)
                for point in spec['starts']:
                    a, b = old(point), new(point)
                    self.assertTrue(a == b or math.isnan(a) and math.isnan(b))
                self.assertEqual(old.events, new.events)

    def test_dry_run_and_resume_lifecycle_with_simulated_workers(self):
        # Use sealed archived callbacks as simulated process output, never run
        # an optimizer here. Exercise interruption, failed-slot retention and resume.
        args = SimpleNamespace(mode='run', output_root=self.path, python='unused',
                               conda='', bonmin='unused', ipopt='unused', cpu=None,
                               run_dir=None)
        attempts = []
        def simulated(command, dest, seconds, fd):
            if dest.parent.name == 'checks':
                return 0, 0.01
            attempts.append(dest.name)
            if len(attempts) == 2:
                raise KeyboardInterrupt('simulated interruption')
            spec = core.read(dest / 'job.json')['spec']
            base = ROOT / 'baseline' / spec['job_id']
            (dest / 'callbacks.jsonl').write_bytes((base / 'callbacks.jsonl').read_bytes())
            core.write(dest / 'result.json', {'status': 'completed', 'recorded_search_wall_s': 1})
            return 0, 1
        with patch.object(runner.platform, 'system', return_value='Linux'), \
             patch.object(core, 'select_cpu', return_value={'simulated': True}), \
             patch.object(core, 'python_command', return_value=['unused']), \
             patch.object(runner, 'launch', side_effect=simulated), \
             patch.object(runner, 'summarize'), patch.object(runner, 'pack'):
            with self.assertRaises(KeyboardInterrupt):
                runner.controller(args)
            directory = next(self.path.glob('cstr_penalty_1e6_*'))
            failed = directory / 'jobs' / attempts[-1] / 'result.json'
            before = failed.read_bytes()
            args.mode, args.run_dir = 'resume', directory
            runner.controller(args)
            self.assertEqual(failed.read_bytes(), before)
        self.assertEqual(len(attempts), 120)
        self.assertEqual(len(set(attempts)), 120)
        self.assertEqual(core.read(failed)['status'], 'execution_failed')
        # Separate real summary check: all 120 slots and failed earlier-target rule.
        counts = runner.summarize(ROOT, directory)
        self.assertEqual(sum(counts.values()), 120)
        exported = runner.rows(directory / 'rbfopt_coordinates.csv')
        self.assertTrue(exported)
        for row in exported:
            self.assertIn('rbfopt', row['job_id'])
            self.assertEqual(json.loads(row['point']), [round(v) for v in json.loads(row['callback_coordinates'])])


if __name__ == '__main__':
    unittest.main()

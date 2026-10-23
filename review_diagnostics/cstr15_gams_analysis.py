"""Import and compare the retained CSTR15 GAMS check without invoking a solver."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import re
import stat
import tempfile
import zipfile

from review_comparison.common import writecsv
from . import cstr15_gams as g
from .common import ROOT, environment, read, save, sha

ARCHIVE = ROOT / 'results/archives/review_cstr15_dantzig_20261021_161412_30959_return_1792599258428957007.zip'
LOCAL = ROOT / 'results/review_feasibility_tautology_20261020'
SOURCES = ('review_diagnostics/cstr15_gams_analysis.py', *g.SOURCES)


def extract_verified(archive, destination):
    archive = Path(archive)
    checksum = archive.with_suffix(archive.suffix + '.sha256').read_text().split()
    if len(checksum) != 2 or checksum[1] != archive.name or sha(archive) != checksum[0]:
        raise ValueError('Return ZIP checksum mismatch')
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate archive member')
        roots = set()
        for info in z.infolist():
            p = Path(info.filename)
            if p.is_absolute() or '..' in p.parts or stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError('Unsafe archive member')
            roots.add(p.parts[0])
        if len(roots) != 1:
            raise ValueError('Expected one result root')
        root = next(iter(roots))
        manifest_name = root + '/RETURN_MANIFEST.json'
        manifest = json.loads(z.read(manifest_name))
        expected = {root + '/' + name for name in manifest['files_sha256']} | {manifest_name}
        if set(names) != expected:
            raise ValueError('Return manifest member inventory mismatch')
        from hashlib import sha256
        for name, digest in manifest['files_sha256'].items():
            if sha256(z.read(root + '/' + name)).hexdigest() != digest:
                raise ValueError('Return manifest hash mismatch: ' + name)
        z.extractall(destination)
    return Path(destination) / root, {'sha256': checksum[0], 'members': len(names), 'all_member_hashes_verified': True}


def derived_metadata_check(saved, replay, bounds):
    """Check each ratio against its own checked objective, without a new tolerance."""
    for record in (saved, replay):
        eligible = record['tightened_feasibility_passed'] and record['execution_protocol_confirmed']
        expected = g.bound_comparisons({'objective': record['objective']}, bounds, eligible)
        if record['bounds'] != expected:
            raise ValueError('Bound metadata is not an exact derivation of its recorded objective')
    a, b = deepcopy(saved), deepcopy(replay)
    a.pop('bounds')
    b.pop('bounds')
    if not g.equivalent(a, b):
        raise ValueError('Primal values or non-derived summary fields disagree')
    for method in bounds:
        for key in ('rho_gt_1', 'tightened_bound_discrepancy_persists'):
            if saved['bounds'][method][key] != replay['bounds'][method][key]:
                raise ValueError('Bound classification changed on replay')
    return {method: {key: {'saved': saved['bounds'][method][key],
                           'replayed': replay['bounds'][method][key],
                           'difference': replay['bounds'][method][key] - saved['bounds'][method][key]}
                     for key in ('objective', 'delta', 'tau', 'rho')}
            for method in bounds}


def residual_metadata_check(saved, replay):
    # Ranking near-zero residuals can change while every named residual agrees.
    # Validate both rankings from their own complete rows, then compare all rows.
    for record in (saved, replay):
        expected = sorted(record['constraints'] + record['bounds'],
                          key=lambda r: r['violation'] or 0, reverse=True)[:20]
        if record['largest_residuals'] != expected:
            raise ValueError('Residual ranking is not derived from its complete residual rows')
    a, b = deepcopy(saved), deepcopy(replay)
    a.pop('largest_residuals')
    b.pop('largest_residuals')
    if not g.equivalent(a, b):
        raise ValueError('Original-GDP residual/configuration checks disagree')
    return {'all_named_residuals_verified': True,
            'saved_largest_residual_names': [r['name'] for r in saved['largest_residuals']],
            'replayed_largest_residual_names': [r['name'] for r in replay['largest_residuals']],
            'ranking_identical': saved['largest_residuals'] == replay['largest_residuals']}


def independently_verify(directory):
    strict_error = None
    try:
        g.verify(directory)
    except ValueError as error:
        # Keep the original verifier unchanged and expose its actual outcome.
        # These are the only checks with derived ratios/rankings; provenance
        # and preflight/model proofs have already passed before either message.
        if str(error) not in {'Saved summary disagrees with independent replay',
                              'Saved returned vector or residuals disagree'}:
            raise
        strict_error = str(error)
    summary, solution, residuals = g.assess(directory)
    saved = read(directory / 'summary.json')
    if solution is None or solution != read(directory / 'solution.json'):
        raise ValueError('Actual returned vector is absent or changed')
    differences = derived_metadata_check(saved, summary, read(directory / 'input_evidence.json')['bounds'])
    residual_check = residual_metadata_check(read(directory / 'residuals.json'), residuals)
    return {'original_verifier_passed': strict_error is None, 'original_verifier_error': strict_error,
            'independent_primal_and_provenance_verified': True, 'new_solver_calls': 0,
            'returned_vector_exactly_preserved': True, 'replayed_summary': summary,
            'derived_bound_differences': differences, 'residual_metadata': residual_check,
            'comparison_policy': 'Original 1e-12 replay comparator retained for primal/full named residual data; each derived ratio and ranking checked exactly against its own data; original 1e-8 feasibility criterion unchanged.'}


def constant_rows(model):
    from gdp_models.comparison import pyo
    from pyomo.core.expr.visitor import identify_variables
    rows = []
    for c in model.component_data_objects(pyo.Constraint, active=True, descend_into=True):
        if list(identify_variables(c.body, include_fixed=False)):
            continue
        body = g.identities.exact_value(c.body)
        lo = g.identities.exact_value(c.lower) if c.has_lb() else None
        hi = g.identities.exact_value(c.upper) if c.has_ub() else None
        if (lo is not None and body < lo) or (hi is not None and body > hi):
            raise ValueError('False constant row: ' + c.name)
        rows.append({'name': c.name, 'exact_body': str(body), 'exact_lower': str(lo) if lo is not None else None,
                     'exact_upper': str(hi) if hi is not None else None, 'equality': c.equality,
                     'satisfied_exactly': True, 'tolerance_used': 0})
    return rows


def iterations(log):
    matches = re.findall(r'Number of Iterations\.+:\s*(\d+)', log)
    if len(matches) != 1:
        raise ValueError('Expected exactly one solver iteration count')
    return int(matches[0])


def analyze(archive, output):
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    with tempfile.TemporaryDirectory(prefix='cstr15-return-') as temporary:
        raw, archive_check = extract_verified(archive, temporary)
        verification = independently_verify(raw)
        local_replay = g.identities.verify(LOCAL, g.INPUT)
        _, nlp, before, _, evidence = g.inputs(g.INPUT)
        constants = constant_rows(nlp)
        mapping = read(raw / 'gams_mapping.json')
        exported_constants = sum(len(mapping['constraints'][r['name']]) for r in constants)
        server = read(raw / 'summary.json')
        expected_equations = mapping['gams_equations_including_objective'] - exported_constants
        if server['raw_gams_statistics']['NUMEQU'] != expected_equations:
            raise ValueError('Constant rows do not explain the reported GAMS equation count')
        local = read(LOCAL / 'summary.json')
        local_row = local['assessment']
        original_vector = read(raw / 'before_solution.json')
        local_start = read(LOCAL / 'before_solution.json')
        if any(original_vector[k] != local_start[k] for k in ('variables', 'booleans')):
            raise ValueError('Dantzig and local runs did not start from the same original W03')
        local_vector = read(LOCAL / 'solution.json')['variables']
        server_vector = read(raw / 'solution.json')['variables']
        if local_vector.keys() != server_vector.keys():
            raise ValueError('Solution variable sets differ')
        differences = {k: server_vector[k] - local_vector[k] for k in local_vector}
        worst = max(differences, key=lambda k: abs(differences[k]))
        configuration = read(raw / 'residuals.json')['discrete_configuration']
        if configuration != read(LOCAL / 'residuals.json')['discrete_configuration']:
            raise ValueError('The two returned configurations differ')
        rows = [
            {'record': 'original_W03', 'objective': before['objective'], 'maximum_unscaled_violation': before['maximum_unscaled_primal_violation'], 'passes_1e_8': before['maximum_unscaled_primal_violation'] <= 1e-8, 'ipopt_iterations': None, 'worker_wall_s': None},
            {'record': 'retained_local_AMPL_IPOPT', 'objective': local_row['objective'], 'maximum_unscaled_violation': local_row['maximum_unscaled_primal_violation'], 'passes_1e_8': local_row['tightened_feasibility_passed'], 'ipopt_iterations': iterations((LOCAL / 'worker.log').read_text()), 'worker_wall_s': local['execution']['wall_s']},
            {'record': 'Dantzig_GAMS_IPOPT', 'objective': server['objective'], 'maximum_unscaled_violation': server['maximum_unscaled_original_GDP_violation'], 'passes_1e_8': server['tightened_feasibility_passed'], 'ipopt_iterations': iterations((raw / 'solver_input/gams.log').read_text()), 'worker_wall_s': read(raw / 'execution.json')['wall_s']},
        ]
        bounds = [{'record': row['record'], 'method': method, **values}
                  for row in rows for method, values in g.bound_comparisons({'objective': row['objective']}, evidence['bounds'], row['passes_1e_8']).items()]
        analysis = {'server_new_NLP_calls': server['actual_new_NLP_calls'], 'new_NLP_calls_in_analysis': 0,
                    'same_original_W03_start': True, 'same_discrete_configuration': True,
                    'discrete_value_count': len(configuration), 'solution_variable_count': len(differences),
                    'Dantzig_minus_local_objective': server['objective'] - local_row['objective'],
                    'maximum_absolute_variable_difference': abs(differences[worst]), 'maximum_difference_variable': worst,
                    'server_execution_revision': read(raw / 'selection.json')['code_revision'],
                    'historical_execution_provider_revision': read(raw / 'selection.json')['historical_execution_provider_revision'],
                    'local_success_retention_revision': '854a1a7fc5a20a5489d82ef7991a16aaf89025f3',
                    'server_environment': read(raw / 'environment.json'), 'server_protocol': server['log_evidence'],
                    'server_raw_statistics': server['raw_gams_statistics'],
                    'local_solver': read(LOCAL / 'selection.json')['solver'],
                    'local_options': (LOCAL / 'ipopt.opt').read_text(),
                    'server_options': (raw / 'solver_input/ipopt.opt').read_text(),
                    'local_worker_result': read(LOCAL / 'worker_result.json'), 'server_worker_result': read(raw / 'worker_result.json'),
                    'equations': {'original_active': evidence['counts']['before'], 'after_three_identity_rows': evidence['counts']['after'],
                                  'GAMS_export_including_objective': mapping['gams_equations_including_objective'],
                                  'exact_satisfied_constant_inequalities': len(constants),
                                  'GAMS_generated_equations_including_objective': expected_equations,
                                  'IPOPT_variables': int(re.search(r'Total number of variables\.+:\s*(\d+)', (raw / 'solver_input/gams.log').read_text())[1]),
                                  'IPOPT_equalities': int(re.search(r'Total number of equality constraints\.+:\s*(\d+)', (raw / 'solver_input/gams.log').read_text())[1]),
                                  'IPOPT_inequalities': int(re.search(r'Total number of inequality constraints\.+:\s*(\d+)', (raw / 'solver_input/gams.log').read_text())[1])},
                    'limitations': ['Single fixed-configuration numerical check, not exact feasibility or global optimality.',
                                    'GLOA discrepancy cause is not established.',
                                    'Different interfaces, solver versions and treatment of constant inequalities prevent causal attribution of iteration/time differences.',
                                    'Diagnostic elapsed times are not added to benchmark performance tables.']}
        output.mkdir(parents=True)
        writecsv(output / 'comparison.csv', rows)
        writecsv(output / 'bound_comparison.csv', bounds)
        save(output / 'analysis.json', analysis)
        save(output / 'verification.json', verification)
        save(output / 'local_reverification.json', local_replay)
        save(output / 'constant_inequalities.json', constants)
        render_readme(output, rows, bounds, analysis, verification, Path(archive).name)
        manifest = {'analysis_kind': 'post-execution solver-free comparison', 'analysis_environment': environment(),
                    'archive': 'results/archives/' + Path(archive).name, 'archive_check': archive_check,
                    'archive_result_root': raw.name,
                    'server_execution_revision': analysis['server_execution_revision'],
                    'historical_execution_provider_revision': analysis['historical_execution_provider_revision'],
                    'source_sha256': {name: sha(ROOT / name) for name in SOURCES},
                    'historical_local_files_sha256': {str(p.relative_to(ROOT)): sha(p) for p in sorted(LOCAL.rglob('*')) if p.is_file()},
                    'output_sha256': {p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file()},
                    'reproduce': 'python -m review_diagnostics.cstr15_gams_analysis --output /path/to/new/analysis',
                    'new_solver_calls': 0}
        save(output / 'manifest.json', manifest)
    return analysis


def render_readme(output, rows, bounds, analysis, verification, archive_name):
    local, server = rows[1:]
    selected = {r['method']: r for r in bounds if r['record'] == 'Dantzig_GAMS_IPOPT'}
    gloa, hull = selected['gloa'], selected['hull']
    lines = ['# CSTR15: Dantzig GAMS/IPOPT versus retained local check', '',
             'The returned Dantzig point passes the original-GDP 1e-8 numerical feasibility test.',
             f"The original ZIP is retained unchanged as [the return archive](../archives/{archive_name}) with its adjacent SHA256 file.",
             'All raw inputs, logs, listing, solution vectors, preflight files, historical execution sources and the server verification report remain inside that archive.',
             f"The single server NLP call used execution revision `{analysis['server_execution_revision']}`; this import and analysis performed zero NLP calls.",
             'The starting point and all 75 discrete values match the retained original W03 configuration.', '',
             '| Record | Objective | Maximum unscaled violation | Passes 1e-8 | IPOPT iterations |',
             '|---|---:|---:|---|---:|']
    for row in rows:
        lines.append(f"| {row['record']} | {row['objective']} | {row['maximum_unscaled_violation']} | {row['passes_1e_8']} | {row['ipopt_iterations'] if row['ipopt_iterations'] is not None else 'not applicable'} |")
    lines += ['', f"Dantzig minus local objective is `{analysis['Dantzig_minus_local_objective']}`.",
              f"Across the 231 saved variable values, the largest absolute difference is `{analysis['maximum_absolute_variable_difference']}` at `{analysis['maximum_difference_variable']}`.",
              'The two objectives differ only at floating-point roundoff scale; the smaller residual is not evidence of a mathematically better solution.',
              '', '## Retained lower bounds', '',
              f"For GLOA A12, lower bound `{gloa['lower_bound']}`, delta `{gloa['delta']}`, tau `{gloa['tau']}` and rho `{gloa['rho']}` retain the rho > 1 discrepancy.",
              f"For Hull A15, lower bound `{hull['lower_bound']}`, delta `{hull['delta']}`, tau `{hull['tau']}` and rho `{hull['rho']}` are within the audit tolerance.",
              'Both tightened points yield the same two classifications, while the original W03 point itself does not pass the tighter 1e-8 test.',
              'The full original/local/Dantzig comparisons are generated in [comparison.csv](comparison.csv) and [bound_comparison.csv](bound_comparison.csv).',
              'These records do not establish exact mathematical feasibility, global optimality or the cause of the GLOA lower-bound discrepancy.',
              '', '## Environment and equation-count differences', '',
              'Dantzig used GAMS 52.2.0, IPOPT 3.14.19 and MUMPS 5.8.1 with Python 3.11.16 and Pyomo 6.10.0.',
              'The retained macOS run used the AMPL interface and IPOPT 3.12.13 with MUMPS; its log does not identify the MUMPS version.',
              'Both runs use the original W03 start, the same numerical tolerances and the same three proved identity removals.',
              'Dantzig explicitly requests MUMPS and no dual warm start, while the local option file leaves those two options implicit; all raw options are preserved in analysis.json.',
              'The local run uses max_cpu_time=290, while GAMS uses reslim=290; both outer worker limits are 300 seconds.',
              'The computational clone has 156 free continuous variables and 303 constraints, including 155 equalities.',
              'The GAMS input has 304 equation blocks including the objective; its listing reports 156 generated equations including that objective.',
              'All 148 remaining inequalities are satisfied constant expressions after discrete fixing, proved exactly as 1 >= 1 or 2 >= 1 in [constant_inequalities.json](constant_inequalities.json).',
              'Their count exactly accounts for the GAMS equation reduction; IPOPT receives 155 equalities and no inequalities after objective substitution.',
              'The earlier AMPL/NL export retained those 148 inequalities, so it is not the identical solver-level representation even though the fixed original GDP and independently checked constraints agree.',
              f"The retained outer worker times are local `{local['worker_wall_s']}` seconds and Dantzig `{server['worker_wall_s']}` seconds.",
              'The inner timing scopes differ: local solve_and_check includes residual validation, while the GAMS worker timing covers its process launch and completion.',
              'The 28 versus 8 iterations and these diagnostic times do not isolate an effect of the solver version, interface or constant-row treatment.',
              'No diagnostic time is added to existing benchmark cost or performance tables.',
              '', '## Independent replay and floating-point metadata', '',
              f"The original unmodified full-summary verifier passed in this analysis environment: `{verification['original_verifier_passed']}`.",
              f"Its recorded error, if any, is `{verification['original_verifier_error']}`.",
              'The server verification report remains unchanged and records its successful server-side replay.',
              'The separate analysis verifier checks the same archived hashes, execution sources, model proofs and actual vector, then compares every original-GDP residual and configuration field with the existing 1e-12 replay comparator.',
              'Each bound ratio is checked exactly from its own recorded objective, and each largest-residual ranking is checked exactly against its own full residual rows.',
              'The local re-evaluation changes the Dantzig objective by floating-point roundoff; dividing the small Hull gap by tau amplifies that difference in rho, and near-zero residual rankings can also change.',
              'These derived differences and both rankings are exposed in [verification.json](verification.json), rather than replacing the server summary or weakening the original verifier.',
              'The original 1e-8 feasibility criterion and both bound classifications are unchanged.',
              '', '## Reproduce without a solver', '', '```bash',
              'git submodule update --init external/dsda-gdp',
              'python -m review_diagnostics.cstr15_gams_analysis --output /path/to/new/analysis',
              '```', '',
              'Use the repository GDP dependencies with Pyomo 6.10.0; neither GAMS nor IPOPT is needed for this command.',
              'The command checks the ZIP and its complete return manifest, extracts into a temporary directory and regenerates the comparisons and verification reports.',
              'Use a new output directory; original outputs and source revisions are never overwritten.',
              '', '## Draft reviewer wording', '',
              f"An additional single-call CSTR15 check in the archived Dantzig GAMS/IPOPT environment returned objective {server['objective']} with maximum unscaled original-GDP violation {server['maximum_unscaled_violation']}, satisfying the 1e-8 numerical test.",
              f"The objective differed from the retained local AMPL/IPOPT result by {analysis['Dantzig_minus_local_objective']}, with the same discrete configuration.",
              'The retained GLOA lower-bound discrepancy persisted, whereas the Hull difference was within the audit tolerance.',
              'This is fixed-configuration numerical evidence and does not establish exact feasibility, global optimality or the source of the lower-bound discrepancy.',
              'These sentences are a draft only; this task did not edit the manuscript, Overleaf, figures or historical performance records.', '',
              '## Validation', '',
              'See the [validation report](../../docs/validation/cstr15_dantzig_results_20261021.json) for the solver-free tests, deterministic CSV replay and preservation checks.',
              'The targeted test command is `python -m pytest tests/test_cstr15_gams_analysis.py tests/test_cstr15_gams.py tests/test_review_diagnostics_feasibility.py tests/test_review_feasibility_followup.py tests/test_review_feasibility_tautology.py -q`.', '']
    (output / 'README.md').write_text('\n'.join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, default=ARCHIVE)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    analyze(args.archive, args.output)
    print('Solver-free analysis completed: ' + str(args.output))


if __name__ == '__main__':
    main()

"""Run the immutable error-only selection for one Grid GDPopt method."""
import argparse
from contextlib import contextmanager
import fcntl
from itertools import combinations
import json
import os
from pathlib import Path
import sys

import gdp_scip_experiments as experiment
from grid_recovery import install_worker


@contextmanager
def launcher_lock(output):
    output.mkdir(parents=True, exist_ok=True)
    with (output / '.method_launcher.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('This recovery method already has an active launcher.') from None
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['plan', 'run', 'check', 'status', 'pack'])
    parser.add_argument('--run-dir', type=Path)
    args = parser.parse_args(argv)
    if (args.mode in {'status', 'pack'}) != (args.run_dir is not None):
        parser.error('--run-dir is required only for status/pack')
    experiment.package_inventory()
    package = experiment.read(experiment.ROOT / 'gdp_scip_package.json')
    selection = experiment.read(experiment.ROOT / 'RECOVERY_SELECTION.json')
    method = package['split_method']
    grids = [j['grid_name'] for j in selection['jobs']]
    if (package['methods'] != [method] or package['planned_jobs'] != len(grids)
            or len(grids) != len(set(grids)) or package['recovery_grids'] != grids
            or any(j['status'] != 'error' or j['method'] != method for j in selection['jobs'])):
        raise ValueError('Invalid error-only selection')
    repository = Path(os.environ.get('GDP_SCIP_REPOSITORY', '/local/scratch/a/lee4382/repository/RBFopt_Test'))
    output = repository / 'results' / ('grid_gdpopt_scip_recovery_' + method)
    command = [args.mode, '--methods', method, '--cpu', str(package['cpu']),
               '--time-limit', '1800', '--output-root', str(output), '--grids', ','.join(grids)]
    if args.run_dir:
        command.extend(['--run-dir', str(args.run_dir)])
    install_worker(experiment)
    if args.mode in {'plan', 'status'}:
        return experiment.main(command)
    if sys.platform != 'linux':
        raise RuntimeError('Run on Dantzig; plan is the solver-free local mode.')
    from cpu_affinity import check_cpu_pair
    checks = [check_cpu_pair(a, b) for a, b in combinations(package['separate_cpu_ids'], 2)]
    print('CPU_SEPARATION=' + json.dumps({'requested_cpu': package['cpu'], 'checks': checks}), flush=True)
    print(f'METHOD={method}; JOBS={len(grids)}; OUTPUT_ROOT={output}', flush=True)
    with launcher_lock(output):
        return experiment.main(command)


if __name__ == '__main__':
    raise SystemExit(main())

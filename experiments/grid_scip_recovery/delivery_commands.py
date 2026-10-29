"""Write independent copy/paste upload, launch, tail and download commands."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'results/runners/grid_gdpopt_scip_recovery_20261025'
LOCAL = '/Users/albertlee0125/Repos/RBFopt_Test/results/runners/grid_gdpopt_scip_recovery_20261025'
SERVER = '/local/scratch/a/lee4382/repository/RBFopt_Test'
HOST = 'lee4382@dantzig.ecn.purdue.edu'


def main():
    pieces = []
    for method, cpu, count in [('ric', 12, 12), ('loa', 14, 19), ('gloa', 16, 15)]:
        stem = f'grid_gdpopt_scip_recovery_{method}_dantzig_20261025'
        runner = f'{SERVER}/results/runners/{stem}'
        pointer = f'{SERVER}/results/grid_gdpopt_scip_recovery_{method}/result_zip.txt'
        text = f'''{method.upper()}: {count} error jobs, CPU {cpu}

Mac upload (one SCP invocation, ZIP plus checksum):

scp {LOCAL}/{stem}.zip {LOCAL}/{stem}.zip.sha256 {HOST}:{SERVER}/

Dantzig launch (paste the complete parenthesized block once):

(
  set -e
  cd {SERVER}
  sha256sum -c {stem}.zip.sha256
  test ! -e results/runners/{stem} || {{ echo "Runner directory already exists; inspect its log before launching again."; exit 1; }}
  unzip -q {stem}.zip -d results/runners
  cd results/runners/{stem}
  sha256sum -c SHA256SUMS > verify.log
  bash run_method.sh plan > plan.json
  nohup bash run_method.sh run > run.log 2>&1 < /dev/null &
  echo $! > launcher.pid
  echo "Launched {method.upper()} on CPU {cpu}; launcher PID $(cat launcher.pid)"
)

Dantzig launcher log (Ctrl-C stops tail only):

tail -n 50 -f {runner}/run.log

Dantzig detailed current job / preflight log:

RUN_DIR=$(sed -n 's/^RUN_DIR=//p' {runner}/run.log | tail -n 1)
CURRENT_JOB=$(sed -n 's/^START //p' {runner}/run.log | tail -n 1)
if [ -n "$RUN_DIR" ] && [ -n "$CURRENT_JOB" ]; then
  tail -n 50 -f "$RUN_DIR/benchmark/$CURRENT_JOB/run.log"
elif [ -n "$RUN_DIR" ]; then
  tail -n 50 -f "$RUN_DIR/preflight/preflight.log"
else
  tail -n 50 -f {runner}/run.log
fi

Dantzig result ZIP path after completion:

cat {pointer}

Mac download after RESULT_ZIP is printed (one SCP invocation; this directory belongs only to this recovery method):

scp '{HOST}:{SERVER}/results/grid_gdpopt_scip_recovery_{method}/*.zip*' ~/Downloads/
'''
        (OUTPUT / f'COMMANDS_{method.upper()}.txt').write_text(text)
        pieces.append(text)
    (OUTPUT / 'DANTZIG_COMMANDS.txt').write_text('\n\n'.join(pieces))
    (OUTPUT / 'README.md').write_text('''# Error-only Grid SCIP recovery delivery

The three ZIPs contain exactly 46 error jobs: RIC 12, LOA 19 and GLOA 15.
They use CPUs 12, 14 and 16 and leave the original combined run on CPU 6 alone.
The five original time limits and twelve reported-optimal jobs are excluded.
Each ZIP is a complete independent package with its own checksum and result directory.
COMMANDS_RIC.txt, COMMANDS_LOA.txt and COMMANDS_GLOA.txt provide separate upload, launch, tail and download blocks.
An OK checksum message only verifies bytes; the launch block and RUN_DIR/START/DONE logs establish execution.
The launch command refuses to overwrite an already extracted runner directory.
No Dantzig solver was executed during package preparation.
The original analysis is stored in results/grid_gdpopt_scip_20261025, and the recovery source and policy are in experiments/grid_scip_recovery.
All 961 bohachevsky2 configurations and bounded network-recovery behavior pass solver-free regression checks.
Validation also verifies the exact 46-job selection, frozen budgets and SCIP routing, package integrity, rejected scope changes and preservation of unfinished GAMS diagnostic files.
The new bounded retries cannot guarantee network or license-service availability, and a failed preflight must be investigated before interpreting the run.
Future results must be paired and reported separately from the preserved original first attempts.
''')


if __name__ == '__main__':
    main()

"""Package the two full-box IPOPT enumerators without calling a model or solver."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

import enumerate_process_ipopt as protocol

ROOT = Path(__file__).resolve().parent


def build(output):
    files = ['enumerate_column_ipopt.py', 'enumerate_dynamic_ipopt.py', 'enumerate_process_ipopt.py',
             'run_column_dynamic_ipopt_dantzig.sh', 'docs/column_dynamic_box_ipopt.txt', 'LICENSE']
    files += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / 'gdp_models').glob('*.py'))]
    entries = {name: (ROOT / name).read_bytes() for name in files}
    for case in protocol.CASES:
        for name, digest in protocol.REFERENCE_HASHES[case].items():
            source = protocol.reference_root() / case / name
            protocol.require(protocol.sha(source) == digest, 'Historical reference changed')
            entries[f'reference/{case}/{name}'] = source.read_bytes()
        entries[f'coordinates_{case}.json'] = (json.dumps(protocol.plan(case), indent=2) + '\n').encode()
    entries['requirements-original.txt'] = (
        'pyomo==6.10.0\nsympy==1.14.0\nnumpy==2.4.6\nnetworkx==3.6.1\nmatplotlib==3.11.2\n').encode()
    entries['bundle_provenance.json'] = (json.dumps({
        'kind': 'column_dynamic_original_ipopt_dfo_boxes_v1',
        'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'branch': subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip(),
        'builder_sha256': protocol.sha(__file__), 'expected_total_coordinates': 153,
        'source_policy': 'Actual bundled hashes identify working-tree code. Pinned upstream checkouts are read only.',
        'local_enumeration_executed': False,
    }, indent=2) + '\n').encode()
    entries['RUNNER_SHA256SUMS'] = ''.join(f'{hashlib.sha256(data).hexdigest()}  {name}\n'
                                        for name, data in sorted(entries.items())).encode()
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'x', zipfile.ZIP_DEFLATED) as z:
        for name, data in entries.items():
            z.writestr('column_dynamic_ipopt_runner/' + name, data)
    with zipfile.ZipFile(output) as z:
        protocol.require(z.testzip() is None, 'Bundle CRC failure')
    output.with_suffix('.zip.sha256').write_text(f'{protocol.sha(output)}  {output.name}\n')
    print(output.resolve())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output)

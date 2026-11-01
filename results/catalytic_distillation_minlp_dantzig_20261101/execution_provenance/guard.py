"""Data-only gates before the unchanged script advances to the next stage."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys


def check_scales(output, source):
    generated = output/'emp_scales.gms'
    original = source/'gdp_models/catalytic_distillation/emp_scales.gms'
    if not generated.is_file() or generated.read_bytes() != original.read_bytes():
        raise RuntimeError('EMP scales are absent or differ; validation and main experiments blocked')
    if 'scales=reproduced' not in (output/'environment.txt').read_text():
        raise RuntimeError('Scale reproduction was not confirmed by the original script')
    return {'passed':True,'sha256':hashlib.sha256(generated.read_bytes()).hexdigest()}


def main():
    output=Path(os.environ['MINLP_OUTPUT']); guard=Path(os.environ['MINLP_GUARD_DIR'])
    if sys.argv[1]=='preflight':
        solver=sys.argv[2]; directory=output/'preflight/preserved'/solver
        directory.mkdir(parents=True,exist_ok=False)
        for name in ('tiny.log','tiny.lst',solver+'.txt'):
            path=output/'preflight'/name
            if path.exists(): shutil.copy2(path,directory/path.name)
        text=(directory/'tiny.lst').read_text(errors='replace')
        if not re.search(r'\bGAMS\s+54\.3\.1\b',text):
            raise RuntimeError('Actual GAMS banner is not 54.3.1; no fallback is permitted')
        (guard/('version_'+solver+'.json')).write_text(json.dumps({'gams':'54.3.1','solver':solver,'listing':str(directory/'tiny.lst')}))
    elif sys.argv[1]=='scales':
        result=check_scales(output,Path(os.environ['MINLP_SOURCE']))
        (guard/'scales_gate.json').write_text(json.dumps(result,indent=2)+'\n')
    else: raise RuntimeError('Unknown guard mode')


if __name__=='__main__': main()

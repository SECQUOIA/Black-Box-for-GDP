"""Read-only MINLP54 evidence audit; standard library only; never calls a solver.

Usage: python3 verify_results.py RESULT_DIRECTORY BASELINE_REPOSITORY
Prints JSON; stdout can be redirected to an independent audit record.
"""
import collections
import csv
import datetime as dt
import gzip
import hashlib
import io
import itertools
import json
from pathlib import Path
import re
import sys
import zipfile

FORMS = ('product', 'bigm', 'chull')
SOLVERS = ('dicopt', 'sbb', 'baron', 'scip')
COORDS = ('f1', 'c1', 'c2', 'c3', 'f2', 'b')
CONFIGS = ('8_8_12_17_17_21', '7_8_11_16_16_20', '3_4_5_11_11_14',
           '4_4_9_10_14_17', '3_6_12_14_19_21', '2_3_9_10_20_21',
           '4_4_6_8_8_10', '3_4_5_6_8_9', '13_13_15_16_17_19')
REFERENCE = 24895.552861
HANGUL = re.compile('[\u1100-\u11ff\u3130-\u318f\ua960-\ua97f\uac00-\ud7af\ud7b0-\ud7ff]')

def sha(b):
    return hashlib.sha256(b).hexdigest()

def fields(text):
    return dict(x.split('=', 1) for x in text.split() if '=' in x)

def rows(text):
    return list(csv.DictReader(io.StringIO(text)))

def unique(items, key):
    out = {key(x): x for x in items}
    assert len(out) == len(items), 'Duplicate records'
    return out

def status(text):
    return tuple(int(re.search(r'\*\*\*\* '+x+r' STATUS\s+(\d+)', text)[1])
                 for x in ('MODEL', 'SOLVER'))

def classify(m, s):
    if m in (1, 2, 7, 8):
        return 'feasible_solution_returned'
    if s == 3:
        return 'time_limit_without_feasible_solution'
    if s == 5:
        return 'evaluation_interrupt_without_feasible_solution'
    if m == 19:
        return 'reported_infeasible_no_solution'
    return 'solver_terminated_without_feasible_solution'

def language_scan(name, data, counts, hits):
    if HANGUL.search(name):
        hits.append(name + ' [filename]')
    if data.startswith(b'PK\x03\x04'):
        counts['zip'] += 1
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            assert z.testzip() is None
            assert len(z.namelist()) == len(set(z.namelist()))
            for item in z.infolist():
                p = Path(item.filename)
                assert not p.is_absolute() and '..' not in p.parts
                if not item.is_dir():
                    language_scan(name + '!/' + item.filename, z.read(item), counts, hits)
    elif data.startswith(b'\x1f\x8b'):
        counts['gzip'] += 1
        language_scan(name + ' [uncompressed]', gzip.decompress(data), counts, hits)
    else:
        text = data.decode('utf-16' if data[:2] in (b'\xff\xfe', b'\xfe\xff') else 'utf-8-sig')
        counts['text'] += 1
        if HANGUL.search(text):
            hits.append(name)

def audit(root, repo):
    baseline = repo / 'results/catalytic_distillation_minlp_20261101'
    outer = root / 'evidence/RETURN_MINLP54.zip'
    if outer.exists():
        with zipfile.ZipFile(outer) as oz:
            prefix = 'results/' + root.name + '/'
            manifest = json.loads(oz.read(prefix + 'FILE_SHA256.json'))
            for name, expected in manifest.items():
                assert sha(oz.read(prefix + name)) == expected, name
        assert sha(outer.read_bytes()) == (root / 'evidence/RETURN_MINLP54.zip.sha256').read_text().split()[0]
    else:
        manifest = json.loads((root / 'FILE_SHA256.json').read_text())
        for name, expected in manifest.items():
            assert sha((root / name).read_bytes()) == expected, name
    blob = (root / 'evidence/raw.zip').read_bytes()
    assert len(blob) <= 90_000_000
    assert sha(blob) == (root / 'evidence/raw.zip.sha256').read_text().split()[0]
    counts, hits = collections.Counter(), []
    language_scan('raw.zip', blob, counts, hits)
    assert not hits
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        read = lambda p: z.read('raw/' + p).decode()
        exists = lambda p: 'raw/' + p in z.namelist()
        assert z.testzip() is None
        watchdogs = [json.loads(z.read(n)) for n in z.namelist() if '/guard/watchdogs/' in n and n.endswith('.json')]
        wd = unique(watchdogs, lambda x: x['cwd'].split('/raw/', 1)[1])
        assert len(wd) == 16
        assert all(w['exit_code'] == 0 and len(w['affinity']) == 1 for w in wd.values())
        assert len({w['affinity'][0] for w in wd.values()}) == 16
        summary = unique(rows((root / 'summary.csv').read_text()), lambda r: (r['form'], r['solver']))
        old = unique(rows((baseline / 'summary.csv').read_text()), lambda r: (r['form'], r['solver']))
        planned = set(itertools.product(FORMS, SOLVERS))
        assert set(summary) == planned == set(old)
        main = []
        for form, solver in itertools.product(FORMS, SOLVERS):
            path = form + '/' + solver
            f = fields(read(path + '/result.txt'))
            row, prev = summary[form, solver], old[form, solver]
            for name in ('result.txt', 'wall.txt', 'gams.log'):
                assert z.read('raw/' + path + '/' + name) == (root / path / name).read_bytes()
            for k in ('modelstat', 'solvestat', 'zobj', *COORDS, 'maxfrac'):
                assert row[k] == f[k], (path, k)
            wall = fields(read(path + '/wall.txt'))
            assert row['wall_s'] == f"{float(wall['wall_s']):.1f}"
            assert int(wall['cpu']) == wd[path]['affinity'][0]
            assert '--reslim=3600' in wd[path]['command']
            m, s = int(f['modelstat']), int(f['solvestat'])
            listing = read(path + ('/solve_minlp.lst' if form == 'product' else '/solve_emp.lst'))
            assert status(listing) == (m, s)
            assert (m, s) == (int(prev['modelstat']), int(prev['solvestat']))
            feasible = m in (1, 2, 7, 8)
            value = float(f['zobj'])
            main.append(dict(form=form, solver=solver, modelstat=m, solvestat=s,
                raw_zobj=value, feasible_objective=value if feasible else None,
                target_hit=feasible and abs(value - REFERENCE) <= 1e-5 * max(1, abs(REFERENCE)),
                configuration=[int(f[k]) for k in COORDS], maxfrac=float(f['maxfrac']),
                outcome=classify(m, s), wall_s=float(row['wall_s']), cpu=wd[path]['affinity'][0],
                process_exit=wd[path]['exit_code'], started_utc=wd[path]['started_utc'],
                finished_utc=wd[path]['finished_utc'], workstation_wall_s=float(prev['wall_s']),
                workstation_raw_zobj=float(prev['zobj']),
                raw_objective_difference=value-float(prev['zobj'])))
        vk = lambda r: (r['form'], '_'.join(r[k] for k in COORDS))
        val = unique(rows(read('validation/validation.csv')), vk)
        oldval = unique(rows((baseline / 'validation/validation.csv').read_text()), vk)
        assert val == oldval
        assert set(val) == set(itertools.product(('gdp', *FORMS), CONFIGS))
        assert read('validation/validation.csv') == (root/'validation/validation.csv').read_text()
        actual_val = {n for n in z.namelist() if n.startswith('raw/validation/') and n.endswith('/result.txt')}
        assert len(actual_val) == 36
        max_diff = 0.0
        for (form, config), row in val.items():
            f = fields(read(f'validation/{form}/{config}/result.txt'))
            for k in ('modelstat', 'solvestat', 'zobj'):
                assert row[k] == f[k]
            g = val['gdp', config]
            assert (row['modelstat']=='2') == (g['modelstat']=='2')
            if form in ('bigm', 'chull') and g['modelstat']=='2':
                d = abs(float(row['zobj'])-float(g['zobj']))
                assert d <= 1e-5 * float(g['zobj'])
                max_diff = max(d, max_diff)
        fixed = []
        for form, solver in itertools.product(('bigm','chull'), ('baron','scip')):
            path = f'fixed_best/{form}/{solver}'
            f = fields(read(path+'/result.txt'))
            for name in ('result.txt','gams.log'):
                assert z.read('raw/'+path+'/'+name) == (root/path/name).read_bytes()
            assert status(read(path+'/solve_emp.lst')) == (int(f['modelstat']),int(f['solvestat']))
            assert '--reslim=1200' in wd[path]['command']
            assert [int(f[k]) for k in COORDS] == [8,8,12,17,17,21]
            oldf=fields((baseline/path/'result.txt').read_text())
            assert (f['modelstat'],f['solvestat']) == (oldf['modelstat'],oldf['solvestat'])
            elapsed=(dt.datetime.fromisoformat(wd[path]['finished_utc'])-dt.datetime.fromisoformat(wd[path]['started_utc'])).total_seconds()
            fixed.append(dict(form=form,solver=solver,modelstat=int(f['modelstat']),solvestat=int(f['solvestat']),
                raw_zobj=float(f['zobj']),feasible_objective=None,wall_s=elapsed,cpu=wd[path]['affinity'][0],
                outcome=classify(int(f['modelstat']),int(f['solvestat'])),process_exit=0))
        cert=[]
        for config in ('7_8_11_16_16_20','8_8_12_17_17_21'):
            point=fields(read(f'certificates/{config}/point/result.txt'))
            assert (point['modelstat'],point['solvestat'])==('2','1')
            for mode in ('examine','scip_free','baron_free'):
                path=f'certificates/{config}/{mode}/check_point'
                log,lst=read(path+'.log'),read(path+'.lst')
                assert z.read('raw/'+path+'.log') == (root/(path+'.log')).read_bytes()
                assert z.read('raw/'+path+'.lst') == gzip.decompress((root/(path+'.lst.gz')).read_bytes())
                m,s=status(lst)
                if mode=='examine':
                    assert 'Primal variable bounds satisfied (tol = 1e-06)' in log
                    assert 'Primal constraints satisfied (tol = 1e-06)' in log
                    value=float(point['zobj']); sec=None
                elif mode=='scip_free':
                    value=float(re.search(r'Primal Bound\s*:\s*([+\-\d.eE]+)',log)[1])
                    sec=float(re.search(r'Solving Time \(sec\)\s*:\s*([\d.]+)',log)[1])
                    assert (m,s)==(1,1)
                else:
                    value=float(re.search(r'Solution\s*=\s*([\d.]+)',log)[1])
                    sec=float(re.search(r'Wall clock time:\s*([\d.]+)',log)[1])
                    assert (m,s)==(1,1)
                assert abs(value-float(point['zobj']))<1e-6
                cert.append(dict(configuration=config,mode=mode,modelstat=m,solvestat=s,objective=value,
                    reported_solver_seconds=sec,missing_baron_option_warning='Cannot open parameter file' in log))
        bigm_exam=read('examine_bigm_fixed_best/ex/log.txt')
        assert 'Primal variable bounds satisfied (tol = 1e-06)' in bigm_exam
        assert 'Primal constraints satisfied (tol = 1e-06)' in bigm_exam
        assert 'Unknown solver name none' in bigm_exam
        scale=read('emp_scales.gms').encode()
        assert scale == (repo/'gdp_models/catalytic_distillation/emp_scales.gms').read_bytes()
        assert json.loads(read('guard/scales_gate.json'))=={'passed':True,'sha256':sha(scale)}
        for solver in SOLVERS:
            f=fields(read('preflight/preserved/'+solver+'/'+solver+'.txt'))
            assert f['modelstat'] in ('1','2','8') and f['solvestat']=='1'
            assert 'GAMS 54.3.1' in read('preflight/preserved/'+solver+'/tiny.lst')
        assert len(read('guard/validation_affinity.txt').splitlines())==36
        assert not any(n.endswith('.gdx') or re.search(r'/225[^/]/',n) for n in z.namelist())
    env=json.loads((root/'execution_provenance/environment_wrapper.json').read_text())
    for name, expected in env['source_sha256'].items():
        assert sha((repo/name).read_bytes())==expected,name
    execution=json.loads((root/'execution_provenance/execution.json').read_text())
    assert execution['exit_code']==0
    assert execution['revision']==env['source_revision']=='a1c3bf336493dc496bb2571e160b1054f237e0be'
    cores=execution['cores']; assert len({(c['socket'],c['core']) for c in cores})==16
    assert {w['affinity'][0] for w in wd.values()}=={c['cpu'] for c in cores}
    for name in ('OMP_NUM_THREADS','OMP_THREAD_LIMIT','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','BLIS_NUM_THREADS'):
        assert env['threads'][name]=='1'
    elapsed=(dt.datetime.fromisoformat(execution['finished_utc'])-dt.datetime.fromisoformat(execution['started_utc'])).total_seconds()
    return dict(structural_verification_passed=True,revision=execution['revision'],execution=execution,
        controller_elapsed_seconds=elapsed,raw_zip_bytes=len(blob),raw_zip_sha256=sha(blob),
        uploaded_manifest_verified_files=len(manifest),source_hashes_verified=len(env['source_sha256']),
        main_runs=main,main_outcomes=dict(collections.Counter(x['outcome'] for x in main)),
        feasible_main_runs=sum(x['feasible_objective'] is not None for x in main),
        target_hits=sum(x['target_hit'] for x in main),missing_runs=0,duplicate_runs=0,
        process_failures=0,external_watchdog_timeouts=0,main_solver_time_limits=2,
        fixed_best=fixed,fixed_solver_time_limits=2,validation_count=36,
        validation_exact_workstation_match=True,bigm_hull_max_abs_difference_from_gdp=max_diff,
        scales_reproduced=True,certificates=cert,examiner_primal_checks_passed=3,
        warnings=['Four warm-start optimality claims are mutually inconsistent and are not accepted as proofs.',
                  'Both BARON warm-start checks warn that baron.opt is absent, then continue with default options.',
                  'Big-M Examiner passes the initial primal checks, then reports unknown subsolver none; no subsolver solution exists.',
                  'Original evidence excludes GDX files and 225? scratch directories.',
                  'Scheduler reservation and continuous CPU exclusivity are not established.'],
        language_scan={'counts':dict(counts),'hangul_hits':hits},
        model_status_9_label='Intermediate Non-Integer',
        status_reference='https://www.gams.com/54/docs/UG_GAMSOutput.html')

if __name__=='__main__':
    print(json.dumps(audit(Path(sys.argv[1]),Path(sys.argv[2])),indent=2,sort_keys=True))

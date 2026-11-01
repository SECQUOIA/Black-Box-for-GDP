"""Read-only accounting after the original MINLP script; never executes a solver."""
import csv
import json
import math
from pathlib import Path
import re
from collections import Counter
import verify as V
import support as S

FORMS=('product','bigm','chull')
SOLVERS=('dicopt','sbb','baron','scip')
CONFIGS=('8_8_12_17_17_21','7_8_11_16_16_20','3_4_5_11_11_14','4_4_9_10_14_17',
         '3_6_12_14_19_21','2_3_9_10_20_21','4_4_6_8_8_10','3_4_5_6_8_9','13_13_15_16_17_19')
FIELDS=('modelstat','solvestat','zobj','f1','c1','c2','c3','f2','b','maxfrac')
TARGET=24895.552861
TOL=1e-5*max(1,abs(TARGET))


def fields(path):
    return dict(item.split('=',1) for item in path.read_text().split() if '=' in item) if path.exists() else {}


def number(value):
    try:
        x=float(value);return x if math.isfinite(x) else None
    except (TypeError,ValueError):return None


def rows(path):return V.rows(path) if path.exists() else []


def audit(raw,dest,reference):
    issues=[];review=[];runs=[]
    summary=rows(dest/'summary.csv')
    indexed={(r['form'],r['solver']):r for r in summary}
    if len(indexed)!=len(summary):issues.append('Duplicate summary rows')
    expected={(f,s) for f in FORMS for s in SOLVERS}
    if set(indexed)-expected:issues.append('Unknown summary rows')
    baseline={(r['form'],r['solver']):r for r in rows(reference/'summary.csv')}
    watchdogs=[V.read(p) for p in (raw/'guard/watchdogs').glob('*.json')]
    for form,solver in sorted(expected):
        d=raw/form/solver;values=fields(d/'result.txt');wall=fields(d/'wall.txt')
        missing=[n for n in ('result.txt','wall.txt','gams.log') if not (d/n).is_file()]
        if missing:issues.append(f'{form}/{solver}: missing '+','.join(missing))
        s=indexed.get((form,solver));watch=[r for r in watchdogs if r['cwd']==str(d)]
        code=watch[0].get('exit_code') if len(watch)==1 else None
        if len(watch)!=1:issues.append(f'{form}/{solver}: watchdog record count {len(watch)}')
        if values:
            if not s:issues.append(f'{form}/{solver}: result omitted from summary')
            elif any(s.get(k,'')!=values.get(k,'') for k in FIELDS):issues.append(f'{form}/{solver}: summary disagrees with raw result')
            if s and number(wall.get('wall_s')) is not None and s['wall_s']!=f"{float(wall['wall_s']):.1f}":issues.append(f'{form}/{solver}: summary wall time differs')
        ss=number(values.get('solvestat'));ms=number(values.get('modelstat'));objective=number(values.get('zobj'))
        delta=objective-TARGET if objective is not None else None
        match=delta is not None and abs(delta)<=TOL
        improved=delta is not None and delta < -TOL
        if match or improved:review.append(f'{form}/{solver}: returned objective {objective}, difference {delta}, modelstat={ms}, solvestat={ss}; interpret before publication')
        outcome=('external_watchdog_timeout' if code in (124,137) else
                 'missing_result' if not values else 'solver_resource_limit' if ss==3 else
                 'solver_failure' if ss in (6,7,9,10,11,12,13) else
                 'no_feasible_solution_reported' if ms not in (1,2,7,8) else
                 'normal_feasible_reported' if ss==1 else 'other_termination_with_feasible_report')
        runs.append(dict(form=form,solver=solver,**{k:values.get(k,'') for k in FIELDS},
                         wall_s=wall.get('wall_s'),watchdog_exit=code,outcome=outcome,
                         difference_to_reference=delta,absolute_reference_match=match,lower_than_reference=improved,
                         missing_files=missing,workstation=baseline.get((form,solver))))
    validation=rows(dest/'validation/validation.csv')
    key=lambda r:(r['form'],'_'.join(r[k] for k in ('f1','c1','c2','c3','f2','b')))
    vi={key(r):r for r in validation}
    expected_validation={(f,c) for f in ('gdp',*FORMS) for c in CONFIGS}
    if len(validation)!=36 or set(vi)!=expected_validation:issues.append('Fixed-form validation coverage is not exactly 36 unique records')
    for form,c in sorted(expected_validation):
        values=fields(raw/'validation'/form/c/'result.txt');r=vi.get((form,c))
        if not values or not r or any(r.get(k,'')!=values.get(k,'') for k in ('modelstat','solvestat','zobj')):
            issues.append(f'Validation raw/CSV missing or inconsistent: {form}/{c}')
    reproduce=True
    for c in CONFIGS:
        gdp=vi.get(('gdp',c),{})
        if gdp.get('modelstat')=='2':
            gv=number(gdp.get('zobj'))
            for form in ('bigm','chull'):
                r=vi.get((form,c),{});rv=number(r.get('zobj'))
                if gv is None or rv is None or r.get('modelstat')!='2' or abs(rv-gv)>1e-5*gv:
                    reproduce=False;review.append(f'{form} does not reproduce GDP at {c}')
    text=(dest/'comparison.txt').read_text() if (dest/'comparison.txt').exists() else ''
    if ('Big-M and hull reproduce the GDP form at every feasible configuration: '+str(reproduce)) not in text:
        issues.append('comparison.txt reproduction conclusion is missing or inconsistent')
    scale=(raw/'guard/scales_gate.json').exists() and V.read(raw/'guard/scales_gate.json').get('passed') is True
    if not scale:issues.append('Mandatory scale reproduction gate missing or failed')
    fixed=[]
    for form in ('bigm','chull'):
        for solver in ('baron','scip'):
            d=raw/'fixed_best'/form/solver;v=fields(d/'result.txt')
            if not v or not (d/'gams.log').exists():issues.append(f'Fixed-best record missing: {form}/{solver}')
            fixed.append(dict(form=form,solver=solver,result=v))
            obj=number(v.get('zobj'))
            if obj is not None and (abs(obj-TARGET)<=TOL or obj<TARGET):review.append(f'Fixed-best {form}/{solver}: returned objective {obj}; review solver status')
    certificates=[]
    for name in CONFIGS[:2]:
        p=raw/'certificates'/name
        if not (p/'point/result.txt').exists():issues.append('Certificate point result missing: '+name)
        for mode in ('examine','scip_free','baron_free'):
            f=p/mode/'check_point.log'
            if not f.exists():issues.append(f'Certificate log missing: {name}/{mode}');continue
            content=f.read_text(errors='replace')
            passed='Primal variable bounds satisfied' in content and 'Primal constraints satisfied' in content
            certificates.append(dict(configuration=name,mode=mode,examiner_primal_checks=passed if mode=='examine' else None))
            if mode=='examine' and not passed:issues.append('Examiner did not confirm original certificate: '+name)
            if mode!='examine':
                listing=p/mode/'check_point.lst'
                reported=content+'\n'+(listing.read_text(errors='replace') if listing.exists() else '')
                for token in re.findall(r'(?:Solution\s*=|Primal Bound\s*:|VARIABLE\s+zobj\.L\s*=)\s*([-+]?\d+(?:\.\d*)?(?:[eE][-+]?\d+)?)',reported,re.I):
                    value=number(token)
                    if value is not None and (abs(value-TARGET)<=TOL or value<TARGET):
                        review.append(f'Certificate {name}/{mode}: reported objective {value} near or below reference; inspect termination before publication')
    examiner=raw/'examine_bigm_fixed_best/ex/log.txt'
    if not examiner.exists():issues.append('Big-M Examiner log missing')
    else:
        content=examiner.read_text(errors='replace')
        if 'Primal variable bounds satisfied' not in content or 'Primal constraints satisfied' not in content:
            issues.append('Big-M Examiner primal check not established')
    logs=list(raw.rglob('*.log'))+list(raw.rglob('*.lst'))
    try:conopt=S.conopt_version_evidence(logs)
    except RuntimeError as error:conopt=dict(version=None,error=str(error));issues.append('CONOPT version not established')
    versions=[]
    for p in logs:
        for line in p.read_text(errors='replace').splitlines():
            if re.search(r'GAMS\s+54\.3\.1|C\s*O\s*N\s*O\s*P\s*T.*version|(?:BARON|SCIP).*version|Version identifier:',line,re.I):
                versions.append(dict(file=str(p.relative_to(raw)),banner=line.strip()))
    archives=[]
    for p in sorted((dest/'evidence').glob('*.zip')):
        info=V.zip_check(p);check=p.with_name(p.name+'.sha256')
        if not check.exists() or check.read_text().split()[0]!=info['sha256']:issues.append('Evidence checksum mismatch: '+p.name)
        info['over_90_MB']=info['bytes']>90000000
        if info['over_90_MB']:review.append(f'Evidence ZIP exceeds 90 MB: {p.name}, {info["bytes"]} bytes')
        archives.append(info)
    if len(archives)!=1:issues.append('Expected exactly one original evidence ZIP')
    review.extend(issues)
    report=dict(planned_main=12,main_rows=runs,summary_rows=len(summary),outcomes=dict(Counter(r['outcome'] for r in runs)),
                validation_rows=len(validation),fixed_best=fixed,certificates=certificates,
                scales_reproduced=scale,bigm_hull_reproduce_gdp=reproduce,conopt=conopt,
                solver_version_banners=versions,archives=archives,reference=TARGET,tolerance=TOL,
                issues=issues,review_reasons=sorted(set(review)),structural_checks_passed=not issues,
                publication_requires_review=bool(review),
                note='Returned objective comparisons are separate from feasibility and termination status; no global optimum is certified.')
    V.write(dest/'validation_audit.json',report)
    return report


def readme(dest,report,environment,execution):
    lines=['# Dantzig catalytic Column MINLP reproduction','',
           'This run reproduces the existing workstation MINLP comparison using GAMS 54.3.1.',
           'The completed 210-job Column DFO campaign was not rerun.',
           f"Execution revision: `{execution['revision']}`; publication revision is pending review.",
           f"Host: `{execution['host']}`; allocated physical cores: `{json.dumps(execution['cores'])}`.",
           f"Start: `{execution['started_utc']}`; end: `{execution['finished_utc']}` (UTC).",
           f"GAMS executable: `{environment['real_gams']}`, SHA256 `{environment['gams_sha256']}`.",
           f"CONOPT backend: `{report['conopt'].get('version')}`; other observed solver banners are preserved in `validation_audit.json`.",
           'Unreported backend versions remain unconfirmed; interface build numbers are not substituted for them.',
           'All original models, initialization and mathematical solver options were preserved.',
           'The main MINLP limit is 3600 seconds and the four fixed-design limits are 1200 seconds.',
           'The supervisor preserves the original script and adds version/scale gates, validation-child affinity, and watchdog exit logging.',
           f"Scale reproduction: `{report['scales_reproduced']}`; fixed-form records: {report['validation_rows']}/36.",
           f"Big-M/Hull reproduce the GDP form: `{report['bigm_hull_reproduce_gdp']}`.",
           f'The reference {TARGET} USD/year is an observed best, not a proven global optimum.',
           'The absolute-difference tolerance is `1e-5 * max(1, abs(reference))`.',
           '', '| Form | Solver | Model status | Solver status | Objective | Outcome |',
           '|---|---|---:|---:|---:|---|']
    for r in report['main_rows']:lines.append(f"| {r['form']} | {r['solver']} | {r['modelstat']} | {r['solvestat']} | {r['zobj']} | {r['outcome']} |")
    lines+=['','Workstation values, objective differences, missing files and termination details are retained alongside every row in `validation_audit.json`.',
            'Failures, resource limits, watchdog timeouts and missing results are not omitted from the twelve planned combinations.',
            f"Full raw output remains at `{execution['output']}`.",
            'The original ZIP excludes `*.gdx` and `*/225?/*`; it is not a complete copy of all raw files.',
            'Original evidence ZIPs and checksum files were retained without recompression or alteration.']
    for a in report['archives']:lines.append(f"Evidence: `{a['name']}`, {a['bytes']} bytes, SHA256 `{a['sha256']}`, CRC passed.")
    lines+=['','Publication review reasons:']
    lines.extend('- '+r for r in report['review_reasons'] or ['None identified by the preliminary audit; independent return-archive verification is still pending.'])
    lines+=['','Reproduction uses the pinned offline source and the environment recorded in `execution_provenance/environment_wrapper.json`.',
            '```bash','bash experiments/catalytic_distillation_minlp/run_dantzig.sh','```',
            'No manuscript, Overleaf document, model, existing result, CI setting or unrelated benchmark was changed.']
    (dest/'README.md').write_text('\n'.join(lines)+'\n')

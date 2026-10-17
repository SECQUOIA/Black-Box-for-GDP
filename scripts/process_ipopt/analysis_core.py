"""Regenerate process-DFO results from the October 15 IPOPT return archives.

Reads immutable original and replacement archives. No optimizer/model/solver imports.
Run with an existing Python environment providing numpy and matplotlib.
"""
from __future__ import annotations
import ast
import base64
import csv
import gzip
import hashlib
import html
import io
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'results/process_ipopt_bam_v2_20261015'
os.environ.setdefault('MPLCONFIGDIR', str(OUT / '.mplcache'))

DATA = {
    'cstr': ROOT / 'results/ipopt_dfo_cstr_20261015_174637_r1dzn5tk',
    'non_cstr': ROOT / 'results/ipopt_dfo_non_cstr_20261015_172428_o671edu_',
    'cstr_bam': ROOT / 'results/bam_budget_v2/ipopt_dfo_cstr_20261015_223017_ncd_12gx',
    'non_cstr_bam': ROOT / 'results/bam_budget_v2/ipopt_dfo_non_cstr_20261015_223138_r3ifrgaq',
}
METHODS = ['rbfopt', 'bam', 'dsda', 'fmqa_sa']
LABELS = {'rbfopt': 'RBFOpt', 'bam': 'BAM', 'dsda': 'DSDA variant', 'fmqa_sa': 'FMQA-SA'}
COLORS = {'rbfopt': '#0072B2', 'bam': '#D55E00', 'dsda': '#009E73', 'fmqa_sa': '#8B5FBF'}
CONDITIONS = [(f'cstr_{n}', b) for n,b in [(5,8),(10,15),(15,22),(20,29),(25,36),(30,43)]] + [('column',16),('small_batch',10)] + [('dynamic',b) for b in [12,15,20,30,37,50]]
SOURCES = {}
FIGURES = []

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def source(path):
    path=Path(path)
    SOURCES[path.relative_to(ROOT).as_posix()] = {'sha256':sha(path), 'bytes':path.stat().st_size}
    return path

def readcsv(path):
    path=source(path)
    op=gzip.open if path.suffix=='.gz' else open
    with op(path,'rt',newline='') as f:
        return list(csv.DictReader(f))

def readjson(path):
    return json.loads(source(path).read_text())

def num(x):
    if x in (None,'','None','null'): return None
    y=float(x)
    return y if math.isfinite(y) else None

def yes(x): return x is True or str(x).lower()=='true'
def point(x): return tuple(json.loads(x)) if isinstance(x,str) else tuple(x)
def finite(x): return x is not None and math.isfinite(x)
def title(case,b=None):
    s=case.replace('cstr_','CSTR ').replace('small_batch','Small Batch').replace('column','Column').replace('dynamic','Dynamic')
    return s + (f' · B={b}' if b is not None else '')
def key(row): return row['case'], row['budget'], row['method']
def clean_json(x):
    if isinstance(x,dict): return {str(k):clean_json(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)): return [clean_json(v) for v in x]
    if isinstance(x,float) and not math.isfinite(x): return 'Infinity' if x>0 else '-Infinity' if x<0 else None
    return x
def savejson(path,x):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(clean_json(x),ensure_ascii=False,indent=2)+'\n')
def writecsv(name,rows):
    if not rows:return
    path=OUT/'tables'/name
    path.parent.mkdir(parents=True,exist_ok=True)
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for r in rows:
            rr={k:(json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict,tuple)) else ('inf' if isinstance(v,float) and math.isinf(v) else v)) for k,v in r.items()}
            w.writerow(rr)

def load():
    runs=[]; callbacks=[]; inputs={}; audits={}; raw_checks=[]; raw_jobs={}
    for batch,d in DATA.items():
        replacement=batch.endswith('_bam');dataset=batch.removesuffix('_bam')
        audits[dataset]=readjson(d/'audit.json')
        reports=readcsv((DATA[dataset] if replacement else d)/'inputs_report.csv')
        for r in reports:
            case=r['case']; path=d/'inputs'/case/'evaluations.csv'
            rows=readcsv(path); tab={point(r['point']):r for r in rows}
            assert len(tab)==len(rows),('duplicate_input',case)
            vals={p:float(r['objective']) for p,r in tab.items() if yes(r['accepted'])}
            assert vals and all(math.isfinite(x) for x in vals.values())
            inputs[case]={'rows':tab,'values':vals,'target':min(vals.values()),'report':r,'source':path.relative_to(ROOT).as_posix()}
        rr=readcsv(d/('audited_runs.csv' if dataset=='non_cstr' and not replacement else 'runs.csv'))
        rr=[r for r in rr if (r['method']=='bam')==replacement]
        cc=readcsv(d/'callbacks.csv.gz')
        jobs={r['job_id']:r for r in readjson(d/'job_metadata.json')}
        raw_jobs.update(jobs)
        byjob=defaultdict(list)
        for c in cc:byjob[c['job_id']].append(c)
        bad_ids=set() if replacement else {r['job_id'] for r in readcsv(d/('budget_control_issues.csv' if dataset=='non_cstr' else 'budget_control_failures.csv'))}
        for r in rr:
            case=r['case']; b=int(r['budget']); job=r['job_id']; target=inputs[case]['target']; method=r['method']
            category=r.get('audit_category',r['category']); protocol=job in bad_ids
            ev=[]; candidate_min=math.inf; returned_min=math.inf; known_cost=0.; unknown=0; init_hit=False
            first_hit=None; returned_first_hit=None; accepted_cost=0.; unaccepted_cost=0.
            for c in sorted(byjob[job],key=lambda x:int(x['index'])):
                i=int(c['index']); p=point(c['point']); within=i<=b
                v=num(c['raw_objective']); a=yes(c['accepted']); t=num(c['selected_attempt_nlp_s']); sr=inputs[case]['rows'].get(p)
                if within:
                    if sr is not None:
                        assert a==yes(sr['accepted']),('accepted_mismatch',job,i)
                        assert v==num(sr['objective']),('objective_mismatch',job,i)
                        assert t==num(sr.get('total_wall_s')),('time_mismatch',job,i)
                        raw_checks.append((job,i,True,a))
                    else:
                        assert not a and v is None and c['evaluation_state']=='logical_exclusion_unmeasured',('unexplained_missing_point',job,i,p)
                        raw_checks.append((job,i,False,False))
                    if a:
                        assert v is not None
                        candidate_min=min(candidate_min,v)
                        if yes(c['value_returned_to_optimizer']):returned_min=min(returned_min,v)
                    observed=finite(candidate_min) and abs(candidate_min-target)<=1e-5*max(1,abs(target))
                    if observed and first_hit is None:first_hit=i
                    if finite(returned_min) and abs(returned_min-target)<=1e-5*max(1,abs(target)) and returned_first_hit is None:returned_first_hit=i
                    if i<=3 and observed:init_hit=True
                    if t is None:unknown+=1
                    else:
                        known_cost+=t
                        if a:accepted_cost+=t
                        else:unaccepted_cost+=t
                else:
                    assert protocol and i==b+1 and yes(c.get('budget_overrun'))
                    assert c['evaluation_state']=='invalid_callback' and t is None
                    assert c['source_row'] in ('', '{}', 'null')
                    assert v is None and not a and not yes(c['value_returned_to_optimizer'])
                event={'job_id':job,'dataset':dataset,'case':case,'budget':b,'method':method,'seed':int(r['seed']),
                    'index':i,'phase':c['phase'],'point':p,'within_budget':within,'accepted':a,'objective':v,
                    'value_returned':yes(c['value_returned_to_optimizer']),'evaluation_state':c['evaluation_state'],
                    'historical_nlp_s':t,'elapsed_dfo_s':num(c['elapsed_s']),'lookup_s':num(c['lookup_wall_s']),
                    'incumbent':candidate_min if finite(candidate_min) else None,
                    'relative_gap':(candidate_min-target)/max(1,abs(target)) if finite(candidate_min) else None,
                    'target_observed':first_hit is not None,'audited_success_run':category=='target_reached',
                    'protocol_failure':protocol,'known_cumulative_nlp_s':known_cost,'missing_cumulative_nlp_count':unknown}
                ev.append(event);callbacks.append(event)
            assert int(r['callback_count'])==len(ev)
            assert num(r['best_accepted_objective'])==(candidate_min if finite(candidate_min) else None)
            assert (category=='target_reached')==(first_hit is not None and category not in ('execution_failed','not_run'))
            starts=json.loads(r['initial_points'])
            assert [list(e['point']) for e in ev[:3]]==starts
            dfo=num(r['dfo_wall_s']); lookup=num(r['lookup_wall_s']); original_total=num(r['historical_nlp_per_callback_sum_s'])
            complete=(unknown==0 and not protocol)
            prep=0.
            if case=='dynamic':
                pr=readjson(d/'inputs/dynamic/preparation.json')
                assert len(pr)==1 and pr[0]['scope']=='once_per_process'
                assert not pr[0]['included_in_point_total_wall_s']
                prep=float(pr[0]['total_preparation_wall_s'])
            estimate=(dfo-lookup+known_cost+prep) if complete and dfo is not None and lookup is not None else None
            nlower=int(r.get('actual_callbacks_lower_bound') or len(ev))
            row={'job_id':job,'dataset':dataset,'case':case,'budget':b,'method':method,'seed':int(r['seed']),
                'category':category,'original_category':r['category'],'execution_status':r['execution_status'],'error':r['error'],
                'protocol_failure':protocol,'target_observed_within_budget':first_hit is not None,
                'initial_target_observed':init_hit,'first_hit_callback':first_hit,'first_returned_hit_callback':returned_first_hit,
                'target_first_at_undelivered_terminal':first_hit==b and returned_first_hit is None,
                'target':target,'best_observed_objective':candidate_min if finite(candidate_min) else None,
                'relative_final_gap':(candidate_min-target)/max(1,abs(target)) if finite(candidate_min) else None,
                'best_point':json.loads(r['best_point']) if r['best_point'] else None,
                'initial_points':starts,'logged_callbacks':len(ev),'within_budget_callbacks':sum(e['within_budget'] for e in ev),
                'actual_callbacks_lower_bound':nlower,'unlogged_callback_count_unknown':dataset=='non_cstr' and protocol,
                'accepted_callbacks':sum(e['accepted'] for e in ev),'dfo_wall_s':dfo,'lookup_wall_s':lookup,
                'historical_nlp_known_within_budget_s':known_cost,'missing_within_budget_nlp_count':unknown,
                'historical_accepted_cost_s':accepted_cost,'historical_unaccepted_cost_s':unaccepted_cost,
                'within_budget_cost_complete':unknown==0,'published_cost_complete':yes(r['nlp_time_available']),
                'reported_historical_total_s':original_total,'dynamic_preparation_s':prep,
                'reconstructed_total_s':estimate,'time_status':'protocol_failure' if protocol else 'missing_nlp_cost' if unknown else 'complete',
                'input_csv_sha256':r['input_csv_sha256'],'result_batch':batch}
            assert row['input_csv_sha256']==SOURCES[inputs[case]['source']]['sha256']
            runs.append(row)
    assert len(runs)==560 and len(callbacks)==12822
    group=defaultdict(list)
    for r in runs:group[key(r)].append(r)
    assert len(group)==56
    for k,rr in group.items():assert sorted(r['seed'] for r in rr)==list(range(10)),k
    for case,b in CONDITIONS:
        for seed in range(10):
            rr=[r for r in runs if r['case']==case and r['budget']==b and r['seed']==seed]
            assert len(rr)==4 and len({json.dumps(r['initial_points']) for r in rr})==1
    return runs,callbacks,inputs,audits,raw_checks,raw_jobs

def summarize(runs):
    grouped=defaultdict(list)
    for r in runs:grouped[key(r)].append(r)
    summaries=[]
    for case,b in CONDITIONS:
        for method in METHODS:
            rr=grouped[case,b,method]; n=len(rr); ct=Counter(r['category'] for r in rr); h=ct['target_reached'];p=h/n
            rep=1 if p==1 else math.inf if p==0 else math.ceil(math.log(.01)/math.log1p(-p))
            complete=all(finite(r['reconstructed_total_s']) for r in rr)
            median=statistics.median(r['reconstructed_total_s'] for r in rr) if complete else None
            mean=statistics.mean(r['reconstructed_total_s'] for r in rr) if complete else None
            protocol=sum(r['protocol_failure'] for r in rr)
            ttstatus='protocol_failure' if protocol else 'missing_nlp_cost' if not complete else 'zero_observed_hits' if h==0 else 'available'
            tts=None if not complete or protocol else math.inf if h==0 else rep*median
            summaries.append({'case':case,'budget':b,'method':method,'n':n,'hits':h,'misses':ct['target_not_reached'],
                'execution_failures':ct['execution_failed'],'not_run':ct['not_run'],'protocol_failures':protocol,
                'success_rate':p,'observed_hits':sum(r['target_observed_within_budget'] for r in rr),
                'initial_hit_seeds':sum(r['initial_target_observed'] for r in rr),
                'terminal_only_hits':sum(r['target_first_at_undelivered_terminal'] and r['category']=='target_reached' for r in rr),
                'median_dfo_s':statistics.median(r['dfo_wall_s'] for r in rr),'mean_dfo_s':statistics.mean(r['dfo_wall_s'] for r in rr),
                'original_cost_complete_runs':sum(r['published_cost_complete'] for r in rr),
                'within_budget_cost_complete_runs':sum(r['within_budget_cost_complete'] for r in rr),
                'reconstructed_total_available_runs':sum(finite(r['reconstructed_total_s']) for r in rr),
                'median_reconstructed_s':median,'mean_reconstructed_s':mean,'runs_for_99pct':rep,'tts99_s':tts,'tts99_status':ttstatus,
                'recorded_callback_mean':statistics.mean(r['logged_callbacks'] for r in rr),
                'missing_cost_callback_count':sum(r['missing_within_budget_nlp_count'] for r in rr),
                'observed_best':min((r['best_observed_objective'] for r in rr if finite(r['best_observed_objective'])),default=None),
                'target':rr[0]['target']})
    return summaries


def group_runs(runs):
    groups=defaultdict(list)
    for r in runs: groups[key(r)].append(r)
    return groups

def group_lookup(summaries):
    return {key(r):r for r in summaries}

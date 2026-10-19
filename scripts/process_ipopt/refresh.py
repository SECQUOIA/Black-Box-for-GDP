"""Audit all original callbacks and add measured same-model rejection costs only."""
from pathlib import Path
import importlib.util, json, math, statistics, itertools, copy, shutil, subprocess
from collections import Counter, defaultdict

import analysis_core as a
ROOT = a.ROOT
OUT = a.OUT
BASE = Path(a.__file__)
NEW = ROOT / 'results/column_dynamic_box_ipopt/dantzig_column_dynamic_ipopt_20261015_205822_gG8bXK'
C30 = ROOT / 'results/cstr30_structural_rejections/dantzig_cstr30_structural_20261015_214202_pgve882p'

def domains(case):
    if case.startswith('cstr_'):
        n=int(case.split('_')[1]); return set(itertools.product(range(1,n+1), repeat=2))
    if case=='column':return set(itertools.product(range(7,16),range(1,10)))
    if case=='dynamic':return set(itertools.product(range(1,10),range(2,10)))
    return set(itertools.product(range(1,4),repeat=3))

def load():
    runs, events, inputs, audits, checks, jobs = a.load()
    original_runs=copy.deepcopy(runs)
    cost_tables={c:dict(v['rows']) for c,v in inputs.items()}
    supplement={}; overlap=[]; coverage=[]
    for c,p in [('cstr_30',C30/'structural_rejections.csv'),('column',NEW/'column/evaluations.csv'),('dynamic',NEW/'dynamic/evaluations.csv')]:
        rows=a.readcsv(p); table={a.point(r['point']):r for r in rows}
        assert len(rows)==len(table)
        missing=domains(c)-set(cost_tables[c])
        assert len(missing)=={'cstr_30':435,'column':17,'dynamic':35}[c]
        assert set(table)==(missing if c=='cstr_30' else domains(c))
        for pt,row in table.items():
            assert a.num(row['total_wall_s']) is not None and float(row['total_wall_s'])>0
            if pt in inputs[c]['rows']:
                old=inputs[c]['rows'][pt]
                assert a.yes(old['accepted'])==a.yes(row['accepted'])
                assert a.num(old['objective'])==a.num(row['objective'])
                overlap.append({'case':c,'point':pt,'accepted':a.yes(old['accepted']),'objective_equal':True,
                    'original_total_s':old['total_wall_s'],'new_total_s':row['total_wall_s'],'selected_time':'original'})
            else:
                assert not a.yes(row['accepted']) and a.num(row['objective']) is None
                assert row['termination']=='not_solved' and float(row['solve_wall_s'])==0
                assert not a.yes(row['solver_called'])
                if c=='cstr_30':assert pt[1]>pt[0]
                elif c=='column':assert pt[0]<8 or pt[1]>8
                else:assert not (pt[0]<pt[1] or pt==(9,9))
                cost_tables[c][pt]=row
                supplement[c,pt]={'case':c,'point':pt,'total_wall_s':float(row['total_wall_s']),
                    'source':p.relative_to(ROOT).as_posix(),'source_sha256':a.sha(p),'status':row['status']}
    combined=a.readcsv(C30/'combined_cstr30_900.csv')
    cmap={a.point(r['point']):r for r in combined}
    assert len(cmap)==len(combined)==900
    for pt,r in inputs['cstr_30']['rows'].items():
        for k,v in r.items():assert cmap[pt][k]==v,(pt,k)
    for c,table in cost_tables.items():
        assert set(table)==domains(c)
        assert all(a.num(r['total_wall_s']) is not None and float(r['total_wall_s'])>0 for r in table.values())
        coverage.append({'case':c,'domain_points':len(domains(c)),'original_rows':len(inputs[c]['rows']),
            'supplement_rows':len(table)-len(inputs[c]['rows']),'timed_rows':len(table),
            'accepted_rows':len(inputs[c]['values']),'missing_total_times':0})
        a.writecsv('cost_table_'+c+'.csv',[{**r,'cost_source':'original' if pt in inputs[c]['rows'] else 'supplement'} for pt,r in sorted(table.items())])
    byjob=defaultdict(list); added=[]
    for e in events:
        e['original_historical_nlp_s']=e['historical_nlp_s']
        if e['within_budget'] and e['historical_nlp_s'] is None:
            s=supplement[e['case'],e['point']]
            assert not e['accepted'] and e['objective'] is None
            e['historical_nlp_s']=s['total_wall_s'];e['time_source']=s['source']
            added.append({'job_id':e['job_id'],'index':e['index'],**s})
        else:e['time_source']='original' if e['within_budget'] else 'not_evaluated_protocol_error'
        byjob[e['job_id']].append(e)
    for r in runs:
        es=byjob[r['job_id']]; valid=[e for e in es if e['within_budget']]
        assert all(e['historical_nlp_s'] is not None for e in valid)
        cumulative=0
        for e in es:
            if e['within_budget']:cumulative+=e['historical_nlp_s']
            e['known_cumulative_nlp_s']=cumulative;e['missing_cumulative_nlp_count']=0
        r['historical_nlp_known_within_budget_s']=sum(e['historical_nlp_s'] for e in valid)
        r['historical_accepted_cost_s']=sum(e['historical_nlp_s'] for e in valid if e['accepted'])
        r['historical_unaccepted_cost_s']=sum(e['historical_nlp_s'] for e in valid if not e['accepted'])
        r['missing_within_budget_nlp_count']=0;r['within_budget_cost_complete']=True
        r['reconstructed_total_s']=None if r['protocol_failure'] else r['dfo_wall_s']-r['lookup_wall_s']+r['historical_nlp_known_within_budget_s']+r['dynamic_preparation_s']
        r['time_status']='protocol_failure' if r['protocol_failure'] else 'complete'
        r['supplemented_callback_count']=sum(e['original_historical_nlp_s'] is None for e in valid)
        r['supplemental_cost_s']=sum(e['historical_nlp_s'] for e in valid if e['original_historical_nlp_s'] is None)
        assert math.isclose(sum(e['lookup_s'] for e in es),r['lookup_wall_s'],rel_tol=1e-12,abs_tol=1e-10)
    immutable=['category','execution_status','protocol_failure','first_hit_callback','first_returned_hit_callback','target','best_observed_objective','initial_points','dfo_wall_s','lookup_wall_s']
    for old,new in zip(original_runs,runs):
        for k in immutable:assert old[k]==new[k]
    assert sum(e['historical_nlp_s'] is None and e['within_budget'] for e in events)==0
    assert not any(not e['within_budget'] for e in events)
    sums=a.summarize(runs)
    summary={'repository_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'replacement_policy':'All 140 BAM slots use the two pinned native-budget reruns; other 420 slots are unchanged.',
        'runs':len(runs),'logged_callbacks':len(events),'in_budget_callbacks':sum(e['within_budget'] for e in events),
        'original_same_row_checks':len(checks),'original_row_objective_status_time_mismatches':0,
        'supplemented_callbacks':len(added),'remaining_in_budget_time_gaps':0,
        'unevaluated_out_of_budget_callbacks':sum(not e['within_budget'] for e in events),
        'protocol_failed_runs':sum(r['protocol_failure'] for r in runs),
        'timed_protocol_valid_runs':sum(r['reconstructed_total_s'] is not None for r in runs),
        'outcomes':dict(Counter(r['category'] for r in runs)),
        'tts_statuses':dict(Counter(r['tts99_status'] for r in sums)),
        'cost_table_coverage':coverage,'overlap_rows_verified':len(overlap),
        'primary_cost_policy':'Keep original same-row process costs; supplement only unmeasured structural exclusions from new same-model measurements. Dynamic original one-time template cost is retained.',
        'time_interpretation':'Retrospective fixed-path reconstruction, not online optimizer-NLP measurements',
        'no_zero_fill_no_cross_size_borrow_no_retry_selection':True,'optimizer_or_process_solver_calls':0}
    a.savejson(OUT/'timing_audit.json',summary)
    a.writecsv('timing_coverage.csv',coverage);a.writecsv('overlap_validation.csv',overlap)
    a.writecsv('supplemented_callbacks.csv',added);a.writecsv('run_results.csv',runs)
    a.writecsv('group_summary.csv',sums);a.writecsv('callbacks.csv',events)
    a.writecsv('protocol_failures.csv',[r for r in runs if r['protocol_failure']])
    a.savejson(OUT/'source_manifest.json',{'analysis_sha256':a.sha(Path(__file__)),'original_analysis_sha256':a.sha(BASE),'sources':a.SOURCES,'summary':summary})
    return runs,events,inputs,cost_tables,sums,summary

if __name__=='__main__':
    runs,events,inputs,costs,sums,summary=load()
    print(json.dumps(summary,indent=2))
    for r in sums:
        print(r['case'],r['budget'],r['method'],r['hits'],r['median_reconstructed_s'],r['tts99_s'],r['tts99_status'])

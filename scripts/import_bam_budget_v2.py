"""Verify the two pinned BAM reruns; import provenance and ledgers without solvers.

Run: python scripts/import_bam_budget_v2.py --archive-dir /path/to/returned/zips
The immutable original runs remain archived; this batch replaces all 140 BAM slots.
"""
import argparse
from collections import Counter
import gzip
import importlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BATCHES = {
    'cstr': ('ipopt_dfo_cstr_20261015_223017_ncd_12gx',
             '2b0c56bdc67297661ebb6ab81ed60ca1df10788541bd39e67fcd391f4a48f570',
             '1eb297dd92fbd379193f6fda91775420a78680cdc348487343b5dab3c06567e0', 60),
    'non_cstr': ('ipopt_dfo_non_cstr_20261015_223138_r3ifrgaq',
             '58ff6a845541e4e8d2cb097e05ffacb4b5500d6dbebf1d95c1a255b9315c7ce1',
             '783652fc99778ed6f02e4ae4d1ce7802ee7fcefea8d57494466f8ce7bf753c8f', 80),
}
OLD = {'cstr': 'ipopt_dfo_cstr_20261015_174637_r1dzn5tk',
       'non_cstr': 'ipopt_dfo_non_cstr_20261015_172428_o671edu_'}


def verify_batch(kind, archive, output):
    # Isolate pinned historical-importer constants from other imports/tests.
    module_spec = importlib.util.spec_from_file_location(
        '_bam_validation_' + kind, Path(__file__).with_name('import_ipopt_dfo_' + kind + '.py'))
    helper = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(helper)
    runner = helper.runner
    require = helper.require
    name, digest, package_digest, count = BATCHES[kind]
    helper.RETURN_NAME, helper.RETURN_SHA256 = name, digest
    helper.PACKAGE = ROOT / 'results/runners' / f'bam_{kind}_budget_v2.zip'
    helper.PACKAGE_SHA256 = package_digest
    with tempfile.TemporaryDirectory() as temporary:
        directory, hashes, package_files = helper.extract_verified(archive, Path(temporary))
        reproduction = directory / 'reproduction'
        plan = runner.read(reproduction / 'plan.json')
        expected = [s for s in importlib.import_module('build_ipopt_dfo_' + kind).plan() if s['method'] == 'bam']
        require(plan == expected and len(plan) == count, 'Plan/seed/settings mismatch')
        require({p.name for p in (directory/'jobs').iterdir()} == {s['job_id'] for s in plan}, 'Incomplete jobs')
        require(runner.read(directory/'availability.json') == {'data_errors': {}, 'environment_errors': {}}, 'Preflight errors')
        tables = {c:runner.load_table(reproduction,c)[0] for c in runner.CASES}
        old = ROOT/'results'/OLD[kind]
        for case in tables:
            require((reproduction/'inputs'/case/'evaluations.csv').read_bytes() ==
                    (old/'inputs'/case/'evaluations.csv').read_bytes(), 'Changed IPOPT oracle')
        old_jobs = {r['job_id']:r for r in runner.read(old/'job_metadata.json')}
        reported = {r['job_id']:r for r in helper.rows(directory/'runs.csv')}
        require(len(reported)==count, 'Report size mismatch')
        cpu=runner.read(directory/'cpu_selection.json')
        selected=cpu['selected']['cpu']
        require(cpu['selected']['effective_cpus']==[selected] and selected not in cpu['excluded_cpus'], 'CPU selection mismatch')
        require(not set(map(int,cpu['selected']['thread_siblings_list'].split(','))) & set(cpu['excluded_cpus']), 'Physical-core overlap')
        metadata=[]
        categories=Counter()
        callback_count=0
        for spec in plan:
            job=directory/'jobs'/spec['job_id']
            budget=spec['budget']
            require(runner.read(job/'spec.json')==spec, 'Job spec mismatch')
            require(spec['starts']==old_jobs[spec['job_id']]['spec']['starts'], 'Changed paired initial design')
            require(runner.bam_native_budget(spec), 'Legacy stop policy in rerun')
            events=helper.strict_jsonl(job/'callbacks.jsonl')
            result=runner.read(job/'result.json')
            settings=runner.read(job/'actual_settings.json')
            runtime=runner.read(job/'runtime.json')
            started=runner.read(job/'started.json')
            require(runtime['host']=='dantzig.ecn.purdue.edu' and started['effective_cpu']==[selected], 'Host/affinity mismatch')
            require(all(runtime['versions'][k].split('+')[0]==v for k,v in runner.VERSIONS['bam'].items()), 'Version mismatch')
            require(len(events)==budget==result['callback_count'], 'Budget not exactly honored')
            require(not (job/'budget_overruns.jsonl').exists() or not (job/'budget_overruns.jsonl').read_text().strip(), 'Guard recorded overrun')
            for i,event in enumerate(events,1):
                helper.validate_callback(event,spec,tables[spec['case']],i)
            helper.validate_settings(spec,settings,events)
            require(all(x['elapsed_s']<=y['elapsed_s'] for x,y in zip(events,events[1:])), 'Nonmonotonic clock')
            require(result['status']=='budget_completed' and result['error'] is None, 'Backend failure')
            require(result['worker_returncode']==0 and result['watchdog_timeout'] is False, 'Worker interrupted')
            native=result['algorithm_result']
            require(native['status']==35 and native['success'] is True and native['nfev']==budget-3, 'Native budget termination mismatch')
            require(0<=sum(e['lookup_wall_s'] for e in events)<=result['dfo_wall_s']<=result['worker_process_wall_s'], 'Invalid timing identity')
            require(all(e['value_returned_to_optimizer'] and e['callback_exit']=='return' for e in events), 'Undelivered value')
            values=[e['raw_objective'] for e in events if e['accepted']]
            best=min(values) if values else None
            target=min(float(r['objective']) for r in tables[spec['case']].values() if r['accepted']=='True')
            hit=best is not None and abs(best-target)<=1e-5*max(1,abs(target))
            category='target_reached' if hit else 'target_not_reached' if best is not None else 'execution_failed'
            report=reported[spec['job_id']]
            require(report['category']==category and helper.number(report,'best_accepted_objective')==best and
                    helper.number(report,'table_accepted_minimum')==target, 'Reported outcome mismatch')
            require(int(report['callback_count'])==budget and helper.number(report,'dfo_wall_s')==result['dfo_wall_s'], 'Report clock/count mismatch')
            require(math.isclose(helper.number(report,'lookup_wall_s'),sum(e['lookup_wall_s'] for e in events),abs_tol=1e-10), 'Lookup total mismatch')
            missing=sum(e['selected_attempt_nlp_s'] is None for e in events)
            require(int(report['missing_nlp_times'])==missing and report['nlp_time_available']==str(not missing), 'Missing timing masked')
            categories[category]+=1
            callback_count+=len(events)
            metadata.append({'job_id':spec['job_id'],'spec':spec,'settings':settings,'runtime':runtime,'started':started,'result':result})
        originals={n:(directory/n).read_bytes() for n in helper.TABLES}
        runner.summarize(directory)
        for n,b in originals.items():
            require((directory/n).read_bytes()==b, 'Regenerated table differs: '+n)
        audit={'batch':name,'archive_sha256':digest,'package_sha256':package_digest,'slots':count,
               'categories':dict(categories),'callbacks':callback_count,'budget_overruns':0,'undelivered_terminal_values':0,
               'objective_status_original_cost_mismatches':0,'package_files_verified':package_files,
               'all_paired_starts_preserved':True,'native_status':35,'original_inputs_preserved':True,
               'missing_structural_times_policy':'Joined later from same-model full-box/structural timing supplements.',
               'scope':'All BAM seeds replaced; no best-of-old/new selection.'}
        destination=output/name
        destination.mkdir(parents=True,exist_ok=True)
        for n in ['runs.csv','summary.csv','summary.json','inputs_report.csv','inputs_report.json','run.json','cpu_selection.json','availability.json']:
            if (directory/n).exists():
                shutil.copy2(directory/n,destination/n)
        with gzip.GzipFile(filename='',mode='wb',fileobj=(destination/'callbacks.csv.gz').open('wb'),mtime=0) as stream:
            stream.write((directory/'callbacks.csv').read_bytes())
        for case in tables:
            inp=destination/'inputs'/case
            inp.mkdir(parents=True,exist_ok=True)
            for p in (reproduction/'inputs'/case).iterdir():
                if p.is_file():
                    shutil.copy2(p,inp/p.name)
        (destination/'job_metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
        (destination/'audit.json').write_text(json.dumps(audit,indent=2)+'\n')
        (destination/'raw_archive_members.json').write_text(json.dumps(hashes,indent=2)+'\n')
        archived=ROOT/'results/archives'/archive.name
        if archive.resolve()!=archived.resolve():
            shutil.copy2(archive,archived)
        return audit


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-dir',type=Path,default=ROOT/'results/archives')
    args=parser.parse_args()
    audits=[verify_batch(kind,args.archive_dir/(data[0]+'.zip'),ROOT/'results/bam_budget_v2') for kind,data in BATCHES.items()]
    print(json.dumps(audits,indent=2))

if __name__=='__main__':
    main()

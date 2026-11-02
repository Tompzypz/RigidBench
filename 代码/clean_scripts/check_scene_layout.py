"""Check public scene interfaces without starting a solver or Blender."""
from pathlib import Path
import argparse
import ast
import concurrent.futures
import json
import os
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--json',type=Path)
    a=p.parse_args()
    registry=json.loads((ROOT/'scripts/scene_registry.json').read_text())['scenes']
    tasks=[];errors=[]
    for row in registry:
        folder=ROOT/row['directory']
        if not (folder/'README.md').is_file():errors.append(str(folder/'README.md'))
        metadata=json.loads((folder/'entrypoints.json').read_text())
        for role in ['simulate','render','build_pcve']:
            path=folder/f'{role}_{row["scene"]}.py'
            if not path.is_file():errors.append(str(path));continue
            ast.parse(path.read_text(),filename=str(path))
            assert 'PCVE_UNIFIED_ENTRY_BEGIN' in path.read_text(),path
            assert metadata['entrypoints'][role]['file']==path.name
            tasks.append((row['scene'],role,path))
        for workflow in metadata.get('workflows',{}).values():
            assert (folder/workflow['file']).is_file(),workflow
    with tempfile.TemporaryDirectory(prefix='pcve_entry_check_') as temporary:
        scratch=Path(temporary)
        def check(item):
            name,role,path=item;out=scratch/name/role
            env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
            help_result=subprocess.run([sys.executable,str(path),'--help'],capture_output=True,text=True,env=env,timeout=30)
            dry=subprocess.run([sys.executable,str(path),'--out-root',str(out),'--dry-run'],capture_output=True,text=True,env=env,timeout=30)
            result={'scene':name,'role':role,'help_return_code':help_result.returncode,'plan_return_code':dry.returncode,'output_created':out.exists()}
            if dry.returncode:result['error']=dry.stderr[-2000:]
            else:
                plan=json.loads(dry.stdout)
                assert plan['dry_run'] and plan['entry']==role and plan['scene']==name
                assert '--dry-run' not in plan['command']
                result['plan']=plan
            return result
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(check,tasks))
        errors += [r for r in results if r['help_return_code'] or r['plan_return_code'] or r['output_created']]
        assert not any(scratch.iterdir()),'A read-only plan created directories'
    report={'passed':not errors,'scenes':len(registry),'public_entries':len(tasks),'errors':errors,'entries':results,
            'scope':'Public CLI structure and read-only execution planning; original physical and render implementations are not executed.'}
    if a.json:
        a.json.parent.mkdir(parents=True,exist_ok=True)
        a.json.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['passed','scenes','public_entries','errors']},indent=2))
    raise SystemExit(0 if report['passed'] else 1)

if __name__=='__main__':main()

"""Build one source and five independent PCVE edits, rendering only requested frames."""
# PCVE_UNIFIED_ENTRY_BEGIN

# Resolve the shared scripts directory, then this scene's module folders.
import sys as _clean_sys
from pathlib import Path as _CleanPath
_clean_scene_dir = _CleanPath(__file__).resolve().parent
_scripts_dir = _clean_scene_dir.parents[1]
_PCVE_PROJECT_ROOT = next(p for p in _clean_scene_dir.parents if (p / "assets").is_dir())
if str(_scripts_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_scripts_dir))
if str(_clean_scene_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_clean_scene_dir))
# Shared modules live in scripts/; scene-local modules live in this directory and
# its physics/, appearance/ and tools/ subdirectories.
for _scene_sub in ("", "physics", "appearance", "tools"):
    _scene_sub_dir = _clean_scene_dir / _scene_sub if _scene_sub else _clean_scene_dir
    if _scene_sub_dir.is_dir() and str(_scene_sub_dir) not in _clean_sys.path:
        _clean_sys.path.insert(1, str(_scene_sub_dir))
# PCVE_UNIFIED_ENTRY_END

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from runtime_support import HERE, MODELS, python_for, render_prefix
from scene_config import defaults, merge, validate, write_json
from simulate_soccer_step_collision import simulate
from validate_soccer_step_collision import validate_cache
from edit_vocab import EDIT_CASES, VOCAB
import pcve_edit_dsl as dsl

SOURCE='soccer_step_collision_baseline'

def edit_record(instruction):
    edit=dsl.parse(instruction,VOCAB)
    override={'physics':dsl.to_scenario_override(edit,VOCAB)}
    if isinstance(edit,dsl.DeleteEdit):
        diff={f'presence ({edit.object_id})':{'from':'present','to':'absent'}}
        summary=f'{edit.object_id} is absent from the physical simulation and rendered scene.'
    else:
        diff={f'{edit.property_name} ({edit.object_id})':dict(
            old=dsl.baseline_value_for(edit,VOCAB),new=dsl.resolved_to_value(edit,VOCAB))}
        summary=dsl.summarize_set_edit(edit,VOCAB)
        if dsl.is_timed(edit):
            summary=(f'{summary} The ball is relaunched with the edited speed and then rolls on '
                     'from that state.')
    diff['timing']=dsl.timing_diff(edit,VOCAB)
    return dict(edit_dsl=instruction,applies_from_frame=dsl.starts_at_frame(edit),edit_summary=summary,
        physics_diff=diff,prompts=dsl.make_prompts(edit,VOCAB),scenario_override=override)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out-root',type=Path,default=HERE/'outputs/suite')
    p.add_argument('--mode',choices=('build','preview','keyframes','animation'),default='keyframes')
    p.add_argument('--simulate-only',action='store_true'); p.add_argument('--render-only',action='store_true')
    p.add_argument('--cases',nargs='+'); p.add_argument('--keyframes',nargs='+',type=int)
    p.add_argument('--preview-frame',type=int,default=72)
    p.add_argument('--resolution',nargs=2,type=int,default=[960,540]); p.add_argument('--samples',type=int,default=32)
    p.add_argument('--threads',type=int,default=4); p.add_argument('--engine',choices=('cycles','eevee'),default='cycles')
    p.add_argument('--device',choices=('cpu','auto'),default='cpu'); p.add_argument('--blender',type=Path)
    p.add_argument('--render-python',type=Path,default=python_for('render'))
    args=p.parse_args()
    if args.simulate_only and args.render_only: raise ValueError('Conflicting modes')
    all_cases=[(SOURCE,None),*EDIT_CASES]
    if args.cases and set(args.cases)-{k for k,_ in all_cases}: raise ValueError('Unknown case ID')
    root=args.out_root.resolve(); path=root/'suite_manifest.json'
    s=defaults(); s['render'].update(resolution=args.resolution,samples=args.samples); validate(s)
    manifest=json.loads(path.read_text(encoding='utf-8')) if path.exists() else dict(
        schema_version=1,suite_name='pcve_soccer_step_collision',source_case_id=SOURCE,
        duration_sec=4.,fps=24,total_frames=96,source=None,edits=[])
    # The manifest is merged across runs; drop entries for cases the
    # vocabulary no longer defines so renamed edits leave nothing behind.
    keep={cid for cid,_ in all_cases}
    manifest['edits']=[r for r in manifest['edits'] if r['case_id'] in keep]
    for case_id,instruction in all_cases:
        if args.cases and case_id not in args.cases: continue
        folder=root/'cases'/case_id; folder.mkdir(parents=True,exist_ok=True)
        info=edit_record(instruction) if instruction else {}
        scenario=merge(s,info.get('scenario_override',{})); validate(scenario)
        record=dict(case_id=case_id,kind='edit' if instruction else 'source',case_dir=str(folder),**info)
        if instruction:
            write_json(folder/'scenario_overrides.json',info['scenario_override'])
            write_json(folder/'prompts.json',dict(source_case_id=SOURCE,
                **{k:info[k] for k in ('edit_dsl','edit_summary','applies_from_frame','physics_diff','prompts')}))
            manifest['edits']=[r for r in manifest['edits'] if r['case_id']!=case_id]+[record]
        else:
            record['description']={'zh':'室内，足球滚过低矮的木地板台阶，撞击台面上静止的篮球。',
                'en':'Indoors, a soccer ball rolls up a low wooden-floor curb and strikes a basketball resting on the raised floor.'}
            write_json(folder/'prompts.json',record['description']); manifest['source']=record
        print('[suite] '+case_id,flush=True); write_json(path,manifest)
        try:
            cache=folder/'physics_transforms.json'
            if args.render_only:
                data=json.loads(cache.read_text(encoding='utf-8')); validate_cache(data)
                if data['scenario']!=scenario: raise ValueError('Cache differs from requested scenario; resimulate')
            else:
                data=simulate(scenario); validate_cache(data); write_json(cache,data)
            write_json(folder/'scenario_input.json',scenario)
            write_json(folder/'simulation_metrics.json',data['quality'])
            record['metrics']=data['quality']; record['status']='simulated'
            if not instruction and not (data['quality']['climbed_step'] and data['quality']['ball_collision_observed']):
                raise RuntimeError('Baseline must climb and then collide')
            if not args.simulate_only:
                command=render_prefix(args,HERE/'render_soccer_step_collision.py')
                command+=['--physics-json',str(cache),'--out-dir',str(folder),'--mode',args.mode,
                    '--resolution',*map(str,args.resolution),'--samples',str(args.samples),
                    '--engine',args.engine,'--device',args.device,'--threads',str(args.threads),
                    '--preview-frame',str(args.preview_frame)]
                if args.keyframes: command+=['--keyframes',*map(str,args.keyframes)]
                with (folder/'render.log').open('w',encoding='utf-8') as log:
                    subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
                record['status']='built' if args.mode=='build' else 'rendered'
                validation=json.loads((folder/'render_validation.json').read_text(encoding='utf-8'))
                record['render_validation']={k:v for k,v in validation.items() if k!='frames'}
            record['outputs']={p.stem:str(p) for p in folder.iterdir() if p.suffix in ('.json','.blend','.png','.mp4')}
            write_json(folder/'run_status.json',dict(status=record['status'],valid=True,simulation_signature=data['simulation_signature']))
        except Exception:
            record['status']='failed'; write_json(path,manifest); raise
        write_json(path,manifest)
    print(path,flush=True)

if __name__=='__main__': main()

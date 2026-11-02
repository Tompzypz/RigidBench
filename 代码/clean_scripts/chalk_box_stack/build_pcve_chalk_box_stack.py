"""One fixed source and five independent PCVE edits for the chalk-box stack."""

# Load this seven-file scene bundle and the reference common scripts.
import sys as _clean_sys
from pathlib import Path as _CleanPath
_clean_scene_dir = _CleanPath(__file__).resolve().parent
_clean_scripts_dir = _clean_scene_dir.parent
_PCVE_PROJECT_ROOT = next(p for p in _clean_scene_dir.parents if (p / "assets").is_dir())
if str(_clean_scripts_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_clean_scripts_dir))
if str(_clean_scene_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_clean_scene_dir))
import edit_vocab as _clean_scene_bundle
_clean_scene_bundle.install_scene_support()




from pathlib import Path
import argparse,json,math,shutil,sys,subprocess,time,hashlib
import pcve_edit_dsl as dsl
from scene_support.chalk_box_stack.scene_config import defaults,merge,validate
from scene_support.chalk_box_stack.scene_geometry import COUNT
from chalk_box_stack.edit_vocab import DESCRIPTION,EDIT_CASES,VOCAB
from scene_support.chalk_box_stack.runtime_support import python_for
from scene_support.chalk_box_stack.cache_contract import validate_cache
ROOT=_PCVE_PROJECT_ROOT
SOURCE_CASE_ID='chalk_box_stack_baseline'
BODIES=('eraser',)+tuple(f'box_{i}' for i in range(COUNT))
# An edit has to move a body far enough to see; the ortho frame covers about
# 1.6 m, so two centimetres is already a couple of pixels.
MIN_VISIBLE_SHIFT_M=.02

from pcve_scene_runtime import add_build_arguments, render_prefix, append_render_options, implementation_hashes

def write_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')

def fingerprint(s,args):
    source=implementation_hashes(Path(__file__).parent)
    asset_root=ROOT/'assets'
    source.update({str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in asset_root.rglob('*') if p.is_file() and p.suffix.lower() in {'.glb','.gltf','.obj','.fbx','.stl','.jpg','.jpeg','.png','.hdr','.exr'}})
    return hashlib.sha256(json.dumps(dict(scenario=s,implementation=source,engine=args.engine,device=args.device,preview_frame=args.preview_frame,mode=args.mode,simulation_only=args.simulate_only),sort_keys=True).encode()).hexdigest()

def standardize_render_outputs(folder,has_overrides):
    files=dict(video='video.mp4',ground_truth='ground_truth_transforms.json',scenario_metadata='scenario_metadata.json')
    if has_overrides:files['scenario_overrides']='scenario_overrides.json'
    for name in files.values():
        if not (folder/name).exists():raise FileNotFoundError(f'Missing output: {folder/name}')
    return {key:str((folder/name).resolve()) for key,name in files.items()}

def run_logged(command,log_path,args):
    """Run one external step the way the older scenes do: quiet log by default,
    console output with --verbose-render."""
    if args.verbose_render:subprocess.run(command,check=True);return
    log_path.parent.mkdir(parents=True,exist_ok=True)
    with log_path.open('w',encoding='utf-8') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)

def clean_stale(out_root,keep_ids):
    """Drop case directories that are no longer part of this suite."""
    cases_dir=out_root/'cases'
    if not cases_dir.exists():return
    for path in sorted(cases_dir.iterdir()):
        if path.is_dir() and path.name not in keep_ids:
            print(f'[suite] remove stale case directory {path}');shutil.rmtree(path)

def commands_for(folder,args):
    """The simulation and render commands a case would run, in that order."""
    sim=[str(args.physics_python),str(Path(__file__).with_name('simulate_chalk_box_stack.py')),'--out',str(folder/'physics_transforms.json'),'--scenario-json',str(folder/'scenario_input.json')]
    script=Path(__file__).with_name('render_chalk_box_stack.py')
    render=render_prefix(args, script)
    render+=['--physics-json',str(folder/'physics_transforms.json'),'--out-dir',str(folder),'--engine',args.engine,'--device',args.device,'--samples',str(args.samples),'--resolution',*map(str,args.resolution),'--mode',args.mode]
    return sim,append_render_options(render,args)

def run_case(folder,s,args):
    validate(s)
    if args.dry_run:
        sim,render=commands_for(folder,args)
        for command in (([] if args.render_only else [sim])+([] if args.simulate_only else [render])):
            print(subprocess.list2cmdline(command))
        return dict(status='dry_run',valid=False,quality=dict(valid=False))
    folder.mkdir(parents=True,exist_ok=True);fp=fingerprint(s,args)
    status_file=folder/'run_status.json';required=['physics_transforms.json','simulation_metrics.json','motion_summary.json']
    if not args.simulate_only:required+=['preview.png','ground_truth_transforms.json','scenario_metadata.json','render_validation.json','chalk_box_stack.blend']+(['video.mp4'] if args.mode=='animation' else [])
    if args.skip_existing and status_file.exists():
        status=json.loads(status_file.read_text(encoding='utf-8'))
        if status.get('fingerprint')==fp and status.get('valid') and all((folder/name).exists() for name in required):return dict(status,status='skipped_existing')
    sim,render=commands_for(folder,args)
    if args.render_only:
        data=json.loads((folder/'physics_transforms.json').read_text(encoding='utf-8'))
        validate_cache(data,s)
        write_json(folder/'scenario_input.json',s)
    else:
        write_json(folder/'scenario_input.json',s)
        run_logged(sim,folder/'simulation.log',args)
        data=json.loads((folder/'physics_transforms.json').read_text(encoding='utf-8'))
        validate_cache(data,s)
    if not args.simulate_only:run_logged(render,folder/'render.log',args)
    status=dict(status='completed',valid=True,simulation_only=args.simulate_only,render_mode=args.mode,fingerprint=fp,quality=data['quality'])
    write_json(status_file,status);return status

def edit_record(case):
    """Parse a case's DSL once and derive the published record from it."""
    edit=dsl.parse(case.dsl,VOCAB)
    if isinstance(edit,dsl.DeleteEdit):
        diff={f'presence ({edit.object_id})':{'from':'present','to':'absent'}}
    elif isinstance(edit,dsl.AddEdit):
        diff={'presence':{'from':'absent','to':'present'},'position':dsl.add_position_diff(edit,VOCAB)}
    else:
        values={'from':dsl.baseline_value_for(edit,VOCAB),'to':dsl.resolved_to_value(edit,VOCAB)}
        # A ``TO`` edit names an absolute value and has no multiplier; saying so
        # is better than publishing a null.
        if edit.factor is not None:values['factor']=edit.factor
        diff={f'{edit.property_name} ({edit.object_id})':values}
    diff['timing']=dsl.timing_diff(edit,VOCAB)
    return edit,dict(case_id=case.case_id,source_case_id=SOURCE_CASE_ID,edit_dsl=case.dsl,
        edit_summary=case.summary,applies_from_frame=dsl.starts_at_frame(edit),
        physics_diff=diff,prompts=dsl.make_prompts(edit,VOCAB),
        overrides={'physics':dsl.to_scenario_override(edit,VOCAB)})

def check_case(case_id,edit,data,baseline):
    """Reject a take that is not a finite simulation of the edit it claims."""
    frames=data['frames']
    for frame in frames:
        for name in BODIES:
            state=frame[name]
            values=[*state['location'],*state['quaternion_xyzw'],*state['linear_velocity'],*state['angular_velocity']]
            if not all(math.isfinite(value) for value in values):
                raise RuntimeError(f'{case_id}: non-finite state at frame {frame["frame_index"]} ({name})')
    shift=max(math.dist(a[name]['location'],b[name]['location'])
              for a,b in zip(frames,baseline['frames']) for name in BODIES)
    if shift<MIN_VISIBLE_SHIFT_M:
        raise RuntimeError(f'{case_id}: no body moves more than {shift:.3f} m away from the source take')
    start=dsl.starts_at_frame(edit)
    if dsl.is_timed(edit):
        early=[{name:frame[name]['location'] for name in BODIES} for frame in frames[:start-1]]
        source=[{name:frame[name]['location'] for name in BODIES} for frame in baseline['frames'][:start-1]]
        if early!=source:
            raise RuntimeError(f'{case_id}: frames before {start} must reproduce the source take exactly')
    return {'max_shift_m':round(shift,4),'timed_events':data['quality'].get('timed_events',[])}

def parser():
    render=defaults()['render']
    p=argparse.ArgumentParser();p.add_argument('--out-root',type=Path,default=ROOT/'renders/pcve_chalk_box_stack_suite')
    p.add_argument('--physics-python',type=Path,default=python_for('physics'));p.add_argument('--render-python',type=Path,default=python_for('render'));p.add_argument('--blender',type=Path)
    p.add_argument('--duration-sec',type=float,default=render['duration_sec']);p.add_argument('--fps',type=int,default=render['fps'])
    p.add_argument('--samples',type=int,default=render['samples']);p.add_argument('--resolution',type=int,nargs=2,default=render['resolution']);p.add_argument('--engine',choices=('eevee','cycles'),default='cycles');p.add_argument('--device',choices=('auto','cpu'),default='auto');p.add_argument('--mode',choices=('preview','animation'),default='animation')
    p.add_argument('--simulate-only',action='store_true');p.add_argument('--render-only',action='store_true');p.add_argument('--skip-existing',action='store_true');p.add_argument('--cases',nargs='+')
    p.add_argument('--dry-run',action='store_true',help='Print the commands each case would run and stop.')
    p.add_argument('--verbose-render',action='store_true',help='Stream simulation and render output to the console.')
    p.add_argument('--clean-stale-cases',action='store_true',help='Delete case directories that are no longer part of this suite.')
    return add_build_arguments(p)

def main():
    args=parser().parse_args();args.out_root=args.out_root.resolve()
    if args.render_only and args.simulate_only:raise ValueError('Conflicting execution modes')
    cases=EDIT_CASES
    if args.cases:
        unknown=set(args.cases)-{SOURCE_CASE_ID,*[case.case_id for case in cases]}
        if unknown:raise ValueError(f'Unknown cases: {unknown}')
        cases=[case for case in cases if case.case_id in args.cases]
    source=defaults();source['render'].update(fps=args.fps,duration_sec=args.duration_sec,resolution=args.resolution,samples=args.samples)
    validate(source)
    if args.dry_run:
        for case_id,instruction in [(SOURCE_CASE_ID,None),*[(case.case_id,case.dsl) for case in cases]]:
            scenario=source
            if instruction:
                scenario=merge(source,{'physics':dsl.to_scenario_override(dsl.parse(instruction,VOCAB),VOCAB)})
            print(f'[suite] {case_id}',flush=True)
            run_case(args.out_root/'cases'/case_id,scenario,args)
        return
    if args.clean_stale_cases:clean_stale(args.out_root,{SOURCE_CASE_ID,*[case.case_id for case in EDIT_CASES]})
    manifest=dict(schema_version=3,suite_name='pcve_chalk_box_stack_suite',
        description='One source and five single-variable edits of the eraser and carton friction; outcomes are measured, not scripted.',
        baseline_physics=source['physics'],total_frames=round(args.fps*args.duration_sec),resolution=args.resolution,
        fps=args.fps,duration_sec=args.duration_sec,samples=args.samples,edit_count=len(cases),
        physical_duration_sec=args.duration_sec,playback_duration_sec=args.duration_sec,sample_fps=args.fps,slow_motion=1,source=None,edits=[],cases=[])
    path=args.out_root/'suite_manifest.json'
    baseline=None
    for i,case in enumerate([None,*cases]):
        case_id=case.case_id if case else SOURCE_CASE_ID
        folder=args.out_root/'cases'/case_id;s=source
        record=dict(case_id=case_id,kind='edit' if case else 'source',seed=9400+i,case_dir=str(folder.resolve()),status='pending')
        edit=None
        if case:
            edit,info=edit_record(case)
            override=info['overrides'];s=merge(source,override)
            record.update({key:value for key,value in info.items() if key!='overrides'})
            record.update(scenario_overrides_json=str((folder/'scenario_overrides.json').resolve()),
                          prompts_json=str((folder/'prompts.json').resolve()))
            write_json(folder/'scenario_overrides.json',override)
            write_json(folder/'prompts.json',{'schema_version':2,**{key:info[key] for key in
                ('case_id','source_case_id','edit_dsl','edit_summary','applies_from_frame','physics_diff','prompts')}})
            manifest['edits'].append(record)
        else:
            record['description']=DESCRIPTION;manifest['source']=record
            write_json(folder/'prompts.json',dict(schema_version=1,case_id=case_id,kind='source',prompts=DESCRIPTION))
        write_json(path,manifest);print(f'[suite] {case_id}',flush=True);start=time.perf_counter()
        try:
            record.update(run_case(folder,s,args))
            if not args.dry_run:
                data=json.loads((folder/'physics_transforms.json').read_text(encoding='utf-8'))
                if case is None:
                    baseline=data
                    # The source take is what every edit is measured against, so
                    # its own two gates stay exactly as they were.
                    if not record['quality']['hit_stack']:raise RuntimeError('Baseline did not strike the stack')
                    if not record['quality']['upper_stack_preserved']:raise RuntimeError('Baseline upper stack did not stay upright')
                    record['check']={'max_shift_m':0.0,'timed_events':[]}
                else:
                    record['check']=check_case(case_id,edit,data,baseline)
            if not args.dry_run and not args.simulate_only and args.mode=='animation':record['outputs']=standardize_render_outputs(folder,bool(case))
            else:record['outputs']={key:str((folder/name).resolve()) for key,name in [('physics','physics_transforms.json'),('scenario_input','scenario_input.json'),('preview','preview.png'),('ground_truth','ground_truth_transforms.json')] if (folder/name).exists()}
        except Exception:
            record['status']='failed';write_json(path,manifest);raise
        record['elapsed_sec']=round(time.perf_counter()-start,3);manifest['cases'].append(record);write_json(path,manifest)

if __name__=='__main__':main()

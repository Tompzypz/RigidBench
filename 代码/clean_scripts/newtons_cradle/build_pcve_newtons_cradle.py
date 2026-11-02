"""PCVE suite with one source and height/restitution edits."""

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
import argparse,json,shutil,sys,subprocess,time,hashlib
import pcve_edit_dsl as dsl
from scene_support.newtons_cradle.scene_config import defaults,merge,validate
from scene_support.newtons_cradle.runtime_support import python_for
from newtons_cradle.edit_vocab import VOCAB,EDIT_CASES
ROOT=Path(__file__).resolve().parents[2]
SOURCE_CASE_ID='newtons_cradle_baseline'
# Human-readable labels for the deletable pendulum slots, used in edit summaries.
OBJECT_LABEL={'ball_02':'middle pendulum ball','ball_03':'second-from-right pendulum ball'}

from pcve_scene_runtime import add_build_arguments, render_prefix, append_render_options, implementation_hashes

def write_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')

def fingerprint(s,args):
    source=implementation_hashes(Path(__file__).parent)
    source.update(implementation_hashes(ROOT/'scripts'/'scene_support'/'newtons_cradle'))
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
    sim=[str(args.physics_python),str(Path(__file__).with_name('simulate_newtons_cradle.py')),'--out',str(folder/'physics_transforms.json'),'--scenario-json',str(folder/'scenario_input.json')]
    script=Path(__file__).with_name('render_newtons_cradle.py')
    render=render_prefix(args, script)
    render+=['--physics-json',str(folder/'physics_transforms.json'),'--out-dir',str(folder),'--engine',args.engine,'--device',args.device,'--samples',str(args.samples),'--resolution',*map(str,args.resolution),'--mode',args.mode]
    return sim,append_render_options(render,args)

def run_case(folder,s,args):
    validate(s);folder.mkdir(parents=True,exist_ok=True);fp=fingerprint(s,args)
    status_file=folder/'run_status.json';required=['physics_transforms.json','simulation_metrics.json']
    if not args.simulate_only:required+=['preview.png','ground_truth_transforms.json','newtons_cradle.blend']+(['video.mp4'] if args.mode=='animation' else [])
    if args.skip_existing and status_file.exists():
        status=json.loads(status_file.read_text(encoding='utf-8'))
        if status.get('fingerprint')==fp and status.get('valid') and all((folder/name).exists() for name in required):return dict(status,status='skipped_existing')
    sim,render=commands_for(folder,args)
    if args.dry_run:
        for command in (([] if args.render_only else [sim])+([] if args.simulate_only else [render])):print(' '.join(map(str,command)))
        return dict(status='dry_run',valid=False,fingerprint=fp,quality=dict(valid=False))
    write_json(folder/'scenario_input.json',s)
    if not args.render_only:run_logged(sim,folder/'simulation.log',args)
    data=json.loads((folder/'physics_transforms.json').read_text(encoding='utf-8'))
    if (data['scenario']['physics']!=s['physics'] or data['playback_fps']!=s['render']['fps']
            or data['slow_motion']!=s['render']['slow_motion'] or data['physical_duration_sec']!=s['render']['duration_sec']):
        raise ValueError('Cached physics/timing differs from requested scenario; resimulate first')
    if not data['quality']['valid']:raise ValueError('Invalid simulation')
    if not args.simulate_only:run_logged(render,folder/'render.log',args)
    status=dict(status='completed',valid=True,simulation_only=args.simulate_only,render_mode=args.mode,fingerprint=fp,quality=data['quality'])
    write_json(status_file,status);return status

def parser():
    p=argparse.ArgumentParser();p.add_argument('--out-root',type=Path,default=ROOT/'renders/pcve_newtons_cradle_suite')
    p.add_argument('--physics-python',type=Path,default=python_for('physics'));p.add_argument('--render-python',type=Path,default=python_for('render'));p.add_argument('--blender',type=Path)
    p.add_argument('--duration-sec',type=float,default=6);p.add_argument('--fps',type=int,default=24);p.add_argument('--slow-motion',type=int,choices=(1,2,4,8),default=1)
    p.add_argument('--samples',type=int,default=32);p.add_argument('--resolution',type=int,nargs=2,default=[960,540]);p.add_argument('--engine',choices=('eevee','cycles'),default='cycles');p.add_argument('--device',choices=('auto','cpu'),default='auto');p.add_argument('--mode',choices=('preview','animation'),default='animation')
    p.add_argument('--simulate-only',action='store_true');p.add_argument('--render-only',action='store_true');p.add_argument('--skip-existing',action='store_true');p.add_argument('--cases',nargs='+')
    p.add_argument('--dry-run',action='store_true',help='Print the commands each case would run and stop.')
    p.add_argument('--verbose-render',action='store_true',help='Stream simulation and render output to the console.')
    p.add_argument('--clean-stale-cases',action='store_true',help='Delete case directories that are no longer part of this suite.')
    return add_build_arguments(p)

def main():
    args=parser().parse_args();args.out_root=args.out_root.resolve()
    if args.render_only and args.simulate_only:raise ValueError('Conflicting execution modes')
    if args.clean_stale_cases and not args.dry_run:clean_stale(args.out_root,{SOURCE_CASE_ID,*[name for name,_ in EDIT_CASES]})
    cases=EDIT_CASES
    if args.cases:
        unknown=set(args.cases)-{SOURCE_CASE_ID,*[name for name,_ in cases]}
        if unknown:raise ValueError(f'Unknown cases: {unknown}')
        cases=[entry for entry in cases if entry[0] in args.cases]
    source=defaults();source['render'].update(fps=args.fps,duration_sec=args.duration_sec,slow_motion=args.slow_motion,resolution=args.resolution,samples=args.samples)
    description={
        'vague':{'zh':'书桌上的五球牛顿摆：拉起左端一个球后静止释放，观察碰撞传递和往返衰减。','en':'Release the leftmost ball of a five-ball desktop Newton cradle and observe collision transmission and decay.'},
        'quantitative':{'zh':'左端球从高于最低球心位置 0.045 m 处静止释放，球间恢复系数 0.95，摆长 0.18 m，重力 9.81 m/s2。','en':'Release the leftmost ball from 0.045 m above its lowest center position; pair restitution 0.95, pendulum length 0.18 m, gravity 9.81 m/s2.'}}
    manifest=dict(schema_version=3,suite_name='pcve_newtons_cradle_suite',description='One source and five edits: two release heights, two whole-clip ball deletions (middle and second-from-right), and a restitution drop applied partway through the clip.',baseline_physics=source['physics'],
        total_frames=round(args.fps*args.duration_sec*args.slow_motion),resolution=args.resolution,fps=args.fps,duration_sec=args.duration_sec*args.slow_motion,samples=args.samples,
        physical_duration_sec=args.duration_sec,playback_duration_sec=args.duration_sec*args.slow_motion,sample_fps=args.fps*args.slow_motion,slow_motion=args.slow_motion,source=None,edits=[])
    path=args.out_root/'suite_manifest.json'
    for i,(case_id,instruction) in enumerate([(SOURCE_CASE_ID,None),*cases]):
        folder=args.out_root/'cases'/case_id;s=source
        record=dict(case_id=case_id,kind='edit' if instruction else 'source',seed=9200+i,case_dir=str(folder.resolve()),status='pending')
        if instruction:
            edit=dsl.parse(instruction,VOCAB)
            override={'physics':dsl.to_scenario_override(edit,VOCAB)};s=merge(source,override)
            if isinstance(edit,dsl.DeleteEdit):
                diff={f'presence ({edit.object_id})':{'from':'present','to':'absent'}}
                summary=f'The {OBJECT_LABEL[edit.object_id]} is absent from the physical simulation and the rendered scene; the remaining balls collide across the gap.'
            else:
                diff={f'{edit.property_name} ({edit.object_id})':{'from':dsl.baseline_value_for(edit,VOCAB),'to':dsl.resolved_to_value(edit,VOCAB)}}
                summary='Only the declared release height or pair restitution changes; all motion is simulated.'
                if dsl.is_timed(edit):summary=f'{summary} The new restitution is applied inside the running simulation at frame {edit.at_frame}, then the simulation continues from that state.'
            record.update(source_case_id=SOURCE_CASE_ID,edit_dsl=instruction,edit_summary=summary,applies_from_frame=dsl.starts_at_frame(edit),
                physics_diff={**diff,'timing':dsl.timing_diff(edit,VOCAB)},prompts=dsl.make_prompts(edit,VOCAB),
                scenario_overrides_json=str((folder/'scenario_overrides.json').resolve()),prompts_json=str((folder/'prompts.json').resolve()))
            write_json(folder/'scenario_overrides.json',override)
            write_json(folder/'prompts.json',{'schema_version':2,**{key:record[key] for key in ('case_id','source_case_id','edit_dsl','edit_summary','applies_from_frame','physics_diff','prompts')}})
            manifest['edits'].append(record)
        else:
            record['description']=description;manifest['source']=record
            write_json(folder/'prompts.json',dict(schema_version=1,case_id=case_id,kind='source',prompts=description))
        write_json(path,manifest);print(f'[suite] {case_id}',flush=True);start=time.perf_counter()
        try:
            record.update(run_case(folder,s,args))
            if not args.dry_run and not instruction and not record['quality']['transmission_observed']:raise RuntimeError('Baseline did not transmit motion to the last ball')
            if not args.dry_run and not args.simulate_only and args.mode=='animation':record['outputs']=standardize_render_outputs(folder,bool(instruction))
            else:record['outputs']={key:str((folder/name).resolve()) for key,name in [('physics','physics_transforms.json'),('scenario_input','scenario_input.json'),('preview','preview.png'),('ground_truth','ground_truth_transforms.json')] if (folder/name).exists()}
        except Exception:
            record['status']='failed';write_json(path,manifest);raise
        record['elapsed_sec']=round(time.perf_counter()-start,3);write_json(path,manifest)

if __name__=='__main__':main()

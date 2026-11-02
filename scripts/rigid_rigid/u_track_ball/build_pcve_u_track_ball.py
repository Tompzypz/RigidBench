"""Source and six one-variable edits, in the other projects' suite format."""
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




from pathlib import Path
import argparse,json,shutil,sys,subprocess,hashlib
import pcve_edit_dsl as dsl
from scene_config import defaults,merge,validate
from edit_vocab import VOCAB,EDIT_CASES
from runtime_support import python_for
ROOT = _PCVE_PROJECT_ROOT
from pcve_scene_runtime import add_build_arguments, render_prefix, append_render_options, implementation_hashes, case_outputs

def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')

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

def required_outputs(args):
    names=['physics_transforms.json','simulation_metrics.json']
    if not args.simulate_only:names+=['ground_truth_transforms.json','scenario_metadata.json']
    if not args.simulate_only:names.append('preview.png')
    if not args.simulate_only:names.append('u_track_ball.blend')
    if not args.simulate_only and args.mode=='animation':names.append('video.mp4')
    return names

def run_case(folder,scenario,args):
    validate(scenario)
    implementation=implementation_hashes(Path(__file__).parent)
    fp=hashlib.sha256(json.dumps(dict(scenario=scenario,implementation=implementation,engine=args.engine,device=args.device,preview_frame=args.preview_frame,mode=args.mode,simulation_only=args.simulate_only),sort_keys=True).encode()).hexdigest()
    status_file=folder/'run_status.json';inputs=folder/'scenario_input.json'
    if args.skip_existing and status_file.exists() and inputs.exists():
        status=json.loads(status_file.read_text(encoding='utf-8'))
        if (status.get('valid') and status.get('fingerprint')==fp and json.loads(inputs.read_text(encoding='utf-8'))==scenario
                and all((folder/name).exists() for name in required_outputs(args))):return dict(status,status='skipped_existing')
    sim=[str(args.physics_python),str(Path(__file__).with_name('simulate_u_track_ball.py')),'--out',str(folder/'physics_transforms.json'),'--scenario-json',str(folder/'scenario_input.json')]
    render=append_render_options(render_prefix(args, Path(__file__).with_name('render_u_track_ball.py')) + ['--physics-json', str(folder / 'physics_transforms.json'), '--out-dir', str(folder), '--engine', args.engine, '--device', args.device, '--samples', str(args.samples), '--resolution', *map(str, args.resolution), '--mode', args.mode], args)
    if args.dry_run:
        for command in (([] if args.render_only else [sim])+([] if args.simulate_only else [render])):print(' '.join(map(str,command)))
        return dict(status='dry_run',valid=False,quality=dict(valid=False))
    if not args.render_only:
        save(inputs,scenario)
        run_logged(sim,folder/'simulation.log',args)
    data=json.loads((folder/'physics_transforms.json').read_text(encoding='utf-8'))
    if (data['scenario']['physics']!=scenario['physics'] or data['playback_fps']!=scenario['render']['fps']
            or data['slow_motion']!=scenario['render']['slow_motion'] or data['physical_duration_sec']!=scenario['render']['duration_sec']):
        raise ValueError('Cached physics/timing differs; rerun simulation')
    if data['scenario'].get('camera')!=scenario.get('camera'):raise ValueError('Cached camera differs from requested scenario')
    if not data['quality']['valid']:raise ValueError('Invalid simulation; resimulate')
    if args.render_only:save(inputs,scenario)
    if not args.simulate_only:run_logged(render,folder/'render.log',args)
    status=dict(status='completed',valid=data['quality']['valid'],fingerprint=fp,simulation_only=args.simulate_only,render_mode=args.mode,quality=data['quality'])
    save(status_file,status)
    return status

def parser():
    p=argparse.ArgumentParser();p.add_argument('--out-root',type=Path,default=ROOT/'renders/pcve_u_track_ball_suite')
    p.add_argument('--physics-python',type=Path,default=python_for('physics'));p.add_argument('--render-python',type=Path,default=python_for('render'))
    p.add_argument('--duration-sec',type=float,default=3);p.add_argument('--fps',type=int,default=24);p.add_argument('--slow-motion',type=int,choices=(1,2,4,8),default=1)
    p.add_argument('--samples',type=int,default=32);p.add_argument('--resolution',type=int,nargs=2,default=[960,540]);p.add_argument('--engine',choices=('eevee','cycles'),default='cycles');p.add_argument('--device',choices=('auto','cpu'),default='auto');p.add_argument('--mode',choices=('preview','animation'),default='animation')
    p.add_argument('--simulate-only',action='store_true');p.add_argument('--render-only',action='store_true');p.add_argument('--skip-existing',action='store_true');p.add_argument('--cases',nargs='+')
    p.add_argument('--dry-run',action='store_true',help='Print the commands each case would run and stop.')
    p.add_argument('--verbose-render',action='store_true',help='Stream simulation and render output to the console.')
    p.add_argument('--clean-stale-cases',action='store_true',help='Delete case directories that are no longer part of this suite.')
    return add_build_arguments(p)

def main():
    args=parser().parse_args();args.out_root=args.out_root.resolve()
    if args.render_only and args.simulate_only:raise ValueError('Choose simulation-only or render-only')
    if args.clean_stale_cases and not args.dry_run:clean_stale(args.out_root,{'u_track_ball_baseline',*[name for name,_ in EDIT_CASES]})
    cases=EDIT_CASES
    if args.cases:
        unknown=set(args.cases)-{'u_track_ball_baseline',*[case for case,_ in cases]}
        if unknown:raise ValueError(f'Unknown cases: {unknown}')
        cases=[item for item in cases if item[0] in args.cases]
    source=defaults();source['render'].update(duration_sec=args.duration_sec,fps=args.fps,slow_motion=args.slow_motion,resolution=args.resolution,samples=args.samples)
    if args.dry_run:
        for case_id,instruction in [('u_track_ball_baseline',None),*cases]:
            scenario=source if instruction is None else merge(source,{'physics':dsl.to_scenario_override(dsl.parse(instruction,VOCAB),VOCAB)})
            run_case(args.out_root/'cases'/case_id,scenario,args)
        return
    description={
        'vague':{'zh':'球从较长的动力段下滑，经过 U 型谷底，越过较短的出口坡并撞击桌上的纸盒。','en':'A ball descends the longer drive branch, crosses the shorter exit branch and strikes a cardboard box on the table.'},
        'quantitative':{'zh':'半径 0.045 m、质量 0.25 kg 的木球从 x = -0.84 m 处静止释放，沿 0.90 m 长的动力坡下滑、经 U 型谷底越过 0.75 m 长的出口坡，撞击质量 0.08 kg 的桌面纸盒；轨道摩擦因数为 0.20，球滚动阻力系数为 0.002，重力 9.81 m/s²。','en':'A wooden ball of radius 0.045 m and mass 0.25 kg is released from rest at x = -0.84 m; it runs 0.90 m down the drive branch, crosses the U-shaped valley and the 0.75 m exit branch, and strikes a 0.08 kg carton on the table. Track friction is 0.20, the ball rolling-resistance coefficient is 0.002, under gravity of 9.81 m/s².'}}
    manifest=dict(schema_version=3,suite_name='pcve_u_track_ball_suite',scene='u_track_ball',description='One source and exactly five single-edit cases; the timed carton removal happens inside the simulation and all outcomes are measured by continued simulation.',fps=args.fps,sample_fps=args.fps*args.slow_motion,slow_motion=args.slow_motion,duration_sec=args.duration_sec*args.slow_motion,physical_duration_sec=args.duration_sec,playback_duration_sec=args.duration_sec*args.slow_motion,total_frames=round(args.fps*args.duration_sec*args.slow_motion),samples=args.samples,resolution=args.resolution,baseline_physics=source['physics'],source=dict(case_id='u_track_ball_baseline',description=description),edits=[])
    for case_id,instruction in [('u_track_ball_baseline',None),*cases]:
        folder=args.out_root/'cases'/case_id;scenario=source;record=manifest['source'] if instruction is None else dict(case_id=case_id,source_case_id='u_track_ball_baseline')
        record.update(kind='edit' if instruction else 'source',seed=0,case_dir=str(folder.resolve()))
        if instruction:
            edit=dsl.parse(instruction,VOCAB);override=dict(physics=dsl.to_scenario_override(edit,VOCAB));scenario=merge(source,override)
            if isinstance(edit,dsl.DeleteEdit):
                diff={f'presence ({edit.object_id})':{'from':'present','to':'absent'}}
                summary='The cardboard box is removed from the physical simulation and the rendered scene.'
                if dsl.is_timed(edit):summary=f'{summary} The removal happens inside the simulation at frame {edit.at_frame}; earlier frames match the source video.'
            else:
                diff={f'{edit.property_name} ({edit.object_id})':{'from':dsl.baseline_value_for(edit,VOCAB),'to':dsl.resolved_to_value(edit,VOCAB)}}
                summary=dsl.summarize_set_edit(edit,VOCAB)
            diff['timing']=dsl.timing_diff(edit,VOCAB)
            record.update(edit_summary=summary,scenario_overrides_json=str((folder/'scenario_overrides.json').resolve()),prompts_json=str((folder/'prompts.json').resolve()),edit_dsl=instruction,applies_from_frame=dsl.starts_at_frame(edit),prompts=dsl.make_prompts(edit,VOCAB),physics_diff=diff)
            save(folder/'scenario_overrides.json',override);manifest['edits'].append(record)
        prompts=dict(schema_version=1,case_id=case_id,kind='source',prompts=description) if instruction is None else dict(schema_version=2,kind='edit',**{k:record[k] for k in ('case_id','source_case_id','edit_dsl','edit_summary','applies_from_frame','physics_diff','prompts')})
        save(folder/'prompts.json',prompts);record['status']='pending';save(args.out_root/'suite_manifest.json',manifest)
        print(f'[suite] {case_id}',flush=True)
        try:record.update(run_case(folder,scenario,args))
        except Exception:
            record['status']='failed';save(args.out_root/'suite_manifest.json',manifest);raise
        if instruction is None and not args.dry_run and not record['quality']['hit_box']:raise RuntimeError('Baseline must clear exit and hit box; inspect simulation_metrics.json')
        record['outputs']=case_outputs(folder)
        save(args.out_root/'suite_manifest.json',manifest)

if __name__=='__main__':main()

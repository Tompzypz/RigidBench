"""One source + five independently resimulated editable scenes."""
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

import argparse,json,sys,subprocess,time
from pathlib import Path
from scene_config import defaults,merge,validate
from runtime_support import ROOT,python_for,render_prefix
from simulate_tennis_bottle_collision import simulate
from validate_tennis_bottle_collision import validate_cache
from edit_vocab import EDIT_CASES,VOCAB
import pcve_edit_dsl as dsl
SOURCE='tennis_bottle_collision_baseline'
def write(p,d):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--out-root',type=Path,default=ROOT/'renders/pcve_tennis_bottle_collision_empty_suite')
 p.add_argument('--render-python',type=Path,default=python_for('render'));p.add_argument('--blender',type=Path)
 p.add_argument('--simulate-only',action='store_true');p.add_argument('--render-only',action='store_true')
 p.add_argument('--samples',type=int,default=24);p.add_argument('--resolution',nargs=2,type=int,default=[960,540])
 p.add_argument('--engine',choices=('cycles','eevee'),default='cycles');p.add_argument('--device',choices=('auto','cpu'),default='auto')
 p.add_argument('--mode',choices=('keyframes','preview','animation','build'),default='keyframes');p.add_argument('--cases',nargs='+')
 p.add_argument('--keyframes',type=int,nargs='+');p.add_argument('--preview-frame',type=int,default=31)
 p.add_argument('--scenario-json',type=Path)
 a=p.parse_args();a.out_root=a.out_root.resolve()
 if a.simulate_only and a.render_only:raise ValueError('Conflicting modes')
 known={SOURCE,*[c[0] for c in EDIT_CASES]}
 if a.cases and set(a.cases)-known:raise ValueError('Unknown case')
 source=defaults()
 if a.scenario_json:source=merge(source,json.loads(a.scenario_json.read_text(encoding='utf-8')))
 source['render'].update(samples=a.samples,resolution=a.resolution);validate(source)
 manifest_path=a.out_root/'suite_manifest.json'
 manifest=dict(schema_version=3,suite_name='pcve_tennis_bottle_collision_suite',fps=source['render']['fps'],total_frames=4*source['render']['fps'],
 physical_duration_sec=4.,playback_duration_sec=4.,baseline_physics=source['physics'],resolution=a.resolution,samples=a.samples,source=None,edits=[])
 if a.cases and manifest_path.exists():manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
 baseline_description=dict(vague=dict(zh='房间内，滚动的网球撞向并排的两个空塑料瓶之间。',en='A rolling tennis ball hits between two adjacent upright empty plastic bottles inside a room.'),quantitative=dict(
   zh=f"房间内，滚动的网球撞向并排的两个空塑料瓶之间。 网球半径3.35厘米、质量{source['physics']['ball_mass']*1000:g}克；空瓶高23厘米、半径4.1厘米，每瓶质量{source['physics']['bottle_mass']*1000:g}克，网球初速{source['physics']['initial_velocity']:g}米/秒。",
   en=f"A rolling tennis ball hits between two adjacent upright empty plastic bottles inside a room. Ball radius 3.35 cm, mass {source['physics']['ball_mass']*1000:g} g; bottle height 23 cm, radius 4.1 cm, each bottle mass {source['physics']['bottle_mass']*1000:g} g; ball speed {source['physics']['initial_velocity']:g} m/s."))
 for case_id,instruction in [(SOURCE,None),*EDIT_CASES]:
  if a.cases and case_id not in a.cases:continue
  folder=a.out_root/'cases'/case_id;folder.mkdir(parents=True,exist_ok=True)
  if instruction:
   edit=dsl.parse(instruction,VOCAB)
   override={'physics':dsl.to_scenario_override(edit,VOCAB)}
   scenario=merge(source,override);validate(scenario)
   if isinstance(edit,dsl.DeleteEdit):
    diff={f'presence ({edit.object_id})':{'from':'present','to':'absent'}}
    summary=f'{edit.object_id} is absent from the physical simulation and rendered scene.'
   elif isinstance(edit,dsl.AddEdit):
    diff={'position':dsl.add_position_diff(edit,VOCAB)}
    summary=f'{edit.object_id} joins the physical simulation and rendered scene at the resolved position.'
   else:
    diff={f'{edit.property_name} ({edit.object_id})':{'from':dsl.baseline_value_for(edit,VOCAB),'to':dsl.resolved_to_value(edit,VOCAB)}}
    summary=dsl.summarize_set_edit(edit,VOCAB)
    if dsl.is_timed(edit):
     summary=f'{summary} The new restitution governs collisions after the edit.'
   diff['timing']=dsl.timing_diff(edit,VOCAB)
   prompts=dsl.make_prompts(edit,VOCAB)
   write(folder/'scenario_overrides.json',override)
   write(folder/'prompts.json',dict(schema_version=2,case_id=case_id,source_case_id=SOURCE,edit_dsl=instruction,
    edit_summary=summary,applies_from_frame=dsl.starts_at_frame(edit),physics_diff=diff,prompts=prompts))
   record=dict(case_id=case_id,kind='edit',source_case_id=SOURCE,edit_dsl=instruction,
    applies_from_frame=dsl.starts_at_frame(edit),edit_summary=summary,physics_diff=diff,prompts=prompts,
    case_dir=str(folder),status='running')
   manifest['edits']=[c for c in manifest['edits'] if c['case_id']!=case_id]+[record]
  else:
   scenario=source;prompts=baseline_description
   write(folder/'prompts.json',dict(schema_version=1,case_id=case_id,kind='source',prompts=prompts))
   record=dict(case_id=case_id,kind='source',case_dir=str(folder),status='running',description=prompts)
   manifest['source']=record
  write(folder/'scenario_input.json',scenario)
  write(manifest_path,manifest);print('[suite] '+case_id,flush=True);start=time.perf_counter()
  try:
   if not a.render_only:
    data=simulate(scenario);validate_cache(data);write(folder/'physics_transforms.json',data);write(folder/'simulation_metrics.json',data['quality'])
   else:
    data=json.loads((folder/'physics_transforms.json').read_text(encoding='utf-8'));validate_cache(data)
    if data['scenario']['physics']!=scenario['physics'] or data['scenario']['camera']!=scenario['camera']:raise ValueError('Cache scenario mismatch')
   if not a.simulate_only:
    cmd=render_prefix(a,Path(__file__).with_name('render_tennis_bottle_collision.py'))
    cmd+=['--out-dir',str(folder),'--physics-json',str(folder/'physics_transforms.json'),'--mode',a.mode,
     '--engine',a.engine,'--device',a.device,'--samples',str(a.samples),'--resolution',*map(str,a.resolution),'--preview-frame',str(a.preview_frame)]
    if a.mode=='keyframes':cmd+=['--keyframes',*map(str,a.keyframes or ([1,min(data['frame_end'],int((data['quality']['first_impact_sec'] or 0)*data['sample_fps'])+2),round(1.25*data['sample_fps'])+1,data['frame_end']] if not instruction else [1,data['frame_end']]))]
    with (folder/'render.log').open('w',encoding='utf-8') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
   record.update(status='completed',valid=True,simulation_only=a.simulate_only,quality=data['quality'],elapsed_sec=time.perf_counter()-start)
   names=dict(video='video.mp4',physics='physics_transforms.json',ground_truth='ground_truth_transforms.json',scenario_input='scenario_input.json',scenario_metadata='scenario_metadata.json',scenario_overrides='scenario_overrides.json',prompts='prompts.json',preview='preview.png',blend='tennis_bottle_collision.blend',keyframes='keyframes.json')
   record['outputs']={key:str(folder/name) for key,name in names.items() if (folder/name).exists()}
   write(folder/'run_status.json',record)
  except Exception as e:
   record.update(status='failed',error=str(e));write(manifest_path,manifest);raise
  write(manifest_path,manifest)
if __name__=='__main__':main()

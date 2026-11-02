"""Shared scenario contract, matching the other rigid-body scene projects."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
from copy import deepcopy
from pathlib import Path
import json, math

SCENE_NAME='chalk_box_stack'
# The delivered four-second film uses this original recipe, not the legacy
# short-demo defaults (4 m/s, 0.48 kg). Keep a single source for its physics,
# framing and timing so the normal CLI cannot silently select another take.
SCENARIO_DIR=_PCVE_ROOT/'assets'/'scenarios'/'chalk_box_stack'
_DELIVERY_SCENARIO=json.loads((SCENARIO_DIR/'four_second.json').read_text(encoding='utf-8'))
BASELINE_PHYSICS=deepcopy(_DELIVERY_SCENARIO['physics'])
# One real-time clock from simulation through video, matching the suites.
TOTAL_FRAMES=96

def defaults():
    return dict(schema_version=1,scene=SCENE_NAME,physics=deepcopy(BASELINE_PHYSICS),
        render=deepcopy(_DELIVERY_SCENARIO['render']),
        camera=deepcopy(_DELIVERY_SCENARIO['camera']))

def merge(base,overrides):
    result=deepcopy(base)
    for key,value in overrides.items():
        result[key]=merge(result[key],value) if isinstance(value,dict) and isinstance(result.get(key),dict) else deepcopy(value)
    return result

def validate(s):
    if set(s)-{'schema_version','scene','physics','render','camera','seed'} or s.get('scene')!=SCENE_NAME:
        raise ValueError('Invalid scenario fields or scene name')
    c=s['physics'];r=s['render']
    if set(c)!=set(BASELINE_PHYSICS):raise ValueError('Unknown or missing physics parameter')
    for key,value in c.items():
        # The timed-edit schedule is a list of events, not a physical knob; the
        # simulator validates every entry it is given. Everything else here is
        # one number per parameter.
        if isinstance(value,(list,tuple,dict)):continue
        if not math.isfinite(value) or (key=='eraser_mass' and value==0):raise ValueError(f'Invalid {key}')
        # ``eraser_start_x`` is a signed position; every other knob is a
        # magnitude and has to stay nonnegative.
        if key!='eraser_start_x' and value<0:raise ValueError(f'Invalid {key}')
    if not isinstance(r['fps'],int) or r['fps']<=0 or not math.isfinite(r['duration_sec']) or r['duration_sec']<=0:raise ValueError('Invalid timing')
    if r.get('slow_motion',1)!=1:raise ValueError('Slow motion is no longer supported; use real-time playback (slow_motion=1)')
    if r['fps']>2400:raise ValueError('Sample rate exceeds physics rate')
    if round(r['fps']*r['duration_sec'])<1:raise ValueError('Empty trajectory')
    if not isinstance(r['samples'],int) or r['samples']<1 or len(r['resolution'])!=2 or any(not isinstance(v,int) or v<2 or v%2 for v in r['resolution']):raise ValueError('Invalid render settings; use even resolution')
    camera=s['camera']
    for key in ('location','target'):
        if len(camera[key])!=3 or not all(math.isfinite(v) for v in camera[key]):raise ValueError('Invalid camera vector')
    scale=camera.get('ortho_scale')
    if (camera['location']==camera['target'] or camera.get('projection','orthographic')!='orthographic'
        or not isinstance(scale,(int,float)) or not math.isfinite(scale) or scale<=0):
        raise ValueError('Original orthographic camera required; resimulate any cache from the previous camera configuration')

def load_scenario(args):
    scenario_path=args.scenario_json
    if scenario_path and not scenario_path.is_file():
        # Keep accepting the former scene-local preset path used by saved commands.
        candidate=SCENARIO_DIR/scenario_path.name
        if candidate.is_file():scenario_path=candidate
    s=merge(defaults(),json.loads(scenario_path.read_text(encoding='utf-8'))) if scenario_path else defaults()
    if args.scenario_overrides_json:s=merge(s,json.loads(args.scenario_overrides_json.read_text(encoding='utf-8')))
    for key in BASELINE_PHYSICS:
        if getattr(args,key,None) is not None:s['physics'][key]=getattr(args,key)
    for key in ('fps','duration_sec','resolution','samples'):
        if getattr(args,key,None) is not None:s['render'][key]=getattr(args,key)
    validate(s)
    return s

"""SI units; editable initial conditions and pairwise coefficient of restitution."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
from copy import deepcopy
import json
import math

SCENE_NAME = 'kitchen_tableware_collision'
BASELINE_PHYSICS = dict(driver_mass=.28, receiver_mass=.28, initial_velocity=.72,
                        receiver_initial_velocity=0., restitution=.68, receiver_active=[1])
PHYSICS_LIMITS = dict(driver_mass=(.12,1.5), receiver_mass=(.12,.65),
                      initial_velocity=(.40,3.7), receiver_initial_velocity=(-.22,.22), restitution=(0.,.95))

# Editable keys this scene adds on top of the shared baseline. These used to
# run as an import side effect of edit_vocab; scene_config owns them now.
BASELINE_PHYSICS.update(tableware_friction=.018, timed_edits=[])
PHYSICS_LIMITS.update(tableware_friction=(0., .12))
TOTAL_FRAMES = 96


def defaults():
    return dict(schema_version=1, scene=SCENE_NAME, seed=0, physics=deepcopy(BASELINE_PHYSICS),
                render=dict(fps=24, duration_sec=4., slow_motion=1, resolution=[960,540], samples=48),
                camera=dict(location=[.35,-1.85,1.64], target=[.08,.18,1.15], lens_mm=38))


def merge(base, overrides):
    result = deepcopy(base)
    if not isinstance(overrides, dict): raise ValueError('Scenario overrides must be an object')
    for key,value in overrides.items():
        if key not in result: raise ValueError(f'Unknown scenario field: {key}')
        result[key] = merge(result[key],value) if isinstance(value,dict) else deepcopy(value)
    return result


def finite(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)


def validate(s):
    if set(s) - {'schema_version','scene','physics','render','camera','seed'}:
        raise ValueError('Unknown scenario field')
    if s['scene'] != SCENE_NAME or s['schema_version'] != 1: raise ValueError('Wrong scene/schema')
    if set(s['physics']) != set(BASELINE_PHYSICS): raise ValueError('Unknown editable physics parameter')
    active=s['physics']['receiver_active']
    if not isinstance(active,list) or len(active)!=1 or type(active[0]) is not int or active[0] not in (0,1):
        raise ValueError('receiver_active must be [0] or [1]')
    for key,(low,high) in PHYSICS_LIMITS.items():
        if not finite(s['physics'][key]) or not low <= s['physics'][key] <= high:
            raise ValueError(f'{key} must be finite and within {low}..{high}')
    r=s['render']
    if type(r['fps']) is not int or r['fps'] <= 0: raise ValueError('Invalid fps')
    if type(r['slow_motion']) is not int or r['slow_motion'] not in (1,2,4,8) or 1440 % (r['fps']*r['slow_motion']):
        raise ValueError('fps * slow_motion must divide the 1440 Hz simulation clock')
    if not finite(r['duration_sec']) or not 0 < r['duration_sec'] <= 30 or round(r['fps']*r['slow_motion']*r['duration_sec']) < 2:
        raise ValueError('Invalid duration')
    if len(r['resolution']) != 2 or any(type(v) is not int or v <= 0 for v in r['resolution']): raise ValueError('Invalid resolution')
    if type(r['samples']) is not int or r['samples'] < 1: raise ValueError('Invalid sample count')
    if set(r) != {'fps','duration_sec','slow_motion','resolution','samples'}: raise ValueError('Unknown render field')
    if set(s['camera']) != {'location','target','lens_mm'}: raise ValueError('Unknown camera field')
    for key in ('location','target'):
        if len(s['camera'][key]) != 3 or not all(finite(v) for v in s['camera'][key]): raise ValueError('Invalid camera vector')
    if not finite(s['camera']['lens_mm']) or s['camera']['lens_mm'] <= 0: raise ValueError('Invalid lens')


def load_scenario(args):
    s=merge(defaults(),json.loads(args.scenario_json.read_text(encoding='utf-8'))) if args.scenario_json else defaults()
    if args.scenario_overrides_json: s=merge(s,json.loads(args.scenario_overrides_json.read_text(encoding='utf-8')))
    for key in BASELINE_PHYSICS:
        if key=='receiver_active':continue
        if getattr(args,key,None) is not None: s['physics'][key]=getattr(args,key)
    if getattr(args,'remove_receiver',False):s['physics']['receiver_active']=[0]
    for key in ('fps','duration_sec','slow_motion'):
        if getattr(args,key,None) is not None: s['render'][key]=getattr(args,key)
    validate(s)
    return s


def add_scenario_arguments(parser):
    from pathlib import Path
    parser.add_argument('--scenario-json',type=Path)
    parser.add_argument('--scenario-overrides-json',type=Path)
    for key in PHYSICS_LIMITS: parser.add_argument('--'+key.replace('_','-'),type=float)
    parser.add_argument('--remove-receiver',action='store_true',help='Remove the ivory target bowl from frame 1')
    parser.add_argument('--fps',type=int)
    parser.add_argument('--duration-sec',type=float)
    parser.add_argument('--slow-motion',type=int,choices=(1,2,4,8))
    return parser

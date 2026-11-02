"""Strict metre/kilogram/second scenario contract, shared by simulation and render."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
from copy import deepcopy
import json
import math
from pathlib import Path

SCENE_NAME = 'soccer_step_collision'
BASELINE_PHYSICS = dict(soccer_mass=.43, basketball_mass=.62, launch_speed=1.95,
    step_height=.045, surface_rolling_friction=.0015,
    soccer_restitution=.72, basketball_restitution=.78)

# Editable keys this scene adds on top of the shared baseline. These used to
# run as an import side effect of edit_vocab; scene_config owns them now.
BASELINE_PHYSICS.update(timed_edits=[])
LIMITS = dict(soccer_mass=(.05,5), basketball_mass=(.05,5), launch_speed=(.1,3),
    step_height=(.005,.20), surface_rolling_friction=(0,.1),
    soccer_restitution=(0,1), basketball_restitution=(0,1))

def defaults():
    return dict(schema_version=1, scene=SCENE_NAME, seed=0,
        physics=deepcopy(BASELINE_PHYSICS),
        render=dict(fps=24, duration_sec=4., resolution=[960,540], samples=40),
        camera=dict(location=[-2.6,-5.5,2.15], target=[.55,.1,.35], lens_mm=48))

def merge(base, override):
    result = deepcopy(base)
    if not isinstance(override, dict): raise ValueError('Override must be an object')
    for k,v in override.items():
        if k not in base: raise ValueError(f'Unknown scenario field: {k}')
        result[k] = merge(base[k],v) if isinstance(base[k],dict) else deepcopy(v)
    return result

def finite(x):
    return type(x) in (int,float) and math.isfinite(x)

def validate(s):
    if set(s) != set(defaults()) or s['scene'] != SCENE_NAME or s['schema_version'] != 1:
        raise ValueError('Wrong scenario schema')
    if set(s['physics']) != set(BASELINE_PHYSICS): raise ValueError('Unknown physics field')
    for k,(lo,hi) in LIMITS.items():
        if not finite(s['physics'][k]) or not lo <= s['physics'][k] <= hi:
            raise ValueError(f'{k} must be within {lo}..{hi}')
    r=s['render']
    if set(r) != set(defaults()['render']): raise ValueError('Unknown render field')
    if type(r['fps']) is not int or r['fps'] <= 0 or 1440 % r['fps']:
        raise ValueError('fps must divide the 1440 Hz simulation clock')
    if not finite(r['duration_sec']) or not .1 <= r['duration_sec'] <= 30:
        raise ValueError('Invalid duration')
    if len(r['resolution']) != 2 or any(type(v) is not int or v<16 for v in r['resolution']):
        raise ValueError('Invalid resolution')
    if type(r['samples']) is not int or r['samples']<1: raise ValueError('Invalid samples')
    c=s['camera']
    if set(c) != set(defaults()['camera']): raise ValueError('Unknown camera field')
    for k in ('location','target'):
        if len(c[k]) != 3 or not all(finite(v) for v in c[k]): raise ValueError('Invalid camera vector')
    if not finite(c['lens_mm']) or c['lens_mm']<=0: raise ValueError('Invalid lens')

def load_scenario(path=None, override=None):
    s=defaults()
    for p in (path,override):
        if p: s=merge(s,json.loads(Path(p).read_text(encoding='utf-8')))
    validate(s)
    return s

def write_json(path, data):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')

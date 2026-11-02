"""A tabletop asymmetric U track; SI units throughout."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
from copy import deepcopy
import math

SCENE_NAME='u_track_ball'
BASELINE_PHYSICS=dict(gravity=[0,0,-9.81],ball_radius=.045,ball_mass=.25,
    friction=.20,ball_friction=.50,rolling_friction=.002,restitution=.05,
    initial_speed=0,initial_position=-.84,drive_length=.90,exit_length=.75,
    drive_height=.56,exit_height=.20,track_bottom=.82,track_width=.18,
    track_thickness=.024,segments_per_branch=60,table_height=.72,
    box_mass=.08,box_position=[1.35,0,.82],box_size=[.16,.22,.20],table_friction=.35,
    substeps=40,solver_iterations=100)

# Editable keys this scene adds on top of the shared baseline. These used to
# run as an import side effect of edit_vocab; scene_config owns them now.
BASELINE_PHYSICS.update(box_presence=[1],timed_edits=[])

def defaults():
    return dict(schema_version=1,scene=SCENE_NAME,physics=deepcopy(BASELINE_PHYSICS),
        render=dict(fps=24,duration_sec=3.,slow_motion=1,resolution=[960,540],samples=16),
        camera=dict(location=[2.45,-4.0,2.45],target=[.35,0,1.02],lens_mm=48))

def merge(base,overrides):
    out=deepcopy(base)
    for key,value in overrides.items():
        out[key]=merge(out[key],value) if isinstance(value,dict) else deepcopy(value)
    return out

def validate(s):
    c=s['physics'];r=s['render']
    unknown=set(c)-set(BASELINE_PHYSICS)
    if unknown: raise ValueError(f'Unknown physics keys: {sorted(unknown)}')
    for k in ('ball_radius','ball_mass','drive_length','exit_length','drive_height','exit_height','track_width','track_thickness','box_mass','substeps','segments_per_branch'):
        if not math.isfinite(c[k]) or c[k]<=0: raise ValueError(f'{k} must be positive and finite')
    for k in ('friction','ball_friction','rolling_friction','table_friction','initial_speed'):
        if not math.isfinite(c[k]) or c[k]<0: raise ValueError(f'{k} must be finite and nonnegative')
    if not -c['drive_length']+.02<=c['initial_position']<=c['exit_length']-.02:
        raise ValueError('Initial position must be inside the track; metres along world X')
    if c['track_width']<=2*c['ball_radius']+.005: raise ValueError('Track too narrow for ball')
    if c['track_bottom']<=c['table_height']+c['track_thickness']: raise ValueError('Track intersects table')
    if c['substeps']!=int(c['substeps']) or c['segments_per_branch']!=int(c['segments_per_branch']): raise ValueError('Discretization must be integral')
    if len(c['gravity'])!=3 or not all(math.isfinite(v) for v in c['gravity']): raise ValueError('Invalid gravity')
    if len(c['box_position'])!=3 or len(c['box_size'])!=3 or any(not math.isfinite(v) for v in c['box_position']+c['box_size']) or any(v<=0 for v in c['box_size']): raise ValueError('Invalid box geometry')
    if abs(c['box_position'][2]-c['table_height']-c['box_size'][2]/2)>1e-6: raise ValueError('Box bottom must sit on tabletop')
    if r['fps']<=0 or r['duration_sec']<=0 or r['slow_motion'] not in (1,2,4,8): raise ValueError('Invalid timing')

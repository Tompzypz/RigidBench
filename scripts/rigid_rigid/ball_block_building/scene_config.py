"""Tabletop wooden-block stack; SI units, with gravity and free contacts."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
from copy import deepcopy
import math

SCENE_NAME='ball_block_building'
# The ball is released already rolling on the tabletop (no-slip spin is derived
# from ball_speed in the simulation), so every edit changes how hard the stack is
# nudged instead of how violently a flying ball smashes through it.
BASELINE_PHYSICS=dict(gravity=[0,0,-9.81],ball_radius=.06,ball_mass=.4,
    ball_speed=2.2,ball_initial_location=[-.60,0,.7802],ball_friction=.4,
    ball_rolling_friction=.0002,ball_restitution=.10,block_density=650.,
    block_friction=.55,block_restitution=.05,table_friction=.70,table_height=.72,
    settle_sec=.8,substeps=40,solver_iterations=120)

# Editable keys this scene adds on top of the shared baseline. These used to
# run as an import side effect of edit_vocab; scene_config owns them now.
BASELINE_PHYSICS.update(block_presence=[1,1],gravity_strength=9.81,timed_edits=[])
TOTAL_FRAMES=96

def defaults():
    return dict(schema_version=1,scene=SCENE_NAME,physics=deepcopy(BASELINE_PHYSICS),
        render=dict(fps=24,duration_sec=4.,slow_motion=1,resolution=[960,540],samples=16),
        camera=dict(location=[2.35,-3.45,1.72],target=[.05,.45,1.05],lens_mm=48))

def merge(base,overrides):
    result=deepcopy(base)
    for key,value in overrides.items():
        result[key]=merge(result[key],value) if isinstance(value,dict) else deepcopy(value)
    return result

def validate(s):
    if set(s)-{'schema_version','scene','physics','render','camera','seed'}:raise ValueError('Unknown scenario field; physics overrides must be nested under physics')
    c=s['physics'];r=s['render']
    if set(c)-set(BASELINE_PHYSICS):raise ValueError('Unknown physics parameter')
    for key in ('ball_radius','ball_mass','block_density','table_height','substeps','solver_iterations'):
        if not math.isfinite(c[key]) or c[key]<=0:raise ValueError(f'{key} must be positive and finite')
    for key in ('ball_speed','ball_friction','ball_rolling_friction','block_friction','table_friction','settle_sec'):
        if not math.isfinite(c[key]) or c[key]<0:raise ValueError(f'{key} must be nonnegative and finite')
    for key in ('ball_restitution','block_restitution'):
        if not math.isfinite(c[key]) or not 0<=c[key]<=1:raise ValueError(f'{key} must be between zero and one')
    for key in ('gravity','ball_initial_location'):
        if len(c[key])!=3 or not all(math.isfinite(v) for v in c[key]):raise ValueError(f'Invalid {key}')
    # The ball starts in rolling contact with the tabletop; a raised start would
    # turn the scene back into a thrown-ball impact.
    if c['ball_initial_location'][2]<c['table_height']+c['ball_radius']:raise ValueError('Ball must start on the tabletop')
    if c['substeps']!=int(c['substeps']) or c['solver_iterations']!=int(c['solver_iterations']):raise ValueError('Integer solver settings required')
    if r['fps']<=0 or r['duration_sec']<=0 or r['slow_motion'] not in (1,2,4,8) or c['substeps']%r['slow_motion']:raise ValueError('Invalid timing')

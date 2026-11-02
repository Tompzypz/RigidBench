"""Five steel pendulums, fixed gravity; only height and restitution are editable."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
from copy import deepcopy
import math
SCENE_NAME='newtons_cradle'
BASELINE_PHYSICS=dict(initial_height=.045,restitution=.95,gravity=[0,0,-9.81],ball_radius=.019,
    ball_density=7800.,pendulum_length=.18,pivot_height=1.00,table_height=.72,
    ball_gap=.0001,joint_damping=.000002,physics_hz=4800,solver_iterations=160)

# Editable keys this scene adds on top of the shared baseline. These used to
# run as an import side effect of edit_vocab; scene_config owns them now.
BASELINE_PHYSICS.update(ball_presence=[1,1,1,1,1],timed_edits=[])
TOTAL_FRAMES=144

def defaults():
    return dict(schema_version=1,scene=SCENE_NAME,physics=deepcopy(BASELINE_PHYSICS),
        render=dict(fps=24,duration_sec=6.,slow_motion=1,resolution=[960,540],samples=16),
        camera=dict(location=[.66,-1.28,1.18],target=[-.035,0,.89],lens_mm=58))

def merge(base,overrides):
    result=deepcopy(base)
    for key,value in overrides.items():
        result[key]=merge(result[key],value) if isinstance(value,dict) else deepcopy(value)
    return result

def validate(s):
    if set(s)-{'schema_version','scene','physics','render','camera','seed'}:raise ValueError('Unknown scenario field')
    if s.get('scene')!=SCENE_NAME:raise ValueError('Wrong scene')
    c=s['physics'];r=s['render']
    if set(c)!=set(BASELINE_PHYSICS):raise ValueError('Unknown/missing physics parameter')
    for key in set(c)-{'initial_height','restitution','ball_presence','timed_edits'}:
        if c[key]!=BASELINE_PHYSICS[key]:raise ValueError('Only initial_height and restitution are editable')
    presence=c.get('ball_presence',BASELINE_PHYSICS.get('ball_presence',[1]*5))
    if not isinstance(presence,list) or len(presence)!=5 or any(v not in (0,1,False,True) for v in presence):
        raise ValueError('ball_presence must be a five-entry 0/1 mask')
    schedule=c.get('timed_edits',[])
    if not isinstance(schedule,list) or any(
            not isinstance(entry,dict) or set(entry)!={'frame','params'}
            or type(entry['frame']) is not int
            or not isinstance(entry['params'],dict) or not entry['params']
            or any(not isinstance(v,(int,float)) or not math.isfinite(v)
                   for v in entry['params'].values())
            for entry in schedule):
        raise ValueError('Invalid timed_edits schedule')
    if not math.isfinite(c['initial_height']) or not 0<=c['initial_height']<=.14:raise ValueError('Height must be 0..0.14 m above the lowest ball-center position')
    if not math.isfinite(c['restitution']) or not 0<=c['restitution']<=1:raise ValueError('Restitution must be 0..1')
    if r['fps']!=int(r['fps']) or r['fps']<=0 or not math.isfinite(r['duration_sec']) or r['duration_sec']<=0 or r['slow_motion'] not in (1,2,4,8):raise ValueError('Invalid timing')
    if c['physics_hz']%(r['fps']*r['slow_motion']):raise ValueError('Sampling must divide fixed 4800 Hz physics clock')

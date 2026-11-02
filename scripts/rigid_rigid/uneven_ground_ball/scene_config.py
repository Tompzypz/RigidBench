"""A ball rolling over a rutted, sloping earth path. SI units."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
from copy import deepcopy
import math

SCENE_NAME='uneven_ground_ball'
TOTAL_FRAMES=72
# Low, near-grazing three-quarter view: the horizon line sits close to the ball,
# so every crest and hollow of the path breaks the silhouette instead of being
# flattened into a top-down texture.
TERRAIN_CAMERA=dict(location=[-0.50,-2.20,.66],target=[-0.50,-.10,.10],lens_mm=26)
BASELINE_PHYSICS=dict(gravity=[0,0,-9.81],ball_radius=.10,ball_mass=.45,ball_speed=1.4,ball_inertia_factor=.64,
    ball_start_xy=[-1.8,-.20],ball_friction=.35,ball_rolling_friction=.0015,
    ball_restitution=.05,ground_friction=1.,substeps=40,solver_iterations=100,
    terrain_bounds=[[-8.,-8.],[12.,8.]],terrain_cells=[400,320],
    terrain_base_height=.08,terrain_slope=-.016,terrain_roughness=1.,    # cx, cy, amplitude, sigma_x, sigma_y. Negative amplitude is a hollow.
    # A broad worn trough carries the ball along +x; discrete mounds and hollows
    # inside and beside it make the path wander without throwing the ball off it.
    bumps=[[-.30,-.30,-.040,2.40,.50],
           [.90,-.50,-.045,.340,.300],
           [.60,.25,.045,.400,.300],
           [-1.20,-.45,-.040,.300,.280],
           [1.80,-.20,.040,.400,.340]])

# Editable keys this scene adds on top of the shared baseline. These used to
# run as an import side effect of edit_vocab; scene_config owns them now.
BASELINE_PHYSICS.update(timed_edits=[])

def defaults():
    return dict(schema_version=1,scene=SCENE_NAME,physics=deepcopy(BASELINE_PHYSICS),
        render=dict(fps=24,duration_sec=3.,slow_motion=1,resolution=[960,540],samples=16),
        camera=dict(location=[-0.55,-2.95,3.6],target=[.75,-.15,.1],lens_mm=35))

def merge(base,overrides):
    result=deepcopy(base)
    for key,value in overrides.items():result[key]=merge(result[key],value) if isinstance(value,dict) else deepcopy(value)
    return result

def validate(s):
    if set(s)-{'schema_version','scene','physics','render','camera','seed'}:raise ValueError('Unknown scenario field; nest physics overrides under physics')
    c=s['physics'];r=s['render']
    if set(c)-set(BASELINE_PHYSICS):raise ValueError('Unknown physics parameter')
    for key in ('ball_radius','ball_mass','ball_inertia_factor','ground_friction','substeps','solver_iterations'):
        if not math.isfinite(c[key]) or c[key]<=0:raise ValueError(f'{key} must be positive and finite')
    for key in ('ball_speed','ball_friction','ball_rolling_friction','terrain_roughness'):
        if not math.isfinite(c[key]) or c[key]<0:raise ValueError(f'{key} must be nonnegative and finite')
    if not 0<=c['ball_restitution']<=1:raise ValueError('Invalid restitution')
    if len(c['gravity'])!=3 or not all(math.isfinite(v) for v in c['gravity']):raise ValueError('Invalid gravity')
    lo,hi=c['terrain_bounds']
    if len(lo)!=2 or len(hi)!=2 or any(not math.isfinite(v) for v in lo+hi) or any(a>=b for a,b in zip(lo,hi)):raise ValueError('Invalid ground bounds')
    if len(c['terrain_cells'])!=2 or any(n<2 or n!=int(n) for n in c['terrain_cells']):raise ValueError('Invalid terrain discretization')
    if len(c['ball_start_xy'])!=2 or any(not a+c['ball_radius']<v<b-c['ball_radius'] for a,b,v in zip(lo,hi,c['ball_start_xy'])):raise ValueError('Ball starts outside terrain')
    for bump in c['bumps']:
        if len(bump)!=5 or not all(math.isfinite(v) for v in bump) or min(bump[3:])<=0:raise ValueError('Invalid terrain bump')
    if r['fps']<=0 or r['duration_sec']<=0 or r['slow_motion'] not in (1,2,4,8) or c['substeps']%r['slow_motion']:raise ValueError('Invalid sampling or slow motion')

"""Four seconds, fixed camera; presence-list bottles and a mid-run schedule."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
from copy import deepcopy
import json,math
from scene_geometry import BALL_RADIUS,BOTTLE_RADIUS,COM_HEIGHT,BOTTLE_SPACING,START_X

SCENE_NAME='tennis_bottle_collision'
# bottle_presence is [bottle_left, bottle_right, bottle_added]; the added slot
# is off at baseline and switched on only by an ADD edit. The added bottle's
# resting position and the ADD anchors live in physics so the edit vocabulary
# can resolve relative placements without scene coordinates entering the DSL.
# ball_add_anchor_position sits at the bottle's resting height above the ball's
# start: ADD resolves on that shared action plane, and interpolating towards
# the ball's true lower centre would seat an upright bottle below its rest height.
_ADDED_POSITION=[START_X/2,-BOTTLE_SPACING/4,COM_HEIGHT]
BASELINE_PHYSICS=dict(ball_mass=.057,bottle_mass=.026,initial_velocity=.85,
 bottle_restitution=.55,bottle_presence=[1,1,0],bottle_added_position=list(_ADDED_POSITION),
 ball_add_anchor_position=[START_X,0.,COM_HEIGHT],bottle_left_position=[0.,-BOTTLE_SPACING/2,COM_HEIGHT],
 ball_radius=BALL_RADIUS,bottle_radius=BOTTLE_RADIUS,timed_edits=[])
def defaults():
 return dict(schema_version=1,scene=SCENE_NAME,seed=0,physics=deepcopy(BASELINE_PHYSICS),
 render=dict(fps=24,duration_sec=4.,slow_motion=1,resolution=[960,540],samples=24),
 camera=dict(location=[-.9,-.7,.40],target=[.15,.06,.1],lens_mm=25))
def merge(base,overrides):
 result=deepcopy(base)
 for k,v in overrides.items():
  if k not in result:raise ValueError('Unknown field: '+k)
  result[k]=merge(result[k],v) if isinstance(v,dict) else deepcopy(v)
 return result
def _finite(v):return type(v) in (float,int) and math.isfinite(v)
def validate(s):
 if s['scene']!=SCENE_NAME or s['schema_version']!=1:raise ValueError('Wrong scene')
 if set(s['physics'])!=set(BASELINE_PHYSICS):raise ValueError('Unknown physics field')
 ph=s['physics'];r=s['render']
 for k,lo,hi in [('ball_mass',.01,.2),('bottle_mass',.005,.5),('initial_velocity',.1,3.)]:
  if not _finite(ph[k]) or not lo<=ph[k]<=hi:raise ValueError(k)
 if not _finite(ph['bottle_restitution']) or not 0<=ph['bottle_restitution']<=1:raise ValueError('bottle_restitution')
 presence=ph['bottle_presence']
 if not isinstance(presence,list) or len(presence)!=3 or any(type(v) is not int or v not in (0,1) for v in presence):
  raise ValueError('bottle_presence must be three 0/1 entries for [bottle_left, bottle_right, bottle_added]')
 for k in ('bottle_added_position','ball_add_anchor_position','bottle_left_position'):
  v=ph[k]
  if not isinstance(v,list) or len(v)!=3 or not all(_finite(c) for c in v):raise ValueError(k)
 for k in ('ball_radius','bottle_radius'):
  if not _finite(ph[k]) or ph[k]<=0:raise ValueError(k)
 schedule=ph['timed_edits']
 if not isinstance(schedule,list):raise ValueError('timed_edits must be a list')
 seen=set()
 for event in schedule:
  if not isinstance(event,dict) or set(event)!={'frame','params'}:raise ValueError('timed_edits entry')
  frame=event['frame'];params=event['params']
  if type(frame) is not int or not 2<=frame<=96 or frame in seen:raise ValueError('timed_edits frame')
  seen.add(frame)
  if not isinstance(params,dict) or not params or not set(params)<={'bottle_restitution','bottle_mass'}:
   raise ValueError('timed_edits params may set only bottle_restitution and bottle_mass')
  for key,value in params.items():
   if not _finite(value):raise ValueError('timed '+key+' must be finite')
   if key=='bottle_restitution' and not 0<=value<=1:raise ValueError('timed bottle_restitution must be within 0..1')
   if key=='bottle_mass' and not .005<=value<=.5:raise ValueError('timed bottle_mass must be within 0.005..0.5 kg')
 if type(r['fps']) is not int or r['fps']<=0 or 1440%r['fps']:raise ValueError('fps must divide 1440')
 if r['slow_motion']!=1 or r['duration_sec']!=4.:raise ValueError('Scene is fixed at 4 seconds in real time')
 if len(r['resolution'])!=2 or any(type(v) is not int or v<1 for v in r['resolution']):raise ValueError('resolution')
 if type(r['samples']) is not int or r['samples']<1:raise ValueError('samples')
 for k in ('location','target'):
  if len(s['camera'][k])!=3 or not all(_finite(v) for v in s['camera'][k]):raise ValueError('camera')
 if not _finite(s['camera']['lens_mm']) or s['camera']['lens_mm']<=0:raise ValueError('lens')
def add_scenario_arguments(p):
 from pathlib import Path
 p.add_argument('--scenario-json',type=Path);p.add_argument('--scenario-overrides-json',type=Path)
 p.add_argument('--initial-velocity',type=float);p.add_argument('--bottle-mass',type=float)
 p.add_argument('--bottle-restitution',type=float)
 return p
def load_scenario(args):
 s=defaults()
 for k in ('scenario_json','scenario_overrides_json'):
  if getattr(args,k,None):s=merge(s,json.loads(getattr(args,k).read_text(encoding='utf-8')))
 for k in BASELINE_PHYSICS:
  if getattr(args,k,None) is not None:s['physics'][k]=getattr(args,k)
 validate(s);return s
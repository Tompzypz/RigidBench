"""Free 3D PyBullet collision; one initial rolling velocity, no target animation."""

# Load this seven-file scene bundle and the reference common scripts.
import sys as _clean_sys
from pathlib import Path as _CleanPath
_clean_scene_dir = _CleanPath(__file__).resolve().parent
_clean_scripts_dir = _clean_scene_dir.parent
_PCVE_PROJECT_ROOT = next(p for p in _clean_scene_dir.parents if (p / "assets").is_dir())
if str(_clean_scripts_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_clean_scripts_dir))
if str(_clean_scene_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_clean_scene_dir))
import edit_vocab as _clean_scene_bundle
_clean_scene_bundle.install_scene_support()

import argparse,json,math,sys
from pathlib import Path
from tennis_bottle_collision.scene_config import *
from tennis_bottle_collision.scene_geometry import *
from tennis_bottle_collision.cache_contract import simulation_signature

def simulate(s):
 import pybullet as p
 validate(s);ph=s['physics'];fps=s['render']['fps'];count=4*fps;stride=SIM_HZ//fps
 client=p.connect(p.DIRECT)
 try:
  p.setGravity(0,0,-9.81);p.setTimeStep(1/SIM_HZ)
  p.setPhysicsEngineParameter(numSolverIterations=120,deterministicOverlappingPairs=1,restitutionVelocityThreshold=.015,contactBreakingThreshold=.0002)
  floor=p.createMultiBody(0,p.createCollisionShape(p.GEOM_BOX,halfExtents=[8,8,.05]),basePosition=[0,0,-.05])
  p.changeDynamics(floor,-1,lateralFriction=1.,restitution=.25)
  room_path=_PCVE_PROJECT_ROOT/'assets'/'scenarios'/'tennis_bottle_collision'/'room_collision.json'
  room=json.loads(room_path.read_text(encoding='utf-8'))
  import hashlib
  asset=_PCVE_PROJECT_ROOT/'assets'/'models'/room['asset']
  if hashlib.sha256(asset.read_bytes()).hexdigest()!=room['asset_sha256']:raise ValueError('Room collider is stale; export it again')
  room_shape=p.createCollisionShape(p.GEOM_MESH,vertices=room['vertices'],indices=room['indices'],flags=p.GEOM_FORCE_CONCAVE_TRIMESH)
  room_body=p.createMultiBody(0,room_shape)
  p.changeDynamics(room_body,-1,lateralFriction=.5,restitution=.15)
  sphere=p.createCollisionShape(p.GEOM_SPHERE,radius=BALL_RADIUS)
  hull=p.createCollisionShape(p.GEOM_MESH,vertices=hull_vertices())
  bodies={};positions=layout(ph)
  for k in KEYS:
   if not present(ph,k):bodies[k]=None;continue
   ball=k=='tennis_ball'
   b=p.createMultiBody(ph['ball_mass'] if ball else ph['bottle_mass'],sphere if ball else hull,basePosition=positions[k])
   p.changeDynamics(b,-1,lateralFriction=.42 if ball else .32,restitution=.65 if ball else ph['bottle_restitution'],
    rollingFriction=.0014 if ball else .0008,spinningFriction=.001,linearDamping=0.,angularDamping=.005,
    collisionMargin=.00005,contactProcessingThreshold=.001)
   if not ball:p.changeDynamics(b,-1,localInertiaDiagonal=[v*ph['bottle_mass']/EMPTY_BOTTLE_PROPERTIES['total_mass_kg'] for v in EMPTY_BOTTLE_PROPERTIES['inertia_diagonal_kg_m2']])
   bodies[k]=b
  # Settle the upright bottles before the visible clip starts.
  for _ in range(400):p.stepSimulation()
  for b in bodies.values():
   if b is not None:p.resetBaseVelocity(b,[0,0,0],[0,0,0])
  v=ph['initial_velocity'];p.resetBaseVelocity(bodies['tennis_ball'],[v,0,0],[0,v/BALL_RADIUS,0])
  room_first=None;first=None;first_pair={};max_pen=0.;max_tilt={k:0. for k in KEYS[1:] if bodies[k] is not None};frames=[]
  # Mid-run schedule: entries land inside the frame loop below and are applied
  # to the live PyBullet bodies, then the run continues from that state.
  timed_events=[];timed_by_frame={}
  for event in ph.get('timed_edits',[]):
   if not isinstance(event,dict) or set(event)!={'frame','params'}:raise ValueError(f'Invalid timed edit entry: {event!r}')
   frame=event['frame'];params=event['params']
   if type(frame) is not int or not 2<=frame<=count:raise ValueError(f'Timed edit frame {frame!r} is outside 2..{count}')
   unknown=set(params)-{'bottle_restitution','bottle_mass'}
   if unknown:raise ValueError(f'Timed edit sets {sorted(unknown)}, which this scene cannot change mid-run')
   for key,value in params.items():
    if not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError(f'Timed {key} must be finite')
    if key=='bottle_restitution' and not 0<=value<=1:raise ValueError('Timed bottle_restitution must be within 0..1')
    if key=='bottle_mass' and not .005<=value<=.5:raise ValueError('Timed bottle_mass must be within 0.005..0.5 kg')
   timed_by_frame.setdefault(frame,[]).append(dict(params))
  for step in range((count-1)*stride+1):
   t=step/SIM_HZ
   if room_first is None and p.getContactPoints(bodies['tennis_ball'],room_body):room_first=t
   for k,b in bodies.items():
    if b is None:continue
    for c in p.getContactPoints(bodyA=b):max_pen=max(max_pen,-c[8])
    if k!='tennis_ball':
     contacts=p.getContactPoints(bodies['tennis_ball'],b)
     if contacts and k not in first_pair:first_pair[k]=t;first=t if first is None else first
     q=p.getBasePositionAndOrientation(b)[1];mat=p.getMatrixFromQuaternion(q)
     max_tilt[k]=max(max_tilt[k],math.degrees(math.acos(max(-1.,min(1.,mat[8])))))
   if step%stride==0:
    frame_index=len(frames)+1
    for params in timed_by_frame.get(frame_index,[]):
     # Applied to the live world: every bottle still standing or falling gets
     # the edited dynamics on its body and the run carries on from the state
     # it had reached.
     updated=[]
     for k,b in bodies.items():
      if b is not None and k!='tennis_ball':
       if 'bottle_restitution' in params:p.changeDynamics(b,-1,restitution=float(params['bottle_restitution']))
       if 'bottle_mass' in params:p.changeDynamics(b,-1,mass=float(params['bottle_mass']))
       updated.append(k)
     timed_events.append(dict(frame=frame_index,time_sec=t,params=dict(params),
      from_values={key:ph[key] for key in params},bottles_updated=updated,
      applied_in_simulation=True,effective_from_frame=frame_index))
    f=dict(frame_index=len(frames)+1,time_sec=t)
    for k,b in bodies.items():
     if b is None:f[k]=dict(present=False);continue
     pos,q=p.getBasePositionAndOrientation(b);v,w=p.getBaseVelocity(b);mat=p.getMatrixFromQuaternion(q)
     f[k]=dict(present=True,location=list(pos),quaternion_xyzw=list(q),linear_velocity=list(v),angular_velocity=list(w),
      matrix_world=[list(mat[j*3:j*3+3])+[pos[j]] for j in range(3)]+[[0,0,0,1]])
    frames.append(f)
   if step<(count-1)*stride:p.stepSimulation()
  travel={k:math.dist(frames[0][k]['location'],frames[-1][k]['location']) for k in KEYS if bodies[k] is not None}
  quality=dict(valid=max_pen<.003,first_ball_room_contact_sec=room_first,first_impact_sec=first,ball_bottle_contact_sec=first_pair,max_penetration_m=max_pen,
   max_bottle_tilt_deg=max_tilt,displacement_m=travel,transmission_observed=any(travel.get(k,0)>.008 for k in KEYS[1:] if bodies[k] is not None),
   final_ball_speed_m_s=math.sqrt(sum(v*v for v in frames[-1]['tennis_ball']['linear_velocity'])),timed_events=timed_events)
  return dict(schema_version=2,scene=SCENE_NAME,scenario=s,simulation_signature=simulation_signature(s),
   playback_fps=fps,sample_fps=fps,slow_motion=1,frame_start=1,frame_end=count,physical_duration_sec=4.,playback_duration_sec=4.,
   solver=dict(engine='PyBullet DIRECT',hz=SIM_HZ,iterations=120,gravity=[0,0,-9.81],
    floor_friction=1.,ball_friction=.42,bottle_friction=.32,ball_rolling_friction=.0014,bottle_rolling_friction=.0008,
    note='Empty PET convex rigid bodies; effective friction, no wall deformation or fluid'),
   empty_bottle_reference=EMPTY_BOTTLE_PROPERTIES,
   objects={k:dict(present=bodies[k] is not None,mass_kg=ph['ball_mass'] if k=='tennis_ball' else ph['bottle_mass']) for k in KEYS},quality=quality,timed_events=timed_events,frames=frames)
 finally:p.disconnect(client)
def main():
 p=add_scenario_arguments(argparse.ArgumentParser(description=__doc__));p.add_argument('--out',type=Path,required=True)
 a=p.parse_args();d=simulate(load_scenario(a));a.out.parent.mkdir(parents=True,exist_ok=True)
 a.out.write_text(json.dumps(d,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
 (a.out.parent/'simulation_metrics.json').write_text(json.dumps(d['quality'],indent=2),encoding='utf-8')
 print(json.dumps(d['quality'],indent=2),flush=True)
if __name__=='__main__':main()

"""Two free thin-shell spheres, one real raised slab, no scripted trajectories."""
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

import argparse
from copy import deepcopy
import math
from pathlib import Path
import sys
from scene_config import load_scenario, validate, write_json, SCENE_NAME
from scene_geometry import *
from validate_soccer_step_collision import signature

def simulate(s):
    import pybullet as p
    validate(s)
    ph=s['physics']; fps=s['render']['fps']; count=round(fps*s['render']['duration_sec'])
    stride=SIM_HZ//fps
    client=p.connect(p.DIRECT)
    try:
        p.setGravity(0,0,-9.81,physicsClientId=client)
        p.setTimeStep(1/SIM_HZ,physicsClientId=client)
        p.setPhysicsEngineParameter(numSolverIterations=100,restitutionVelocityThreshold=.02,
            deterministicOverlappingPairs=1,contactBreakingThreshold=.0002,physicsClientId=client)
        static={}
        for name,center,size in boxes(ph['step_height']):
            shape=p.createCollisionShape(p.GEOM_BOX,halfExtents=[v/2 for v in size])
            b=p.createMultiBody(0,shape,basePosition=center); static[name]=b
            p.changeDynamics(b,-1,lateralFriction=.65,restitution=.22,
                rollingFriction=ph['surface_rolling_friction'] if name=='platform' else .0015,
                collisionMargin=.0001)
        masses=[ph['soccer_mass'],ph['basketball_mass']]
        bodies={}
        for i,(key,r,m) in enumerate(zip(KEYS,RADII,masses)):
            shape=p.createCollisionShape(p.GEOM_SPHERE,radius=r)
            b=p.createMultiBody(m,shape,basePosition=[START_X[i],LANE_Y,r+(ph['step_height'] if i else 0)])
            inertia=2/3*m*r*r
            p.changeDynamics(b,-1,lateralFriction=.8,rollingFriction=0,spinningFriction=0,
                restitution=ph[f'{key}_restitution'],linearDamping=0,angularDamping=0,
                localInertiaDiagonal=[inertia]*3,ccdSweptSphereRadius=r*.8,contactProcessingThreshold=0)
            v=ph['launch_speed'] if i==0 else 0
            p.resetBaseVelocity(b,[v,0,0],[0,v/r,0]); bodies[key]=b
        frames=[]; events=[]; touching=set(); max_pen=0.; climb_time=None
        pair_start=None; pair_pre=None; pair_post=None; receiver_pre_max=0.
        event_pairs=[('curb_contact',bodies['soccer'],static['platform']),
                     ('ball_collision',bodies['soccer'],bodies['basketball'])]
        # Mid-run schedule: entries land inside the frame loop below and are
        # applied to the live PyBullet world, then the run continues from that
        # state. Frame 1 is the initial state and is rejected on purpose.
        timed_events=[];timed_by_frame={}
        for event in ph.get('timed_edits',[]):
            if not isinstance(event,dict) or set(event)!={'frame','params'}:
                raise ValueError(f'Invalid timed edit entry: {event!r}')
            frame=event['frame'];params=event['params']
            if type(frame) is not int or not 2<=frame<=count:
                raise ValueError(f'Timed edit frame {frame!r} is outside 2..{count}')
            unknown=set(params)-{'launch_speed'}
            if unknown:
                raise ValueError(f'Timed edit sets {sorted(unknown)}, which this scene cannot change mid-run')
            speed=params['launch_speed']
            if not isinstance(speed,(int,float)) or not .1<=speed<=3.:
                raise ValueError('Timed launch_speed must be finite and within 0.1..3 m/s')
            timed_by_frame.setdefault(frame,[]).append(dict(params))
        previous_v={k:list(p.getBaseVelocity(b)[0]) for k,b in bodies.items()}
        for step in range((count-1)*stride+1):
            t=step/SIM_HZ
            velocity={k:list(p.getBaseVelocity(b)[0]) for k,b in bodies.items()}
            for label,a,b in event_pairs:
                contacts=[c for c in p.getContactPoints(a,b) if c[8] <= .0001]
                if contacts and label not in touching:
                    if label=='curb_contact' and any(e['event']==label for e in events):
                        pass  # Store first step impact; later top-face contacts are not new curb hits.
                    else:
                        events.append(dict(event=label,time_sec=t,frame_index=min(count,1+math.ceil(t*fps))))
                    if label=='ball_collision' and pair_start is None:
                        pair_start=t; pair_pre=deepcopy(previous_v)
                if label=='ball_collision' and not contacts and label in touching:
                    if pair_post is None: pair_post=deepcopy(velocity)
                if contacts: touching.add(label)
                else: touching.discard(label)
            for b in bodies.values():
                for c in p.getContactPoints(bodyA=b): max_pen=max(max_pen,-c[8])
            pos=p.getBasePositionAndOrientation(bodies['soccer'])[0]
            if climb_time is None and pos[0]>=RADII[0] and pos[2]>=ph['step_height']+RADII[0]-.002:
                climb_time=t
            if pair_start is None: receiver_pre_max=max(receiver_pre_max,math.dist(velocity['basketball'],[0,0,0]))
            if step%stride==0:
                frame_index=len(frames)+1
                for params in timed_by_frame.get(frame_index,[]):
                    # Applied to the live world: the ball is re-launched at the
                    # edited speed with matching no-slip spin, and the run
                    # carries on from exactly the state it had reached.
                    speed=float(params['launch_speed']);radius=RADII[0]
                    linear_before,angular_before=p.getBaseVelocity(bodies['soccer'])
                    p.resetBaseVelocity(bodies['soccer'],[speed,0,0],[0,speed/radius,0])
                    linear_after,angular_after=p.getBaseVelocity(bodies['soccer'])
                    timed_events.append(dict(frame=frame_index,time_sec=t,parameter='launch_speed',
                        from_value=ph['launch_speed'],to_value=speed,
                        before=dict(soccer_linear_velocity=list(linear_before),soccer_angular_velocity=list(angular_before)),
                        after=dict(soccer_linear_velocity=list(linear_after),soccer_angular_velocity=list(angular_after)),
                        applied_in_simulation=True,effective_from_frame=frame_index))
                row=dict(frame_index=len(frames)+1,time_sec=t)
                for key,b in bodies.items():
                    pos,q=p.getBasePositionAndOrientation(b); v,w=p.getBaseVelocity(b)
                    rot=p.getMatrixFromQuaternion(q)
                    row[key]=dict(location=list(pos),quaternion_xyzw=list(q),linear_velocity=list(v),angular_velocity=list(w),
                        matrix_world=[list(rot[j*3:j*3+3])+[pos[j]] for j in range(3)]+[[0,0,0,1]])
                frames.append(row)
            previous_v=velocity
            if step<(count-1)*stride: p.stepSimulation()
        metrics=dict(climbed_step=climb_time is not None,climb_time_sec=climb_time,
            ball_collision_observed=pair_start is not None,first_ball_collision_sec=pair_start,
            impact_pre_velocity=pair_pre,impact_post_velocity=pair_post,
            basketball_preimpact_max_speed_m_s=receiver_pre_max,
            basketball_travel_m=frames[-1]['basketball']['location'][0]-START_X[1],
            soccer_final_x_m=frames[-1]['soccer']['location'][0],
            basketball_final_x_m=frames[-1]['basketball']['location'][0],
            max_contact_penetration_m=max_pen,
            soccer_max_center_height_m=max(f['soccer']['location'][2] for f in frames),
            timed_events=timed_events)
        quality=dict(valid=max_pen<.002 and receiver_pre_max<.02,**metrics)
        return dict(schema_version=1,scene=SCENE_NAME,scenario=deepcopy(s),simulation_signature=signature(s),
            fps=fps,frame_end=count,duration_sec=s['render']['duration_sec'],sampled_end_sec=(count-1)/fps,
            solver=dict(name='PyBullet',clock_hz=SIM_HZ,constants=constants(),inertia='thin spherical shell: 2/3 m r^2'),
            objects={k:dict(radius_m=RADII[i],mass_kg=masses[i],origin='sphere center') for i,k in enumerate(KEYS)},
            events=events,timed_events=timed_events,quality=quality,frames=frames)
    finally:
        p.disconnect(client)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--scenario-json',type=Path)
    parser.add_argument('--scenario-overrides-json',type=Path)
    args=parser.parse_args()
    data=simulate(load_scenario(args.scenario_json,args.scenario_overrides_json))
    write_json(args.out,data); write_json(args.out.parent/'simulation_metrics.json',data['quality'])
    print(data['quality'])
    if not data['quality']['valid']: raise RuntimeError('Physics validation failed')

if __name__=='__main__': main()

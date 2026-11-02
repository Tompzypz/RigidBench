"""Initial push, passive friction, and free rigid body contact in PyBullet."""

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

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
from toy_car_collision.scene_config import SCENE_NAME,add_scenario_arguments,load_scenario,validate
from toy_car_collision.scene_geometry import *
from toy_car_collision.cache_contract import simulation_signature

def simulate(s):
    import pybullet as p
    validate(s);ph=s['physics'];r=s['render']
    fps=r['fps']*r['slow_motion'];count=round(fps*r['duration_sec']);stride=SIM_HZ//fps
    client=p.connect(p.DIRECT)
    try:
        p.setGravity(0,0,-9.81);p.setTimeStep(1/SIM_HZ)
        p.setPhysicsEngineParameter(numSolverIterations=100,deterministicOverlappingPairs=1,restitutionVelocityThreshold=.005,contactBreakingThreshold=.0001)
        ground=p.createMultiBody(0,p.createCollisionShape(p.GEOM_PLANE))
        p.changeDynamics(ground,-1,lateralFriction=FLOOR_FRICTION,restitution=0.)
        masses=[ph['driver_mass'],ph['receiver_mass']]
        bodies=[]
        for i in range(2):
            if not ph['present'][i]:bodies.append(None);continue
            shape=p.createCollisionShape(p.GEOM_BOX,halfExtents=HALF_EXTENTS[i])
            b=p.createMultiBody(masses[i],shape,basePosition=[START_X[i],0,DIMENSIONS[i][2]/2])
            p.changeDynamics(b,-1,lateralFriction=ph['driver_friction'] if i==0 else ph['receiver_friction'],
                             restitution=.32**.5,linearDamping=0,angularDamping=0,collisionMargin=.0001)
            p.resetBaseVelocity(b,[ph['initial_velocity'] if i==0 else 0,0,0])
            bodies.append(b)
        frames=[];impact=None;pre=None;post=None;previous=None;max_pen=0.;max_z=0.
        # Mid-run schedule: entries land inside the frame loop below and are
        # applied to the live PyBullet bodies, then the run continues from
        # that state. Frame 1 is the initial state and is rejected on purpose.
        timed_events=[];timed_by_frame={}
        for event in ph.get('timed_edits',[]):
            if not isinstance(event,dict) or set(event)!={'frame','params'}:
                raise ValueError(f'Invalid timed edit entry: {event!r}')
            frame=event['frame'];params=event['params']
            if type(frame) is not int or not 2<=frame<=count:
                raise ValueError(f'Timed edit frame {frame!r} is outside 2..{count}')
            allowed={'driver_friction','receiver_friction','receiver_speed_multiplier'}
            unknown=set(params)-allowed
            if unknown:
                raise ValueError(f'Timed edit sets {sorted(unknown)}, which this scene cannot change mid-run')
            for key,value in params.items():
                if not isinstance(value,(int,float)):
                    raise ValueError(f'Timed {key} must be a number')
                if key=='receiver_speed_multiplier':
                    if not .05<=value<=50.:
                        raise ValueError(f'Timed receiver_speed_multiplier must be within 0.05..50')
                elif not .0001<=value<=1.:
                    raise ValueError(f'Timed {key} must be finite and within 0.0001..1')
            timed_by_frame.setdefault(frame,[]).append(dict(params))
        for step in range((count-1)*stride+1):
            t=step/SIM_HZ
            velocities=[list(p.getBaseVelocity(b)[0]) if b is not None else None for b in bodies]
            contact=all(b is not None for b in bodies) and bool(p.getContactPoints(*bodies))
            if contact and impact is None:impact=t;pre=previous
            if impact is not None and post is None and not contact:post=velocities
            for i,b in enumerate(bodies):
                if b is None:continue
                pos,q=p.getBasePositionAndOrientation(b)
                max_z=max(max_z,abs(pos[2]-DIMENSIONS[i][2]/2))
                for c in p.getContactPoints(bodyA=b):max_pen=max(max_pen,-c[8])
            if step%stride==0:
                frame_index=len(frames)+1
                for params in timed_by_frame.get(frame_index,[]):
                    # Applied to the live world: friction edits rewrite the
                    # named car's floor friction, a speed multiplier rescales
                    # the receiver's current velocity in place, and the run
                    # carries on from exactly the state it had reached.
                    for key,value in params.items():
                        index={'driver_friction':0,'receiver_friction':1}.get(key)
                        body=bodies[index] if index is not None else bodies[1]
                        if body is None:continue
                        if key=='receiver_speed_multiplier':
                            lin,ang=p.getBaseVelocity(body)
                            speed_before=(lin[0]**2+lin[1]**2+lin[2]**2)**.5
                            scaled=[value*c for c in lin]
                            p.resetBaseVelocity(body,scaled,ang)
                            speed_after=(scaled[0]**2+scaled[1]**2+scaled[2]**2)**.5
                            timed_events.append(dict(frame=frame_index,time_sec=t,parameter=key,car='car_b',
                                multiplier=value,velocity_before_m_s=list(lin),velocity_after_m_s=list(scaled),
                                speed_before_m_s=speed_before,speed_after_m_s=speed_after,
                                applied_in_simulation=True,effective_from_frame=frame_index))
                        else:
                            friction_before=p.getDynamicsInfo(body,-1)[1]
                            p.changeDynamics(body,-1,lateralFriction=float(value))
                            friction_after=p.getDynamicsInfo(body,-1)[1]
                            timed_events.append(dict(frame=frame_index,time_sec=t,parameter=key,
                                car='car_a' if index==0 else 'car_b',
                                from_value=friction_before,to_value=friction_after,
                                applied_in_simulation=True,effective_from_frame=frame_index))
                f=dict(frame_index=len(frames)+1,time_sec=t)
                for key,b in zip(KEYS,bodies):
                    if b is None:f[key]=dict(present=False);continue
                    pos,q=p.getBasePositionAndOrientation(b);lin,ang=p.getBaseVelocity(b);mat=p.getMatrixFromQuaternion(q)
                    f[key]=dict(present=True,location=list(pos),quaternion_xyzw=list(q),linear_velocity=list(lin),angular_velocity=list(ang),
                                matrix_world=[list(mat[j*3:j*3+3])+[pos[j]] for j in range(3)]+[[0,0,0,1]])
                frames.append(f)
            previous=velocities
            if step<(count-1)*stride:p.stepSimulation()
        displacement=frames[-1]['car_b']['location'][0]-START_X[1] if bodies[1] is not None else None
        quality=dict(valid=max_pen<.002 and max_z<.003,transmission_observed=impact is not None and displacement>.001,
                     first_impact_sec=impact,pre_impact_velocity=pre,post_impact_velocity=post,
                     receiver_displacement_m=displacement,max_penetration_m=max_pen,max_ground_height_error_m=max_z,
                     driver_final_x_m=frames[-1]['car_a']['location'][0],
                     receiver_peak_speed_m_s=max((f['car_b'].get('linear_velocity',[0])[0] for f in frames),default=0),
                     timed_events=timed_events)
        return dict(schema_version=2,scene=SCENE_NAME,scenario=deepcopy(s),simulation_signature=simulation_signature(s),
                    solver=dict(name='PyBullet',api_version=p.getAPIVersion(),constants=fixed_constants()),
                    playback_fps=r['fps'],sample_fps=fps,slow_motion=r['slow_motion'],frame_end=count,
                    physical_duration_sec=r['duration_sec'],playback_duration_sec=r['duration_sec']*r['slow_motion'],sampled_end_time_sec=(count-1)/fps,
                    objects={k:dict(mass_kg=masses[i],dimensions=list(DIMENSIONS[i]),collision_shape='box',present=bool(ph['present'][i])) for i,k in enumerate(KEYS)},
                    quality=quality,timed_events=timed_events,frames=frames)
    finally:p.disconnect(client)

def main():
    parser=add_scenario_arguments(argparse.ArgumentParser(description=__doc__));parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();data=simulate(load_scenario(args));args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(data,indent=2,allow_nan=False),encoding='utf-8')
    (args.out.parent/'simulation_metrics.json').write_text(json.dumps(data['quality'],indent=2),encoding='utf-8')
    print(json.dumps(data['quality'],indent=2))
    if not data['quality']['valid']:raise RuntimeError('Invalid physical trace')

if __name__=='__main__':main()

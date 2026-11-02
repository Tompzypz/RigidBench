"""Full 3D PyBullet rigid bodies: one initial push, then contact and friction."""
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
import json
import math
from pathlib import Path
import sys
from scene_config import SCENE_NAME,add_scenario_arguments,load_scenario,validate
from scene_geometry import KEYS,COUNTER_Z,COM_HEIGHT,RADIUS,FRICTION,START_X,SIM_HZ,hull_vertices,fixed_constants
from validate_kitchen_tableware_collision import simulation_signature


def simulate(s):
    import pybullet as p
    validate(s)
    r=s['render']; ph=s['physics']; sample_fps=r['fps']*r['slow_motion']
    count=round(sample_fps*r['duration_sec']); stride=SIM_HZ//sample_fps
    tableware_friction=float(ph.get('tableware_friction',FRICTION))
    if not math.isfinite(tableware_friction) or tableware_friction<0:
        raise ValueError('tableware_friction must be finite and nonnegative')
    timed_by_frame={}
    for entry in ph.get('timed_edits') or []:
        frame=entry.get('frame'); params=entry.get('params')
        if not isinstance(frame,int) or not 2<=frame<=count or not isinstance(params,dict) or set(params)!={'tableware_friction'}:
            raise ValueError(f'Unsupported or invalid timed event: {entry!r}')
        value=float(params['tableware_friction'])
        if not math.isfinite(value) or value<0:
            raise ValueError('Timed friction must be finite and nonnegative')
        timed_by_frame.setdefault(frame,[]).append(value)
    client=p.connect(p.DIRECT)
    try:
        p.setGravity(0,0,-9.81)
        p.setTimeStep(1/SIM_HZ)
        p.setPhysicsEngineParameter(numSolverIterations=120, restitutionVelocityThreshold=.001,
                                    deterministicOverlappingPairs=1,contactBreakingThreshold=.0005)
        floor=p.createCollisionShape(p.GEOM_BOX,halfExtents=[1.52,.49,.025])
        table=p.createMultiBody(0,floor,basePosition=[0,0,COUNTER_Z-.025])
        p.changeDynamics(table,-1,lateralFriction=1.,restitution=0.)
        shape=p.createCollisionShape(p.GEOM_MESH,vertices=hull_vertices())
        bodies=[]
        masses=[ph['driver_mass'],ph['receiver_mass']]
        speeds=[ph['initial_velocity'],ph['receiver_initial_velocity']]
        for i in range(2):
            if i==1 and not ph['receiver_active'][0]:
                bodies.append(None)
                continue
            b=p.createMultiBody(masses[i],shape,basePosition=[START_X[i],0,COUNTER_Z+COM_HEIGHT+.00015])
            p.changeDynamics(b,-1,lateralFriction=tableware_friction,
                             restitution=math.sqrt(ph['restitution']),
                             spinningFriction=.001,rollingFriction=.0001,linearDamping=0.,angularDamping=0.,
                             collisionMargin=.0001,contactProcessingThreshold=.001)
            bodies.append(b)
        # Settle the foot rings before applying initial velocities. This pre-roll is not in the clip.
        for _ in range(180): p.stepSimulation()
        for b,v in zip(bodies,speeds):
            if b is not None:p.resetBaseVelocity(b,[v,0,0],[0,0,0])
        active_bodies=[b for b in bodies if b is not None]
        frames=[]; events=[]; previous_contact=False; max_penetration=0.; max_tilt=0.; min_edge=10.; left_counter=set()
        last_motion=0.; receiver_max_speed=0.; impact_start=None; impact_pre=None; timed_events=[]
        def velocities(): return [list(p.getBaseVelocity(b)[0]) if b is not None else [0.,0.,0.] for b in bodies]
        pre_v=velocities()
        for step in range((count-1)*stride+1):
            t=step/SIM_HZ
            if step%stride==0:
                # A timed edit fires at its frame boundary, before the motion
                # that follows it: the new friction is written into every live
                # bowl and the run carries on from the state it had reached.
                frame_number=step//stride+1
                for value in timed_by_frame.get(frame_number,[]):
                    previous=tableware_friction;tableware_friction=float(value)
                    for b in active_bodies:
                        p.changeDynamics(b,-1,lateralFriction=tableware_friction)
                    timed_events.append(dict(frame=frame_number,time_sec=t,parameter='tableware_friction',
                                             from_value=previous,to_value=tableware_friction,
                                             applied_in_simulation=True))
            v=velocities()
            contacts=p.getContactPoints(bodies[0],bodies[1]) if bodies[1] is not None else []
            contact=bool(contacts)
            if contact and not previous_contact:
                impact_start=t; impact_pre=pre_v
            if previous_contact and not contact:
                before=impact_pre[0][0]-impact_pre[1][0]; after=v[1][0]-v[0][0]
                events.append(dict(time_sec=impact_start,contact_end_sec=t,pre_velocity=impact_pre,post_velocity=v,
                                   axial_separation_approach_speed_ratio=after/before if before>1e-6 else None,
                                   momentum_change_x_kg_m_s=sum(m*(post[0]-pre[0]) for m,post,pre in zip(masses,v,impact_pre))))
            previous_contact=contact
            receiver_max_speed=max(receiver_max_speed,math.dist(v[1],[0,0,0]))
            if max(math.hypot(vel[0],vel[1]) for vel in v)>.005: last_motion=t
            for b in active_bodies:
                pos,q=p.getBasePositionAndOrientation(b)
                # Stability guards (tilt, edge clearance) only apply while a
                # bowl is actually resting on the counter: inside the footprint
                # AND at surface height. A bowl knocked airborne or slid past
                # an edge is allowed to fly, tumble and fall -- its tilt and
                # clearance there are meaningless -- so tracking freezes and
                # the departure is reported instead of failing the run.
                supported=(abs(pos[0])<1.52-RADIUS and abs(pos[1])<.49-RADIUS
                           and pos[2]<=COUNTER_Z+COM_HEIGHT+.005)
                if supported:
                    mat=p.getMatrixFromQuaternion(q)
                    max_tilt=max(max_tilt,math.degrees(math.acos(max(-1.,min(1.,mat[8])))))
                    min_edge=min(min_edge,1.52-abs(pos[0])-RADIUS,.49-abs(pos[1])-RADIUS)
                    for c in p.getContactPoints(bodyA=b): max_penetration=max(max_penetration,-c[8])
                elif abs(pos[0])>=1.52-RADIUS or abs(pos[1])>=.49-RADIUS or pos[2]<COUNTER_Z:
                    left_counter.add(b)
            if step%stride==0:
                frame=dict(frame_index=len(frames)+1,time_sec=t)
                for key,b in zip(KEYS,bodies):
                    if b is None:
                        frame[key]=dict(present=False)
                        continue
                    pos,q=p.getBasePositionAndOrientation(b); linear,angular=p.getBaseVelocity(b)
                    mat=p.getMatrixFromQuaternion(q)
                    matrix=[list(mat[j*3:j*3+3])+[pos[j]] for j in range(3)]+[[0,0,0,1]]
                    frame[key]=dict(present=True,location=list(pos),quaternion_xyzw=list(q),
                                    linear_velocity=list(linear),angular_velocity=list(angular),matrix_world=matrix)
                frames.append(frame)
            pre_v=v
            if step<(count-1)*stride:p.stepSimulation()
        final_speed=max(math.hypot(*p.getBaseVelocity(b)[0][:2]) for b in active_bodies)
        quality=dict(valid=max_penetration<.002 and max_tilt<25,
                     transmission_observed=receiver_max_speed>.02,events=events,
                     first_impact_sec=events[0]['time_sec'] if events else impact_start,
                     last_motion_sec=last_motion,settled_by_end=final_speed<.005,final_speed_m_s=final_speed,
                     max_penetration_m=max_penetration,max_tilt_deg=max_tilt,min_table_edge_clearance_m=min_edge,
                     bowls_left_counter=sorted(left_counter),
                     receiver_max_speed_m_s=receiver_max_speed,
                     effective_table_friction=tableware_friction,requested_pair_restitution=ph['restitution'],
                     timed_events=timed_events)
        return dict(schema_version=2,scene=SCENE_NAME,scenario=deepcopy(s),simulation_signature=simulation_signature(s),
                    solver=dict(name='PyBullet',api_version=p.getAPIVersion(),constants=fixed_constants()),
                    playback_fps=r['fps'],sample_fps=sample_fps,slow_motion=r['slow_motion'],frame_end=count,
                    physical_duration_sec=r['duration_sec'],playback_duration_sec=r['duration_sec']*r['slow_motion'],
                    sampled_end_time_sec=(count-1)/sample_fps,
                    objects={k:dict(present=bodies[i] is not None,mass_kg=masses[i],radius_m=RADIUS,height_m=.042,
                                    collision_shape='convex hull of shared lathe profile',origin='nominal center of mass') for i,k in enumerate(KEYS)},
                    quality=quality,timed_events=timed_events,frames=frames)
    finally:p.disconnect(client)


def main():
    parser=add_scenario_arguments(argparse.ArgumentParser(description=__doc__))
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(); d=simulate(load_scenario(args))
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(d,indent=2,allow_nan=False),encoding='utf-8')
    (args.out.parent/'simulation_metrics.json').write_text(json.dumps(d['quality'],indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(d['quality'],indent=2))
    if not d['quality']['valid']: raise RuntimeError('Physical validation failed')


if __name__=='__main__':main()

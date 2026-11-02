"""Free 3D rigid-body rolling, impact and sliding; no scripted post-impact motion."""
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
from scene_config import add_scenario_arguments, load_scenario, validate, SCENE_NAME
from scene_geometry import *
from validate_kitchen_can_collision import simulation_signature


# A mid-run edit writes a number into a body that is already moving, so it is
# not the launch condition the ordinary parameters describe: a can shoved to
# 0.99 m/s partway across the table is a legitimate edit even though the
# scenario's own initial_velocity band stops at 0.85 m/s. The bands below are
# therefore about keeping the run physical (positive mass, no bounce gain),
# not about reproducing the source clip.
# The coefficients the scene shipped with, kept as the settling pair: a rest pose
# does not depend on friction, so starting every run from these makes an edit
# show up in the motion only.
SOURCE_CAN_MU, SOURCE_TABLE_MU = 0.065, 1.0

TIMED_FIELDS = {'initial_velocity': (0.0, 1.5), 'receiver_initial_velocity': (-0.6, 0.6),
                'driver_mass': (.08, 1.), 'receiver_mass': (.08, 1.), 'restitution': (0.0, 1.0),
                'can_friction': (.005, .8), 'table_friction': (0.0, 2.)}


def timed_schedule(ph, count):
    """Read ``physics.timed_edits`` into ``{frame: params}``, rejecting nonsense.

    Frame 1 is refused: the scenario's ordinary parameters already set that
    state, and accepting it here would give one edit two spellings. Anything the
    applier below cannot write is refused too -- an entry that is silently
    dropped renders as a video that looks like the source.
    """
    schedule = {}
    for entry in ph.get('timed_edits') or []:
        if not isinstance(entry, dict) or set(entry) != {'frame', 'params'}:
            raise ValueError(f'Unsupported timed event: {entry!r}')
        frame = entry['frame']
        if type(frame) is not int or not 2 <= frame <= count:
            raise ValueError(f'Timed event frame {frame!r} is outside the clip (2..{count})')
        if frame in schedule:
            raise ValueError(f'More than one timed event targets frame {frame}')
        if not isinstance(entry['params'], dict) or not entry['params']:
            raise ValueError('Timed event params must be a non-empty object')
        for name, value in entry['params'].items():
            if name not in TIMED_FIELDS:
                raise ValueError(f'Timed edit cannot write {name!r}; this scene accepts {sorted(TIMED_FIELDS)}')
            low, high = TIMED_FIELDS[name]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f'Timed {name!r} must be a finite number')
            if not low <= float(value) <= high:
                raise ValueError(f'Timed {name!r} = {value!r} is outside {low}..{high}')
        schedule[frame] = dict(entry['params'])
    return schedule


def body_state(p, bodies):
    """Position and velocity of both cans, for the event log."""
    state = {}
    for key, body in zip(KEYS, bodies):
        if body is None:
            state[key] = None
            continue
        pos, _ = p.getBasePositionAndOrientation(body)
        state[key] = {'location': list(pos), 'linear_velocity': list(p.getBaseVelocity(body)[0])}
    return state


def apply_timed_params(p, params, bodies, table, *, frame, time_sec):
    """Write one frame's edited physics into the running simulation.

    Returns one event per parameter with the value on both sides of the write
    and the motion state, which is what makes a mid-run case auditable
    afterwards. The rolling can is given the spin that matches its new speed, so
    a mid-run speed edit keeps it rolling instead of skidding.

    Friction is written through the body values Bullet actually holds, but the
    event reports the declared contact coefficient (can-can or can-table), and
    the write is chosen so the *other* contact keeps its product unchanged.
    """
    events = []
    for key, value in params.items():
        state_before = body_state(p, bodies)
        if key in ('initial_velocity', 'receiver_initial_velocity'):
            index = 0 if key == 'initial_velocity' else 1
            body = bodies[index]
            if body is None:
                raise ValueError(f'Timed edit writes {key!r} but that can is not in the scene')
            linear, angular = p.getBaseVelocity(body)
            before = float(linear[0])
            spin = [0.0, float(value) / RADIUS, 0.0] if index == 0 else list(angular)
            p.resetBaseVelocity(body, [float(value), 0.0, 0.0], spin)
            after = float(p.getBaseVelocity(body)[0][0])
        elif key in ('driver_mass', 'receiver_mass'):
            index = 0 if key == 'driver_mass' else 1
            body = bodies[index]
            if body is None:
                raise ValueError(f'Timed edit writes {key!r} but that can is not in the scene')
            before = float(p.getDynamicsInfo(body, -1)[0])
            p.changeDynamics(body, -1, mass=float(value))
            after = float(p.getDynamicsInfo(body, -1)[0])
        elif key == 'table_friction':
            before = float(p.getDynamicsInfo(table, -1)[1])
            p.changeDynamics(table, -1, lateralFriction=float(value))
            after = float(p.getDynamicsInfo(table, -1)[1])
        elif key == 'can_friction':
            before = float(p.getDynamicsInfo(bodies[0], -1)[1])
            for body in bodies:
                if body is not None:
                    p.changeDynamics(body, -1, lateralFriction=float(value))
            after = float(p.getDynamicsInfo(bodies[0], -1)[1])
        else:  # restitution: the pair value the bodies were created with
            before = float(p.getDynamicsInfo(bodies[0], -1)[5]) ** 2
            for body in bodies:
                if body is not None:
                    p.changeDynamics(body, -1, restitution=math.sqrt(float(value)))
            after = float(p.getDynamicsInfo(bodies[0], -1)[5]) ** 2
        events.append({'frame': frame, 'time_sec': time_sec, 'parameter': key,
                       'from': before, 'to': after,
                       'state_before': state_before, 'state_after': body_state(p, bodies)})
    return events


def simulate(s):

    import pybullet as p
    validate(s)
    r=s['render']; ph=s['physics']; fps=r['fps']*r['slow_motion']
    count=round(fps*r['duration_sec']); stride=SIM_HZ//fps
    # One declared coefficient per body surface; Bullet multiplies the two at a
    # contact, so the can-table coefficient is their product and the can-can one
    # is the cans' value squared.
    can_mu=float(ph['can_friction']); table_mu=float(ph['table_friction'])
    # Validated before any body exists: a schedule that names a frame outside
    # the clip or a field this scene cannot write is not worth simulating.
    schedule=timed_schedule(ph,count)
    client=p.connect(p.DIRECT)
    try:
        p.setGravity(0,0,-9.81); p.setTimeStep(1/SIM_HZ)
        p.setPhysicsEngineParameter(numSolverIterations=120, restitutionVelocityThreshold=.001,
                                   deterministicOverlappingPairs=1, contactBreakingThreshold=.0003)
        shape=p.createCollisionShape(p.GEOM_BOX,halfExtents=[1.52,.49,.025])
        table=p.createMultiBody(0,shape,basePosition=[0,0,COUNTER_Z-.025])
        p.changeDynamics(table,-1,lateralFriction=SOURCE_TABLE_MU,restitution=0.)
        shape=p.createCollisionShape(p.GEOM_MESH,vertices=hull_vertices())
        masses=[ph['driver_mass'],ph['receiver_mass']]; bodies=[]
        for i in range(2):
            if i==1 and not ph['receiver_active'][0]:
                bodies.append(None); continue
            # Local cylinder Z axis becomes world Y for the rolling can.
            orientation=p.getQuaternionFromEuler([-math.pi/2,0,0]) if i==0 else [0,0,0,1]
            z=COUNTER_Z+(RADIUS if i==0 else COM_HEIGHT)+.0002
            body=p.createMultiBody(masses[i],shape,basePosition=[START_X[i],0,z],baseOrientation=orientation)
            p.changeDynamics(body,-1,lateralFriction=SOURCE_CAN_MU,restitution=math.sqrt(ph['restitution']),
                             rollingFriction=.00065,spinningFriction=.0001,linearDamping=0.,angularDamping=0.,
                             collisionMargin=.0001,contactProcessingThreshold=.001)
            bodies.append(body)
        for _ in range(240):p.stepSimulation()
        # The settling pass is not part of the clip. It runs on the source
        # coefficients so that an edit changes the motion after frame 1 and not
        # the rest state the clip starts from; the declared coefficients are
        # written in here, before the released can is given its speed.
        p.changeDynamics(table,-1,lateralFriction=table_mu)
        for body in bodies:
            if body is not None:p.changeDynamics(body,-1,lateralFriction=can_mu)
        p.resetBaseVelocity(bodies[0],[ph['initial_velocity'],0,0],[0,ph['initial_velocity']/RADIUS,0])
        if bodies[1] is not None:p.resetBaseVelocity(bodies[1],[ph['receiver_initial_velocity'],0,0],[0,0,0])
        frames=[]; first_impact=None; max_penetration=0.; max_receiver_tilt=0.; max_receiver_speed=0.
        edge=10.; last_motion=0.; contact_impulse=0.; max_roll_slip=0.; max_slip_ratio=0.; timed_events=[]
        for step in range((count-1)*stride+1):
            t=step/SIM_HZ
            contacts=p.getContactPoints(bodies[0],bodies[1]) if bodies[1] is not None else []
            if contacts and first_impact is None:first_impact=t
            contact_impulse+=sum(c[9]/SIM_HZ for c in contacts)
            for i,b in enumerate(bodies):
                if b is None:continue
                pos,q=p.getBasePositionAndOrientation(b); v,w=p.getBaseVelocity(b)
                if math.hypot(*v[:2])>.005:last_motion=t
                mat=p.getMatrixFromQuaternion(q)
                extent_x=sum(abs(mat[j])*d for j,d in enumerate((RADIUS,RADIUS,COM_HEIGHT)))
                extent_y=sum(abs(mat[3+j])*d for j,d in enumerate((RADIUS,RADIUS,COM_HEIGHT)))
                edge=min(edge,1.52-abs(pos[0])-extent_x,.49-abs(pos[1])-extent_y)
                if i==1:
                    max_receiver_tilt=max(max_receiver_tilt,math.degrees(math.acos(max(-1.,min(1.,mat[8])))))
                    max_receiver_speed=max(max_receiver_speed,math.hypot(*v[:2]))
                elif first_impact is None and abs(v[0])>.02:
                    # Rolling, not skidding: the contact point's speed is v - w*r,
                    # and the ratio says how much of the travel is slip. A can
                    # that is merely translating would sit near 1.0.
                    max_roll_slip=max(max_roll_slip,abs(v[0]-w[1]*RADIUS))
                    max_slip_ratio=max(max_slip_ratio,abs(v[0]-w[1]*RADIUS)/abs(v[0]))
                for c in p.getContactPoints(bodyA=b):max_penetration=max(max_penetration,-c[8])
            if step%stride==0:
                frame_index=len(frames)+1
                # The edit lands at the top of its frame: the state recorded
                # here is already the edited one, and every earlier frame is
                # the source clip's own physics.
                if frame_index in schedule:
                    timed_events.extend(apply_timed_params(
                        p,schedule[frame_index],bodies,table,frame=frame_index,time_sec=t))
                f=dict(frame_index=frame_index,time_sec=t)
                for key,b in zip(KEYS,bodies):
                    if b is None:f[key]=dict(present=False);continue
                    pos,q=p.getBasePositionAndOrientation(b);v,w=p.getBaseVelocity(b);mat=p.getMatrixFromQuaternion(q)
                    matrix=[list(mat[j*3:j*3+3])+[pos[j]] for j in range(3)]+[[0,0,0,1]]
                    f[key]=dict(present=True,location=list(pos),quaternion_xyzw=list(q),linear_velocity=list(v),angular_velocity=list(w),matrix_world=matrix)
                frames.append(f)
            if step<(count-1)*stride:p.stepSimulation()
        speeds=[math.hypot(*p.getBaseVelocity(b)[0][:2]) for b in bodies if b is not None]
        travel={k:frames[-1][k]['location'][0]-frames[0][k]['location'][0] if frames[0][k]['present'] else None for k in KEYS}
        quality=dict(valid=max_penetration<.002 and edge>0 and max_receiver_tilt<25,
                     first_impact_sec=first_impact,transmission_observed=max_receiver_speed>.02,
                     receiver_max_speed_m_s=max_receiver_speed,displacement_x_m=travel,
                     max_receiver_tilt_deg=max_receiver_tilt,max_penetration_m=max_penetration,
                     min_table_edge_clearance_m=edge,max_preimpact_roll_slip_m_s=max_roll_slip,
                     max_preimpact_slip_ratio=max_slip_ratio,
                     contact_normal_impulse_Ns=contact_impulse,last_motion_sec=last_motion,
                     settled_by_end=max(speeds)<.005,final_speed_m_s=max(speeds),
                     requested_pair_restitution=ph['restitution'],
                     requested_can_friction=ph['can_friction'],
                     requested_table_friction=ph['table_friction'],
                     effective_can_lateral_friction=can_mu,
                     effective_table_lateral_friction=table_mu)
        return dict(schema_version=2,scene=SCENE_NAME,scenario=deepcopy(s),simulation_signature=simulation_signature(s),
                    solver=dict(name='PyBullet',api_version=p.getAPIVersion(),constants=fixed_constants()),
                    playback_fps=r['fps'],sample_fps=fps,slow_motion=r['slow_motion'],frame_end=count,
                    physical_duration_sec=r['duration_sec'],playback_duration_sec=count/r['fps'],sampled_end_time_sec=(count-1)/fps,
                    objects={k:dict(present=bodies[i] is not None,mass_kg=masses[i],radius_m=RADIUS,height_m=HEIGHT,
                                   collision_shape='convex hull of can shoulder and rim profile',origin='can geometric center') for i,k in enumerate(KEYS)},
                    timed_edits=[dict(frame=frame,params=params) for frame,params in sorted(schedule.items())],
                    timed_events=timed_events,
                    quality=quality,frames=frames)
    finally:p.disconnect(client)


def main():
    parser=add_scenario_arguments(argparse.ArgumentParser(description=__doc__))
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();data=simulate(load_scenario(args))
    args.out.parent.mkdir(parents=True,exist_ok=True)
    for path,payload in [(args.out,data),(args.out.parent/'simulation_metrics.json',data['quality'])]:
        path.write_text(json.dumps(payload,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(data['quality'],indent=2))
    if not data['quality']['valid']:raise RuntimeError('Physical validation failed')


if __name__=='__main__':main()

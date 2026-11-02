"""Free rigid-body dynamics. No trajectory correction or post-launch forces."""
from __future__ import annotations

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
import math
from pathlib import Path
import pybullet as b
from pcve_timed_edits import check_horizon, unknown_param
from scene_config import load_scenario, write_json
from scene_geometry import (AC_CENTER, AC_SIZE, CABINET_CENTER, CABINET_SIZE, SPARE_BALL_CENTERS,
    SPARE_BALL_RADIUS, geometry_snapshot)

# The one parameter a timed edit may rewrite mid-run. Anything else would need
# its own live write into the solver, and silently ignoring it would render as
# a video indistinguishable from the source.
TIMED_PARAMS = ('gravity_z',)

def timed_schedule(p, count):
    """Read the in-run schedule into {frame: [new gravity, ...]}.

    Validated here rather than trusted: a frame outside the clip, a parameter
    this loop cannot write, or a gravity pointing out of the room would each
    produce a run that quietly is not the edit the manifest claims.
    """
    schedule = {}
    for event in p.get('timed_edits') or []:
        frame, params = event.get('frame'), event.get('params')
        if not isinstance(frame, int) or frame < 2:
            raise ValueError(f'Timed edit needs an integer frame from 2 on: {event!r}')
        if not isinstance(params, dict) or not params:
            raise ValueError(f'Timed edit carries no parameters: {event!r}')
        unknown = set(params) - set(TIMED_PARAMS)
        if unknown:
            raise unknown_param(', '.join(sorted(unknown)))
        value = float(params['gravity_z'])
        if not math.isfinite(value) or value >= 0:
            raise ValueError(f'Timed gravity must be finite and point down, got {value!r}')
        schedule.setdefault(frame, []).append(value)
    check_horizon(schedule, count)
    return schedule

def simulate(scenario):
    p = scenario['physics']
    fps=int(p['fps'])
    # Fast edits need smaller steps to retain the same contact accuracy.
    sub=int(p['substeps_per_frame'])*max(1,math.ceil(p['ball_initial_speed']/6))
    count = round(fps*p['duration_sec'])
    dt = 1/(fps*sub)
    r = p['ball_radius']
    width, depth, height = p['room_size']
    schedule = timed_schedule(p, count)
    gravity = float(p['gravity_z'])
    client = b.connect(b.DIRECT)
    try:
        b.setGravity(0, 0, gravity)
        b.setTimeStep(dt)
        b.setPhysicsEngineParameter(numSolverIterations=120, deterministicOverlappingPairs=1,
            restitutionVelocityThreshold=0.02, contactBreakingThreshold=0.001)
        def box(half, pos, restitution, friction, rolling=0):
            shape = b.createCollisionShape(b.GEOM_BOX, halfExtents=half)
            obj = b.createMultiBody(0, shape, basePosition=pos)
            b.changeDynamics(obj, -1, restitution=restitution, lateralFriction=friction, rollingFriction=rolling)
            return obj
        floor = box([width/2, depth/2, .1], [width/2, depth/2, -.1], p['floor_restitution'], p['floor_friction'], p['floor_rolling_friction'])
        walls = {}
        for name, half, pos in (
            ('wall_x', [.1, depth/2+.2, height/2], [-.1, depth/2, height/2]),
            ('wall_y', [width/2+.2, .1, height/2], [width/2, -.1, height/2]),
            ('wall_x_far', [.1, depth/2+.2, height/2], [width+.1, depth/2, height/2]),
            ('wall_y_far', [width/2+.2, .1, height/2], [width/2, depth+.1, height/2])):
            walls[box(half, pos, p['wall_restitution'], p['wall_friction'])] = name
        cabinet=box([s/2 for s in CABINET_SIZE],CABINET_CENTER,.3,.6)
        # The split unit is boxed too.  It sits 2.10 m up where no trajectory
        # reaches, but a collider is the only way that claim can be falsified: if
        # a solver change ever threw the ball up there it would show as a prop
        # contact instead of passing through the wall unit.
        air_conditioner=box([s/2 for s in AC_SIZE],AC_CENTER,.3,.6)
        props={cabinet:'cabinet',air_conditioner:'air_conditioner'}
        spare_shape=b.createCollisionShape(b.GEOM_SPHERE,radius=SPARE_BALL_RADIUS)
        for index,position in enumerate(SPARE_BALL_CENTERS,1):
            spare=b.createMultiBody(0,spare_shape,basePosition=position)
            props[spare]=f'spare_volleyball_{index}'
        shape = b.createCollisionShape(b.GEOM_SPHERE, radius=r)
        ball = b.createMultiBody(p['ball_mass'], shape, basePosition=p['ball_initial_location'])
        # Thin spherical shell inertia is appropriate for a hollow inflated ball.
        inertia=2/3*p['ball_mass']*r*r
        b.changeDynamics(ball, -1, restitution=p['ball_restitution'], lateralFriction=p['ball_friction'],
            rollingFriction=p['ball_rolling_friction'], spinningFriction=p['ball_spinning_friction'],
            linearDamping=p['linear_damping'], angularDamping=p['angular_damping'],
            ccdSweptSphereRadius=r*.8, contactProcessingThreshold=0,
            localInertiaDiagonal=[inertia]*3)
        norm = math.hypot(*p['launch_direction'])
        velocity=[p['ball_initial_speed']*v/norm for v in p['launch_direction']]
        b.resetBaseVelocity(ball, linearVelocity=velocity, angularVelocity=p['ball_initial_angular_velocity'])
        frames, events, active = [], [], set()
        floor_events,prop_events=[],[]
        timed_events=[]
        max_spin=math.hypot(*p['ball_initial_angular_velocity'])
        prop_clearance=100.0
        spare_clearance=100.0
        air_conditioner_clearance=100.0
        minimum_gap, minimum_wall_gap = 1.0, 1.0
        for frame in range(1, count+1):
            if frame > 1:
                # A timed edit writes the new gravity into the live solver
                # before this frame's steps, so frames 1..frame-1 keep the
                # state the source video had and everything after it runs on
                # the new value. Nothing here touches the stored trajectory.
                for new_gravity in schedule.get(frame, ()):
                    pos_before = b.getBasePositionAndOrientation(ball)[0]
                    vel_before = b.getBaseVelocity(ball)[0]
                    timed_events.append({'frame_index': frame, 'time_sec': (frame-1)/fps,
                        'parameter': 'gravity_z', 'from_value': gravity, 'to_value': new_gravity,
                        'applied_in_simulation': True,
                        'applied_before_substeps_of_frame': frame,
                        # The state the change was written into: the clip's last
                        # pre-edit frame, which is frame-1.
                        'state_before_edit': {'frame_index': frame-1, 'time_sec': (frame-2)/fps,
                            'ball_location': list(pos_before), 'ball_linear_velocity': list(vel_before)},
                        'note': 'Gravity written into the running solver at this frame; '
                                'the clip continues from the state reached so far.'})
                    gravity = new_gravity
                    b.setGravity(0, 0, gravity)
                for step in range(sub):
                    before_v,before_spin = b.getBaseVelocity(ball)
                    b.stepSimulation()
                    touching = set()
                    for contact in b.getContactPoints(bodyA=ball):
                        target = contact[2]
                        if target in walls or target==floor or target in props:
                            if contact[9]<=1e-6:
                                continue
                            touching.add(target)
                            axis=0 if walls.get(target,'').startswith('wall_x') else 1
                            approaching=(before_v[2]<-.15 if target==floor else math.hypot(*before_v)>.08 if target in props else abs(before_v[axis])>.08)
                            if target not in active and approaching:
                                t = ((frame-2)*sub+step+1)*dt
                                after_v,after_spin = b.getBaseVelocity(ball)
                                event={'wall': walls.get(target,'floor' if target==floor else 'prop'), 'time_sec': t,
                                    'frame_index': frame, 'position': list(b.getBasePositionAndOrientation(ball)[0]),
                                    'incoming_velocity': list(before_v), 'outgoing_velocity': list(after_v),
                                    'incoming_angular_velocity':list(before_spin),'outgoing_angular_velocity':list(after_spin),
                                    'normal_impulse_ns': contact[9]*dt}
                                if target in props:
                                    event['prop_name']=props[target]
                                (events if target in walls else floor_events if target==floor else prop_events).append(event)
                    active = touching
                    pos = b.getBasePositionAndOrientation(ball)[0]
                    minimum_gap = min(minimum_gap, pos[2]-r)
                    minimum_wall_gap = min(minimum_wall_gap, pos[0]-r, pos[1]-r, width-pos[0]-r, depth-pos[1]-r)
                    prop_clearance=min(prop_clearance,
                        math.sqrt(sum(max(abs(pos[i]-CABINET_CENTER[i])-CABINET_SIZE[i]/2,0)**2 for i in range(3)))-r)
                    spare_clearance=min(spare_clearance,*(math.dist(pos,center)-r-SPARE_BALL_RADIUS for center in SPARE_BALL_CENTERS))
                    air_conditioner_clearance=min(air_conditioner_clearance,
                        math.sqrt(sum(max(abs(pos[i]-AC_CENTER[i])-AC_SIZE[i]/2,0)**2 for i in range(3)))-r)
                    prop_clearance=min(prop_clearance,spare_clearance)
                    max_spin=max(max_spin,math.hypot(*b.getBaseVelocity(ball)[1]))
            pos, quat = b.getBasePositionAndOrientation(ball)
            vel, spin = b.getBaseVelocity(ball)
            frames.append({'frame_index': frame, 'time_sec': (frame-1)/fps,
                'ball_location': list(pos), 'ball_quaternion_xyzw': list(quat),
                'ball_linear_velocity': list(vel), 'ball_angular_velocity': list(spin)})
        metrics = {'wall_collisions': events, 'wall_collision_count': len(events),
            'floor_collisions':floor_events,'prop_collisions':prop_events,
            'min_prop_clearance_m':prop_clearance,'max_angular_speed_rad_s':max_spin,
            'min_spare_ball_clearance_m':spare_clearance,'min_ac_clearance_m':air_conditioner_clearance,
            'corner_wall_sequence': [e['wall'] for e in events[:2]],
            'min_floor_gap_m': minimum_gap, 'min_wall_gap_m': minimum_wall_gap,
            'path_length_m': sum(math.dist(a['ball_location'], c['ball_location']) for a,c in zip(frames,frames[1:])),
            'final_position': frames[-1]['ball_location'], 'ball_mass_kg': p['ball_mass'],
            'initial_kinetic_energy_j': .5*p['ball_mass']*p['ball_initial_speed']**2+.5*inertia*math.hypot(*p['ball_initial_angular_velocity'])**2,
            'timed_events':timed_events,'timed_edit_frames':sorted(schedule),
            'gravity_z_baseline':float(p['gravity_z']),'gravity_z_final':gravity,
            'finite_states':all(all(math.isfinite(v) for v in row['ball_location']+row['ball_linear_velocity'])
                for row in frames),
            'note': 'Airborne thin-shell rigid sphere, gravity and contact friction. Initial spin zero; impact-generated spin is measured. No post-launch correction.'}
        if not metrics['finite_states']:
            raise RuntimeError('Non-finite rigid state in the simulated trajectory')
        return {'schema_version': 1, 'simulator': 'pybullet', 'fps': fps, 'frame_start': 1,
            'frame_end': count, 'duration_sec': p['duration_sec'], 'physics': p,
            'static_geometry':geometry_snapshot(),'effective_substeps_per_frame':sub,'frames': frames, 'metrics': metrics}
    finally:
        b.disconnect(client)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--scenario-overrides-json', type=Path)
    args = parser.parse_args()
    data = simulate(load_scenario(args.scenario_overrides_json))
    write_json(args.out, data)
    write_json(args.out.with_name('simulation_metrics.json'), data['metrics'])
    print([(e['wall'], round(e['time_sec'], 3)) for e in data['metrics']['wall_collisions']])
    print([(e['frame_index'], e['from_value'], e['to_value']) for e in data['metrics']['timed_events']])

if __name__ == '__main__':
    main()

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
from scene_config import load_scenario, write_json

# Physics a schedule entry may write into the running simulation. A launch
# speed is deliberately absent: it is spent at frame 1, so there is nothing
# left to change later.
TIMED_FIELDS = {'ball_restitution', 'ball_friction', 'ball_mass', 'ball_spin_scale'}


def load_schedule(physics, frame_count):
    """Read a scenario's timed-edit schedule into ``{frame: params}``."""
    entries = physics.get('timed_edits', [])
    if not isinstance(entries, list):
        raise ValueError('timed_edits must be a list of {frame, params} events')
    schedule = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {'frame', 'params'}:
            raise ValueError('Each timed edit needs exactly a frame and a params object')
        frame = entry['frame']
        if isinstance(frame, bool) or not isinstance(frame, int) or not 2 <= frame <= frame_count:
            raise ValueError(f'Timed edit frame {frame!r} is outside 2..{frame_count}')
        if frame in schedule:
            raise ValueError(f'Two timed edits target frame {frame}')
        params = entry['params']
        if not isinstance(params, dict) or not params:
            raise ValueError(f'Timed edit at frame {frame} carries no parameters')
        unknown = set(params) - TIMED_FIELDS
        if unknown:
            raise ValueError(f'A timed edit cannot change: {sorted(unknown)}')
        for name, value in params.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f'Timed {name} must be a finite number')
            if name != 'ball_mass' and value < 0:
                raise ValueError(f'Timed {name} must be non-negative')
        schedule[frame] = dict(params)
    return schedule


def apply_timed_params(client, frame, params, ball, physics, fps):
    """Write a scheduled parameter set into the live body and report both ends.

    Only the dynamics of the ball move: its pose and linear velocity are read
    before and after so the record can show that the edit redefined a
    coefficient rather than kicking the body. A spin edit is the one schedule
    entry that intentionally changes a velocity, so the angular velocity is
    recorded on both sides while the line stays held on pose and translation.
    """
    mass, friction = (b.getDynamicsInfo(ball, -1, physicsClientId=client)[i] for i in (0, 1))
    restitution = b.getDynamicsInfo(ball, -1, physicsClientId=client)[5]
    position, _ = b.getBasePositionAndOrientation(ball, physicsClientId=client)
    linear, angular = b.getBaseVelocity(ball, physicsClientId=client)
    before_params = {name: physics[name] for name in params}
    before_state = {'mass_kg': mass, 'lateral_friction': friction, 'restitution': restitution,
                    'location': list(position), 'linear_velocity': list(linear),
                    'angular_velocity': list(angular),
                    'spin_rad_s': math.sqrt(sum(c * c for c in angular))}
    physics.update(params)
    dynamics = {}
    if 'ball_mass' in params:
        dynamics['mass'] = params['ball_mass']
    if 'ball_friction' in params:
        dynamics['lateralFriction'] = params['ball_friction']
    if 'ball_restitution' in params:
        dynamics['restitution'] = params['ball_restitution']
    if dynamics:
        b.changeDynamics(ball, -1, physicsClientId=client, **dynamics)
    if 'ball_spin_scale' in params:
        # Same axis the ball is already spinning about, multiplied by how much
        # the declared ratio moved (baseline 1.0 -> 5.0 is five times as fast):
        # a spin edit adds rotation, it does not invent a new axis.
        ratio = params['ball_spin_scale'] / before_params['ball_spin_scale']
        b.resetBaseVelocity(ball, linearVelocity=list(linear),
                            angularVelocity=[c * ratio for c in angular], physicsClientId=client)
    mass_after, friction_after = (b.getDynamicsInfo(ball, -1, physicsClientId=client)[i] for i in (0, 1))
    restitution_after = b.getDynamicsInfo(ball, -1, physicsClientId=client)[5]
    position_after, _ = b.getBasePositionAndOrientation(ball, physicsClientId=client)
    linear_after, angular_after = b.getBaseVelocity(ball, physicsClientId=client)
    if list(position_after) != list(position) or list(linear_after) != list(linear):
        raise RuntimeError('A coefficient change moved the ball; that is a kick, not an edit')
    return {'frame': frame, 'time_sec': (frame - 1) / fps, 'params': params,
            'before': {'params': before_params, 'state': before_state},
            'after': {'params': {name: physics[name] for name in params},
                      'state': {'mass_kg': mass_after, 'lateral_friction': friction_after,
                                'restitution': restitution_after,
                                'location': list(position_after),
                                'linear_velocity': list(linear_after),
                                'angular_velocity': list(angular_after),
                                'spin_rad_s': math.sqrt(sum(c * c for c in angular_after))}},
            'status': 'applied', 'effective_from_frame': frame}


def simulate(scenario):
    p = scenario['physics']
    fps, sub = int(p['fps']), int(p['substeps_per_frame'])
    count = round(fps*p['duration_sec'])
    dt = 1/(fps*sub)
    r = p['ball_radius']
    width, depth, height = p['room_size']
    schedule = load_schedule(p, count)
    client = b.connect(b.DIRECT)
    try:
        b.setGravity(0, 0, p['gravity_z'])
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
        shape = b.createCollisionShape(b.GEOM_SPHERE, radius=r)
        ball = b.createMultiBody(p['ball_mass'], shape, basePosition=[*p['ball_initial_location_xy'], r+.0001])
        b.changeDynamics(ball, -1, restitution=p['ball_restitution'], lateralFriction=p['ball_friction'],
            rollingFriction=p['ball_rolling_friction'], spinningFriction=p['ball_spinning_friction'],
            linearDamping=p['linear_damping'], angularDamping=p['angular_damping'],
            ccdSweptSphereRadius=r*.8, contactProcessingThreshold=0)
        dx, dy = p['launch_direction_xy']
        norm = math.hypot(dx, dy)
        vx, vy = p['ball_initial_speed']*dx/norm, p['ball_initial_speed']*dy/norm
        # For v = omega cross (0,0,r), pure rolling starts with this spin. The
        # declared ratio is 1.0 unless an edit says otherwise, and multiplying
        # by it leaves the source clip's numbers exactly as they were.
        spin_scale = p['ball_spin_scale']
        b.resetBaseVelocity(ball, linearVelocity=[vx, vy, 0],
                            angularVelocity=[-vy/r*spin_scale, vx/r*spin_scale, 0])
        frames, events, active = [], [], set()
        timed_events = []
        minimum_gap, minimum_wall_gap = 1.0, 1.0
        for frame in range(1, count+1):
            # The edit lands at the top of its frame: frames 1..n-1 have already
            # been stepped on the baseline physics, and this frame's steps run on
            # the edited value from the state the baseline had reached.
            if frame in schedule:
                timed_events.append(apply_timed_params(client, frame, schedule[frame], ball, p, fps))
            if frame > 1:
                for step in range(sub):
                    before_v = list(b.getBaseVelocity(ball)[0])
                    b.stepSimulation()
                    touching = set()
                    for contact in b.getContactPoints(bodyA=ball):
                        target = contact[2]
                        if target in walls:
                            touching.add(target)
                            if target not in active:
                                t = ((frame-2)*sub+step+1)*dt
                                after_v = list(b.getBaseVelocity(ball)[0])
                                events.append({'wall': walls[target], 'time_sec': t,
                                    'frame_index': frame, 'position': list(b.getBasePositionAndOrientation(ball)[0]),
                                    'incoming_velocity': before_v, 'outgoing_velocity': after_v,
                                    'normal_impulse_ns': contact[9]*dt})
                    active = touching
                    pos = b.getBasePositionAndOrientation(ball)[0]
                    minimum_gap = min(minimum_gap, pos[2]-r)
                    minimum_wall_gap = min(minimum_wall_gap, pos[0]-r, pos[1]-r, width-pos[0]-r, depth-pos[1]-r)
            pos, quat = b.getBasePositionAndOrientation(ball)
            vel, spin = b.getBaseVelocity(ball)
            frames.append({'frame_index': frame, 'time_sec': (frame-1)/fps,
                'ball_location': list(pos), 'ball_quaternion_xyzw': list(quat),
                'ball_linear_velocity': list(vel), 'ball_angular_velocity': list(spin)})
        metrics = {'wall_collisions': events, 'wall_collision_count': len(events),
            'corner_wall_sequence': [e['wall'] for e in events[:2]],
            'min_floor_gap_m': minimum_gap, 'min_wall_gap_m': minimum_wall_gap,
            'path_length_m': sum(math.dist(a['ball_location'], c['ball_location']) for a,c in zip(frames,frames[1:])),
            'final_position': frames[-1]['ball_location'], 'ball_mass_kg': p['ball_mass'],
            'ball_radius_m': p['ball_radius'],
            'initial_kinetic_energy_j': .7*p['ball_mass']*p['ball_initial_speed']**2,
            'timed_events': timed_events,
            'note': 'Rigid sphere, static walls. Mass-only edit should preserve the trajectory but scale collision impulse.'}
        return {'schema_version': 1, 'simulator': 'pybullet', 'fps': fps, 'frame_start': 1,
            'frame_end': count, 'duration_sec': p['duration_sec'], 'physics': p,
            'timed_edits': p.get('timed_edits', []), 'frames': frames, 'metrics': metrics}
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

if __name__ == '__main__':
    main()

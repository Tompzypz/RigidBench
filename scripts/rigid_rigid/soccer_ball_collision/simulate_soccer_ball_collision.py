"""Free 3D rolling spheres: initial velocities only, then PyBullet contacts."""
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
from scene_config import SCENE_NAME, add_scenario_arguments, load_scenario, validate
from scene_geometry import KEYS, RADIUS, START_X, START_Y, SIM_HZ, fixed_constants
from validate_soccer_ball_collision import simulation_signature

import pcve_timed_edits as timed

# Physics keys a timed edit may write, one per vocabulary binding plus the
# presence mask. Anything else is rejected outright: a schedule entry the
# simulator silently drops would render as the baseline video.
TIMED_KEYS = {f'{prefix}_{field}' for prefix in ('driver', 'receiver')
              for field in ('mass', 'friction', 'rolling_friction', 'restitution',
                            'angular_velocity')}
TIMED_KEYS.add('ball_active')

# Indices into pybullet's getDynamicsInfo tuple (measured against this
# build: 0 mass, 1 lateral friction, 2 inertia diagonal, 5 restitution,
# 6 rolling friction), one per writable field.
DYNAMICS_INDEX = {'mass': 0, 'friction': 1, 'rolling_friction': 6, 'restitution': 5}


def read_dynamics(p, client, body, field):
    return p.getDynamicsInfo(body, -1, physicsClientId=client)[DYNAMICS_INDEX[field]]


def apply_timed_params(p, client, bodies, params, timed_events, frame_number, step):
    """Write one frame's schedule into the live bodies, recording what changed.

    ``ball_active`` removes bodies through the shared helper -- a real
    ``removeBody``, so the ball stops colliding from that frame on. Dynamics
    values go through ``changeDynamics`` on the running state; a mass edit
    also rescales the thin-shell inertia the scene builds its bodies with.
    """
    flags = params.get('ball_active')
    if flags is not None:
        before = [1 if b is not None else 0 for b in bodies]
        timed.remove_bodies(p, client, bodies, flags)
        if before != [1 if b is not None else 0 for b in bodies]:
            timed_events.append(dict(frame=frame_number, time_sec=step / SIM_HZ,
                                     parameter='ball_active', from_value=before,
                                     to_value=list(flags), applied_in_simulation=True))
    for key, value in params.items():
        if key == 'ball_active':
            continue
        index = 0 if key.startswith('driver_') else 1
        body = bodies[index]
        if body is None:
            continue
        if key.endswith('_angular_velocity'):
            # Spin writes go through resetBaseVelocity, keeping the ball's
            # current linear velocity; the recorded "from" is the y-spin it
            # had the moment before the schedule took over.
            previous = p.getBaseVelocity(body, physicsClientId=client)[1][1]
            linear = p.getBaseVelocity(body, physicsClientId=client)[0]
            p.resetBaseVelocity(body, linearVelocity=list(linear),
                                angularVelocity=[0., float(value), 0.],
                                physicsClientId=client)
            timed_events.append(dict(frame=frame_number, time_sec=step / SIM_HZ,
                                     parameter=key, from_value=previous,
                                     to_value=float(value), applied_in_simulation=True))
            continue
        field = 'rolling_friction' if key.endswith('_rolling_friction') else key.rpartition('_')[2]
        previous = read_dynamics(p, client, body, field)
        if field == 'mass':
            mapped = float(value)
            p.changeDynamics(body, -1, mass=mapped,
                             localInertiaDiagonal=[2 / 3 * mapped * RADIUS ** 2] * 3,
                             physicsClientId=client)
        else:
            p.changeDynamics(
                body, -1, physicsClientId=client,
                **{{'friction': 'lateralFriction', 'rolling_friction': 'rollingFriction',
                    'restitution': 'restitution'}[field]: float(value)})
        timed_events.append(dict(frame=frame_number, time_sec=step / SIM_HZ,
                                 parameter=key, from_value=previous, to_value=float(value),
                                 applied_in_simulation=True))


def simulate(s):
    import pybullet as p
    validate(s)
    r, ph = s['render'], s['physics']
    sample_fps = r['fps'] * r['slow_motion']
    count = round(sample_fps * r['duration_sec'])
    stride = SIM_HZ // sample_fps
    client = p.connect(p.DIRECT)
    try:
        p.setGravity(0, 0, -9.81)
        p.setTimeStep(1 / SIM_HZ)
        p.setPhysicsEngineParameter(numSolverIterations=100, restitutionVelocityThreshold=.01,
                                    deterministicOverlappingPairs=1, contactBreakingThreshold=.0001)
        plane = p.createCollisionShape(p.GEOM_PLANE)
        ground = p.createMultiBody(0, plane)
        p.changeDynamics(ground, -1, lateralFriction=.8, restitution=0.)
        shape = p.createCollisionShape(p.GEOM_SPHERE, radius=RADIUS)
        masses = [ph['driver_mass'], ph['receiver_mass'], ph['ball_c_mass']]
        speeds = [ph['initial_velocity'], ph['receiver_initial_velocity'], 0.]
        restitutions = [ph['driver_restitution'], ph['receiver_restitution'],
                        ph['ball_c_restitution']]
        starts = [[START_X[i], START_Y[i], RADIUS] for i in range(2)]
        starts.append(list(ph['ball_c_start_position']))
        prefixes = ('driver', 'receiver', 'ball_c')
        bodies = []
        for i, (mass, speed) in enumerate(zip(masses, speeds)):
            if not ph['ball_active'][i]:
                bodies.append(None)
                continue
            prefix = prefixes[i]
            body = p.createMultiBody(mass, shape, basePosition=starts[i])
            inertia = 2 / 3 * mass * RADIUS ** 2  # thin inflated shell, not a solid ball
            p.changeDynamics(body, -1, lateralFriction=ph[f'{prefix}_friction'],
                             rollingFriction=ph[f'{prefix}_rolling_friction'],
                             spinningFriction=.0002, restitution=restitutions[i],
                             linearDamping=0., angularDamping=0., localInertiaDiagonal=[inertia] * 3)
            p.resetBaseVelocity(body, [speed, 0, 0], [0, speed / RADIUS, 0])
            bodies.append(body)
        # Edits that land partway through the clip arrive in the scenario's
        # physics block as [{"frame": n, "params": {...}}]. Frames before n
        # are the baseline clip bit for bit; at the top of frame n the params
        # are written into the live bodies and the run carries on from there.
        timed_by_frame = {}
        for entry in ph.get('timed_edits') or []:
            frame = entry.get('frame') if isinstance(entry, dict) else None
            params = entry.get('params') if isinstance(entry, dict) else None
            if (not isinstance(frame, int) or not 2 <= frame <= count
                    or not isinstance(params, dict) or not params
                    or set(params) - TIMED_KEYS):
                raise ValueError(f'Unsupported or invalid timed edit: {entry!r}')
            timed_by_frame.setdefault(frame, {}).update(dict(params))
        timed_events = []
        frames, events = [], []
        previous_contact = False
        def velocities():
            return [list(p.getBaseVelocity(b)[0]) if b is not None else None for b in bodies]
        pre_v = velocities()
        max_penetration = 0.
        max_ground_error = 0.
        contact_start = None
        impact_pre = None
        for step in range((count - 1) * stride + 1):
            t = step / SIM_HZ
            if step % stride == 0 and (step // stride + 1) in timed_by_frame:
                frame_number = step // stride + 1
                apply_timed_params(p, client, bodies, timed_by_frame.pop(frame_number),
                                   timed_events, frame_number, step)
            v = velocities()
            present = [b for b in bodies if b is not None]
            contacts = []
            for i in range(len(present)):
                for j in range(i + 1, len(present)):
                    contacts.extend(p.getContactPoints(present[i], present[j]))
            contact = bool(contacts)
            if contact and not previous_contact:
                contact_start, impact_pre = t, pre_v
            if previous_contact and not contact:
                events.append(dict(time_sec=contact_start, contact_end_sec=t,
                                   pre_velocity=impact_pre, post_velocity=v,
                                   momentum_change_x_kg_m_s=sum(m * (b[0] - a[0]) for m, a, b in zip(masses, impact_pre, v) if a is not None and b is not None)))
            previous_contact = contact
            for b in bodies:
                if b is None:
                    continue
                pos, _ = p.getBasePositionAndOrientation(b)
                max_ground_error = max(max_ground_error, abs(pos[2] - RADIUS))
                for c in p.getContactPoints(bodyA=b):
                    max_penetration = max(max_penetration, -c[8])
            if step % stride == 0:
                f = dict(frame_index=len(frames) + 1, time_sec=t)
                for key, b in zip(KEYS, bodies):
                    if b is None:
                        f[key] = dict(present=False, location=None, quaternion_xyzw=None,
                                      linear_velocity=None, angular_velocity=None, matrix_world=None)
                        continue
                    pos, q = p.getBasePositionAndOrientation(b)
                    linear, angular = p.getBaseVelocity(b)
                    mat = p.getMatrixFromQuaternion(q)
                    matrix = [list(mat[j*3:j*3+3]) + [pos[j]] for j in range(3)] + [[0, 0, 0, 1]]
                    f[key] = dict(present=True, location=list(pos), quaternion_xyzw=list(q),
                                  linear_velocity=list(linear), angular_velocity=list(angular), matrix_world=matrix)
                frames.append(f)
            pre_v = v
            if step < (count-1) * stride:
                p.stepSimulation()
        impact = events[0] if events else None
        reversal = bool(impact and impact['post_velocity'][0][0] < 0 < impact['post_velocity'][1][0])
        quality = dict(valid=max_penetration < .002 and max_ground_error < .004,
                       transmission_observed=bool(events), rebound_observed=reversal, events=events,
                       first_impact_sec=impact['time_sec'] if impact else contact_start,
                       max_penetration_m=max_penetration, max_ground_height_error_m=max_ground_error,
                       final_center_distance_m=math.dist(frames[-1]['ball_a']['location'], frames[-1]['ball_b']['location']) if all(b is not None for b in bodies) else None,
                       requested_pair_restitution=math.prod(restitutions),
                       active_object_count=sum(ph['ball_active']), rigid_body_count=p.getNumBodies(),
                       timed_events=timed_events)
        return dict(schema_version=2, scene=SCENE_NAME, scenario=deepcopy(s),
                    simulation_signature=simulation_signature(s),
                    solver=dict(name='PyBullet', api_version=p.getAPIVersion(), constants=fixed_constants()),
                    playback_fps=r['fps'], sample_fps=sample_fps, slow_motion=r['slow_motion'], frame_end=count,
                    physical_duration_sec=r['duration_sec'], playback_duration_sec=r['duration_sec']*r['slow_motion'],
                    sampled_end_time_sec=(count-1)/sample_fps, timed_events=timed_events,
                    objects={k: dict(present=bool(ph['ball_active'][i]),
                                     mass_kg=masses[i], radius_m=RADIUS,
                                     restitution=restitutions[i],
                                     friction=ph[f'{prefixes[i]}_friction'],
                                     rolling_friction=ph[f'{prefixes[i]}_rolling_friction'],
                                     collision_shape='sphere', origin='sphere center')
                             for i, k in enumerate(KEYS)},
                    quality=quality, frames=frames)
    finally:
        p.disconnect(client)


def main():
    parser = add_scenario_arguments(argparse.ArgumentParser(description=__doc__))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    data = simulate(load_scenario(args))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, indent=2, allow_nan=False), encoding='utf-8')
    (args.out.parent/'simulation_metrics.json').write_text(json.dumps(data['quality'], indent=2), encoding='utf-8')
    print(json.dumps(data['quality'], indent=2))
    if not data['quality']['valid']:
        raise RuntimeError('Invalid physical trace')


if __name__ == '__main__':
    main()

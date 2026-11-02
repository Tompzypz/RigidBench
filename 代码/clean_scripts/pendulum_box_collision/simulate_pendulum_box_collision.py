"""A sliding pine block meets a swinging steel bob; SI units, no scripted motion.

Both bodies are given their initial state on frame 1 and then left alone: the
block starts off-screen at the far end of the bench and slides towards +X at
``box_speed``, the bob starts at the bottom of its arc with a tangential speed
``bob_speed`` towards +X, and the only things that change either of them
afterwards are Bullet's contact solver and the gravity torque on the pendulum.

The phase is the reason the bob starts moving *away* from the block
--------------------------------------------------------------------
A 0.36 m pendulum has a 1.21 s period, so half a period is 0.60 s, and the
block is placed to arrive exactly then: ``APPROACH_DISTANCE`` in
``scene_geometry`` is the 0.64 m that 1.2 m/s covers in 0.605 s against bench
friction. The clip therefore opens with a metre of empty bench and a pendulum
in free swing, and the block slides in from the left edge roughly a tenth of a
second later.

Which way the bob leaves the bottom decides what the collision *is*. Started
towards -X it would be heading for the block already and would meet it at the
half-period mark while moving +X, i.e. being hit from behind. Started towards
+X it swings out to the right, comes back down through the bottom at the half
period moving -X, and is met head-on by the incoming block -- a face impact at
the bottom of the arc, which is also the pose a viewer expects from "a block
hits a pendulum".

The phase is not held fixed across edits, and it should not be: the block's
arrival time is ``distance / speed``, so ``box_speed`` decides where on its arc
the bob is when it is hit, and ``bob_speed`` decides how high that arc goes.
What *is* guaranteed is that the two always meet: the slider sweeps through
``x = 0`` once every run, the bob never leaves the 12 cm either side of it that
the block covers, and the block is tall enough (85 mm) that the bob's centre
stays below its top edge for the whole swing -- so every case gets a face
impact, never a corner clip or a miss.

Why the bob is a free sphere on a point-to-point constraint
-----------------------------------------------------------
The obvious model is a fixed-based multibody with one revolute link, which is
what ``newtons_cradle`` uses. Measured here, that link's ``restitution`` is
never applied: a box hitting it at 2.5 m/s separates at 0.05 m/s even with both
bodies set to sqrt(0.9), i.e. the pair behaves as perfectly inelastic no matter
what the coefficient says. A free rigid sphere held by a ``JOINT_POINT2POINT``
constraint to a massless anchor at the pivot keeps the rod rigid -- the measured
length error over the whole clip is 0.2 mm -- and *does* honour restitution, so
the collision is the one the coefficient describes. The constraint force acts
along the rod, through the sphere's centre, so it adds no torque about the
centre; the ball is free to spin, which is what a hung ball does.

Why the bob starts at the bottom
--------------------------------
The alternative -- hold the bob at an angle and let it fall -- puts a second,
unstated parameter in the scene (the release angle) and ties the bob's speed to
it, so ``bob_speed`` would no longer be independently editable. Starting at the
bottom with a tangential speed makes ``bob_speed`` mean exactly what a reader of
the clip sees, and the bob is still visibly swinging before the block arrives.

The hinge reaction is an external impulse, so the *bob's* momentum is not
conserved and the pair's only approximately. The metrics therefore lead with
measured speeds, the bob's swing height and the pair's mechanical energy, and
never claim a momentum balance that the pivot quietly breaks.
"""
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




import argparse, json, math, sys
from pathlib import Path

from scene_support.pendulum_box_collision import runtime_support  # noqa: E402
from scene_support.pendulum_box_collision.cache_contract import CACHE_SCHEMA_VERSION, simulation_signature  # noqa: E402
from scene_support.pendulum_box_collision.scene_config import BASELINE_PHYSICS, PHYSICS_LIMITS, load_scenario, validate  # noqa: E402
from scene_support.pendulum_box_collision.scene_geometry import (  # noqa: E402
    BENCH_SIZE, BOB_CENTER_Z, BOB_RADIUS, BOX_SIZE, BOX_START_X, PENDULUM_LENGTH,
    PIVOT, TABLE_Z, box_center, moving_objects)
import pybullet as p  # noqa: E402

# Fixed dynamics. None of these is an editable parameter, so they live here next
# to the implementation rather than in the scenario.
PHYSICS_DT = 1 / 4800
BENCH_RESTITUTION = .02    # box/bench product, so the block does not bounce
BOX_FRICTION = .30         # varnished bench: 0.30 * 0.16 = 0.048 effective, 0.47 m/s^2
BENCH_FRICTION = .16
BOB_FRICTION = .25         # steel on pine, 0.42 * 0.25 = 0.105 at the contact
SOLVER_ITERATIONS = 100
# How long after the first contact the recoil peaks are read. A quarter second
# is long enough for the bob to fall back to the bottom of its arc and show the
# speed it carries away, and short enough that a second touch -- the pendulum
# coming back half a period later -- cannot be mistaken for the first one.
REBOUND_WINDOW = .25
MAX_PENETRATION = .001     # 1 mm: above this the contact is visibly wrong
MAX_ROD_ERROR = .001       # 1 mm of constraint stretch
# The pair restitution coefficient is an editable physics key
# (``restitution``, baseline 0.55 -- a pine/steel pair). The value the solver
# actually delivers is reported per case as ``restitution_measured`` (a little
# under what it is asked for at this step size), and a timed edit can lower it
# partway through the clip; the applier below then writes the new value into
# both live bodies and the run continues.


def _box_inertia(mass):
    w, d, h = BOX_SIZE
    return (mass / 12 * (d * d + h * h), mass / 12 * (w * w + h * h), mass / 12 * (w * w + d * d))


def _angle_deg(position):
    """Signed swing angle: negative on the box's side of the vertical."""
    return math.degrees(math.atan2(position[0] - PIVOT[0], PIVOT[2] - position[2]))


def simulate(s):
    validate(s)
    physics = s['physics']
    r = s['render']
    sample_fps = r['fps'] * r['slow_motion']
    duration_sec = r['duration_sec']
    for key, value in physics.items():
        if key == 'timed_edits':
            continue  # schedule, not a scalar; validated below
        if not math.isfinite(value) or value < 0 or (value == 0 and key != 'bob_speed'):
            # bob_speed may legitimately be 0 (bob released at rest); every
            # other parameter must stay strictly positive.
            raise ValueError(f'{key} must be finite and positive')
        low, high = PHYSICS_LIMITS[key]
        if not low <= value <= high:
            raise ValueError(f'{key} must be between {low} and {high}')
    restitution = physics['restitution']

    client = p.connect(p.DIRECT)
    try:
        p.setTimeStep(PHYSICS_DT, physicsClientId=client)
        p.setGravity(0, 0, -9.81, physicsClientId=client)
        p.setPhysicsEngineParameter(numSolverIterations=SOLVER_ITERATIONS,
                                    contactBreakingThreshold=.001, contactSlop=0.,
                                    contactERP=0., restitutionVelocityThreshold=0.,
                                    deterministicOverlappingPairs=1, physicsClientId=client)

        def static_block(size, location, friction, restitution=BENCH_RESTITUTION):
            shape = p.createCollisionShape(p.GEOM_BOX, halfExtents=[v / 2 for v in size],
                                           physicsClientId=client)
            uid = p.createMultiBody(0, shape, basePosition=location, physicsClientId=client)
            p.changeDynamics(uid, -1, lateralFriction=friction, restitution=restitution,
                             linearDamping=0, angularDamping=0, collisionMargin=.0002,
                             physicsClientId=client)
            return uid

        # Floor, then the bench slab whose top face is the sliding surface.
        static_block((8., 5., .1), (0., 0., -.05), .8)
        static_block(BENCH_SIZE, (0., 0., TABLE_Z - BENCH_SIZE[2] / 2), BENCH_FRICTION)

        box_shape = p.createCollisionShape(p.GEOM_BOX, halfExtents=[v / 2 for v in BOX_SIZE],
                                           physicsClientId=client)
        box = p.createMultiBody(physics['box_mass'], box_shape, basePosition=box_center(),
                                baseOrientation=p.getQuaternionFromEuler([0, 0, 0]),
                                physicsClientId=client)
        # Bullet multiplies the two bodies' restitution, so sqrt(e) on both sides
        # of the pair gives the requested pair coefficient.
        p.changeDynamics(box, -1, lateralFriction=BOX_FRICTION, restitution=math.sqrt(restitution),
                         linearDamping=0, angularDamping=.02, collisionMargin=.0002,
                         physicsClientId=client)

        bob_shape = p.createCollisionShape(p.GEOM_SPHERE, radius=BOB_RADIUS, physicsClientId=client)
        bob = p.createMultiBody(physics['bob_mass'], bob_shape,
                                basePosition=[0., 0., BOB_CENTER_Z], physicsClientId=client)
        p.changeDynamics(bob, -1, lateralFriction=BOB_FRICTION, restitution=math.sqrt(restitution),
                         linearDamping=0, angularDamping=0, collisionMargin=.0002,
                         physicsClientId=client)
        anchor = p.createMultiBody(0, -1, basePosition=list(PIVOT), physicsClientId=client)
        p.createConstraint(anchor, -1, bob, -1, p.JOINT_POINT2POINT, [0, 0, 0], [0, 0, 0],
                           [0, 0, PENDULUM_LENGTH], physicsClientId=client)

        # Frame 1: block sliding in from off-screen, bob at the bottom of its
        # arc heading away from it -- see the module docstring on phase.
        p.resetBaseVelocity(box, (physics['box_speed'], 0, 0), physicsClientId=client)
        p.resetBaseVelocity(bob, (physics['bob_speed'], 0, 0), physicsClientId=client)

        def box_state():
            position, quaternion = p.getBasePositionAndOrientation(box, physicsClientId=client)
            linear, angular = p.getBaseVelocity(box, physicsClientId=client)
            return dict(position=list(position), quaternion=list(quaternion),
                        linear_velocity=list(linear), angular_velocity=list(angular))

        def bob_state():
            position, quaternion = p.getBasePositionAndOrientation(bob, physicsClientId=client)
            linear, angular = p.getBaseVelocity(bob, physicsClientId=client)
            return dict(position=list(position), quaternion=list(quaternion),
                        linear_velocity=list(linear), angular_velocity=list(angular),
                        angle=math.atan2(position[0] - PIVOT[0], PIVOT[2] - position[2]),
                        rod_error=abs(math.dist(position, list(PIVOT)) - PENDULUM_LENGTH))

        def energies(state):
            box_energy = .5 * physics['box_mass'] * sum(v * v for v in state['box']['linear_velocity'])
            w = state['box']['angular_velocity']; inertia = _box_inertia(physics['box_mass'])
            box_energy += .5 * sum(inertia[i] * w[i] * w[i] for i in range(3))
            box_energy += physics['box_mass'] * 9.81 * (state['box']['position'][2] - (TABLE_Z + BOX_SIZE[2] / 2))
            bob_energy = .5 * physics['bob_mass'] * sum(v * v for v in state['bob']['linear_velocity'])
            bob_energy += .5 * (.4 * physics['bob_mass'] * BOB_RADIUS ** 2) * sum(
                v * v for v in state['bob']['angular_velocity'])
            bob_energy += physics['bob_mass'] * 9.81 * (state['bob']['position'][2] - BOB_CENTER_Z)
            return box_energy, bob_energy

        initial = dict(box=box_state(), bob=bob_state())
        initial_box_energy, initial_bob_energy = energies(initial)
        initial_total = initial_box_energy + initial_bob_energy

        # Mid-run schedule: the clip runs on baseline physics up to each edit
        # frame, the new restitution is written into both live bodies there,
        # and the run carries on from the state it had reached. Only the pair
        # coefficient can be timed in this scene.
        total_frames = round(sample_fps * duration_sec)
        timed_by_frame = {}
        for entry in physics.get('timed_edits') or []:
            frame, params = entry.get('frame'), entry.get('params')
            if (not isinstance(frame, int) or not 2 <= frame <= total_frames
                    or not isinstance(params, dict) or set(params) != {'restitution'}):
                raise ValueError(f'Unsupported or invalid timed event: {entry!r}')
            value = float(params['restitution'])
            if not math.isfinite(value) or not .05 <= value <= .92:
                raise ValueError('Timed restitution must be finite and within PHYSICS_LIMITS')
            timed_by_frame.setdefault(frame, []).append(value)
        timed_events = []
        applied_frames = set()

        frames = []
        next_frame = 0
        total_steps = round(duration_sec / PHYSICS_DT)
        first_contact = None
        contact_episodes = 0
        was_touching = False
        last_touch = -1.
        max_penetration = 0.
        max_rod_error = initial['bob']['rod_error']
        max_energy = initial_total
        pre = dict(box=initial['box'], bob=initial['bob'])
        impact = None
        separation = None
        rebound = dict(bob=0., box=0.)
        peak_angle = 0.
        peak_bob_energy = initial_bob_energy

        for step in range(total_steps + 1):
            t = step * PHYSICS_DT
            # A timed edit fires when the clock reaches its frame boundary,
            # before that frame is sampled: the change never rewrites history,
            # only the motion from this instant on.
            for frame, values in timed_by_frame.items():
                if frame in applied_frames or t + PHYSICS_DT / 2 < (frame - 1) / sample_fps:
                    continue
                applied_frames.add(frame)
                for value in values:
                    previous = restitution
                    restitution = value
                    for body in (box, bob):
                        p.changeDynamics(body, -1, restitution=math.sqrt(value),
                                         physicsClientId=client)
                    timed_events.append(dict(
                        frame=frame, time_sec=(frame - 1) / sample_fps,
                        parameter='restitution', from_value=previous, to_value=value,
                        applied_in_simulation=True))
            if t + PHYSICS_DT / 2 >= next_frame / sample_fps:
                state = dict(box=box_state(), bob=bob_state())
                box_energy, bob_energy = energies(state)
                max_energy = max(max_energy, box_energy + bob_energy)
                max_rod_error = max(max_rod_error, state['bob']['rod_error'])
                peak_angle = max(peak_angle, abs(state['bob']['angle']))
                if first_contact is not None:
                    peak_bob_energy = max(peak_bob_energy, bob_energy)
                frames.append(dict(time=next_frame / sample_fps, box=state['box'], bob=state['bob']))
                next_frame += 1
            if step == total_steps:
                break
            pre = dict(box=box_state(), bob=bob_state())
            p.stepSimulation(physicsClientId=client)
            now = (step + 1) * PHYSICS_DT

            touching = False
            for contact in p.getContactPoints(physicsClientId=client):
                max_penetration = max(max_penetration, -contact[8])
                if {contact[1], contact[2]} == {box, bob}:
                    touching = True
            if touching:
                if first_contact is None:
                    first_contact = now
                    impact = dict(
                        bob_angle_deg=math.degrees(pre['bob']['angle']),
                        bob_speed=math.hypot(pre['bob']['linear_velocity'][0], pre['bob']['linear_velocity'][2]),
                        box_speed=abs(pre['box']['linear_velocity'][0]),
                        box_vx=pre['box']['linear_velocity'][0],
                        bob_vx=pre['bob']['linear_velocity'][0],
                        approach=abs(pre['box']['linear_velocity'][0] - pre['bob']['linear_velocity'][0]))
                if not was_touching and now - last_touch > .02:
                    contact_episodes += 1
                last_touch = now
                was_touching = True
            elif was_touching:
                # The step the two bodies part company is the only clean place
                # to read the separation speed: afterwards the bench friction is
                # already eating it and the rod has started curving the bob.
                was_touching = False
                if separation is None:
                    separation = dict(
                        box=p.getBaseVelocity(box, physicsClientId=client)[0][0],
                        bob=p.getBaseVelocity(bob, physicsClientId=client)[0][0])

            if first_contact is not None and now - first_contact <= REBOUND_WINDOW:
                # Peak recoil of each body away from the other, within a fixed
                # window after the hit -- not "over the rest of the clip".
                #
                # The window exists because the pendulum comes back. Half a
                # period after the impact the bob swings down again, and in a
                # 1.2 s clip it can reach the block a second time (a slower
                # slider is still nearby, a faster one has already left). That
                # second touch is real physics and is reported separately as
                # ``contact_episodes``, but it must not be folded into "how hard
                # did the block get knocked back", so the recoil is read only
                # in the first quarter second, which is also where both peaks
                # physically live.
                #
                # The two peaks still happen at different times, and that is
                # physics too: the block is on a level bench and reaches its
                # peak the instant the impulse lands, while the bob is a few
                # degrees up the arc when it is struck, so it first descends to
                # the bottom and only then carries its largest speed away. Both
                # bodies are compared against their own baseline, and the
                # coefficient itself is read at the separation step, never from
                # these peaks.
                bx = p.getBaseVelocity(box, physicsClientId=client)[0][0]
                bvx = p.getBaseVelocity(bob, physicsClientId=client)[0][0]
                rebound['box'] = max(rebound['box'], -bx)
                rebound['bob'] = max(rebound['bob'], bvx)

        final = dict(box=box_state(), bob=bob_state())
        max_rod_error = max(max_rod_error, final['bob']['rod_error'])
        final_box_energy, final_bob_energy = energies(final)
        finite = all(math.isfinite(v) for frame in frames for body in ('box', 'bob')
                     for key in ('position', 'quaternion', 'linear_velocity', 'angular_velocity')
                     for v in frame[body][key])
        restitution = None
        if impact and separation:
            restitution = -(separation['box'] - separation['bob']) / (impact['box_vx'] - impact['bob_vx'])
        quality = dict(
            valid=(finite and max_penetration < MAX_PENETRATION and max_rod_error < MAX_ROD_ERROR
                   and max_energy <= initial_total * 1.03),
            hit_box=first_contact is not None,
            first_contact_sec=first_contact,
            contact_episodes=contact_episodes,
            bob_angle_at_contact_deg=impact['bob_angle_deg'] if impact else None,
            bob_speed_at_contact_mps=impact['bob_speed'] if impact else 0.,
            box_speed_at_contact_mps=impact['box_speed'] if impact else 0.,
            approach_speed_mps=impact['approach'] if impact else 0.,
            restitution_measured=restitution,
            bob_rebound_speed_mps=rebound['bob'],
            box_rebound_speed_mps=rebound['box'],
            box_final_speed_mps=abs(final['box']['linear_velocity'][0]),
            bob_final_speed_mps=abs(final['bob']['linear_velocity'][0]),
            bob_peak_swing_deg=max(math.degrees(peak_angle), abs(_angle_deg(final['bob']['position']))),
            bob_peak_height_m=PENDULUM_LENGTH * (1 - math.cos(max(peak_angle, abs(final['bob']['angle'])))),
            bob_stopped=rebound['bob'] < .10,
            max_penetration_m=max_penetration,
            max_rod_error_m=max_rod_error,
            initial_energy_j=initial_total,
            max_energy_ratio=max_energy / initial_total,
            final_energy_ratio=(final_box_energy + final_bob_energy) / initial_total,
            # A bob released at rest has no initial energy to gain against;
            # report the absolute peak instead of a meaningless ratio.
            bob_energy_gain=(peak_bob_energy / initial_bob_energy
                             if initial_bob_energy > 0 else None),
            requested_pair_restitution=physics['restitution'],
            timed_events=timed_events,
        )
        if not quality['valid']:
            raise RuntimeError(f'Invalid collision simulation: {quality}')
    finally:
        p.disconnect(client)

    out_frames = []
    for index, old in enumerate(frames[:round(sample_fps * duration_sec)], 1):
        frame = dict(frame_index=index, time_sec=old['time'], playback_time_sec=(index - 1) / r['fps'])
        for key, pose in (('box', old['box']), ('bob', old['bob'])):
            position = pose['position']; quaternion = pose['quaternion']
            rotation = p.getMatrixFromQuaternion(quaternion)
            frame[key] = dict(
                present=True, location=position, quaternion_xyzw=quaternion,
                matrix_world=[[rotation[3 * i + j] for j in range(3)] + [position[i]]
                              for i in range(3)] + [[0, 0, 0, 1]],
                linear_velocity=pose['linear_velocity'], angular_velocity=pose['angular_velocity'],
                speed=math.sqrt(sum(v * v for v in pose['linear_velocity'])))
            if key == 'bob':
                frame[key].update(pendulum_angle_rad=pose['angle'],
                                  height_m=PENDULUM_LENGTH * (1 - math.cos(pose['angle'])))
        out_frames.append(frame)

    return dict(schema_version=CACHE_SCHEMA_VERSION, simulation_signature=simulation_signature(s),
                scene='pendulum_box_collision', simulator='pybullet',
                constraint_model='Free sphere on a JOINT_POINT2POINT rod; box on a bench',
                scenario=s, physics=physics,
                geometry=dict(box_size=list(BOX_SIZE), box_start_x=BOX_START_X, table_z=TABLE_Z,
                              bob_radius=BOB_RADIUS, pendulum_length=PENDULUM_LENGTH,
                              pivot=list(PIVOT), bob_center_z=BOB_CENTER_Z),
                objects=moving_objects(physics), frames=out_frames, quality=quality,
                timed_events=timed_events,
                fps=sample_fps, sample_fps=sample_fps, playback_fps=r['fps'],
                slow_motion=r['slow_motion'], frame_start=1, frame_end=len(out_frames),
                duration_sec=duration_sec, physical_duration_sec=duration_sec,
                playback_duration_sec=duration_sec * r['slow_motion'], physics_dt=PHYSICS_DT)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--scenario-json', type=Path)
    parser.add_argument('--scenario-overrides-json', type=Path)
    for key in BASELINE_PHYSICS:
        parser.add_argument('--' + key.replace('_', '-'), type=float)
    parser.add_argument('--fps', type=int); parser.add_argument('--duration-sec', type=float)
    parser.add_argument('--slow-motion', type=int, choices=(1, 2, 4, 8))
    args = parser.parse_args()
    data = simulate(load_scenario(args))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    args.out.with_name('simulation_metrics.json').write_text(
        json.dumps(data['quality'], indent=2), encoding='utf-8')
    print(json.dumps(data['quality']))


if __name__ == '__main__':
    main()

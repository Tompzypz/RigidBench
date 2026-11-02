"""PyBullet trajectory for a pot lid dropped from the kitchen counter to the floor.

One rigid lid, one static floor, no scripted motion after the drop: the lid is
given an initial pose, a small nudge and a tipping angular velocity, and everything the video shows
is the solver's answer. Metres, kilograms, seconds, +Z up.

Simulation coordinates put ``(0, 0, 0)`` on the floor directly under the drop,
so ``layout.action_origin`` is the only place the kitchen model's own
coordinates enter: the renderer adds it back when it writes keyframes.

The collision shape is the lid mesh's convex hull, exported by the renderer
(``lid_hull.json``) so the body that tumbles on screen is the body that was
solved. Without that file the scene falls back to a plain disc and says so.

Run standalone:
    .runtime/sim/python.exe scripts/pot_lid_drop/simulate_pot_lid_drop.py \
        --out renders/pot_lid_drop/physics_transforms.json
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





import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import pybullet as p

HERE = Path(__file__).resolve().parent
from scene_support.pot_lid_drop import scenario_io  # noqa: E402

FLOOR_HALF_EXTENT = 6.0
FLOOR_THICKNESS = 0.1

# Physics keys whose values PyBullet's changeDynamics takes verbatim. A timed
# edit may only touch these; anything else would be a silently dropped edit
# that renders as the baseline video.
LIVE_FIELDS = {
    'lid_mass': ('mass', 'mass'),
    'lid_friction': ('lateralFriction', 'lateral friction'),
    'lid_rolling_friction': ('rollingFriction', 'rolling friction'),
    'lid_spinning_friction': ('spinningFriction', 'spinning friction'),
    'lid_restitution': ('restitution', 'restitution'),
}

# World-level keys a timed edit may write; these go through setGravity
# rather than the lid's changeDynamics.
WORLD_TIMED_FIELDS = {'gravity_z'}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--scenario', type=Path, default=None)
    parser.add_argument('--scenario-overrides-json', type=Path, default=None)
    parser.add_argument('--lid-hull-json', type=Path, default=None)
    parser.add_argument('--fps', type=int, default=None)
    parser.add_argument('--duration-sec', type=float, default=None)
    parser.add_argument('--substeps', type=int, default=None)
    return parser.parse_args()


# ------------------------------------------------------------------- geometry


def load_hull(path: Path | None, physics: dict[str, Any]) -> tuple[list[list[float]], dict[str, Any]]:
    """Lid collision vertices, centred on the volume centroid, in metres.

    The exporter writes them in the lid's own frame with +Z through the dome,
    which is the frame the renderer also animates, so a solved pose drops
    straight onto the Blender object with no extra rotation.
    """
    if path is not None and Path(path).is_file():
        payload = scenario_io.read_json(Path(path))
        vertices = [[float(c) for c in v] for v in payload['vertices']]
        meta = {k: v for k, v in payload.items() if k != 'vertices'}
        meta['hull_source'] = str(Path(path).resolve())
        return vertices, meta

    radius = float(physics['lid_radius_m'])
    thickness = float(physics['lid_rim_thickness_m'])
    segments = 48
    vertices = []
    for z in (-thickness / 2, thickness / 2):
        ring = [
            [radius * math.cos(i * math.tau / segments), radius * math.sin(i * math.tau / segments), z]
            for i in range(segments)
        ]
        vertices.extend(ring)
    meta = {
        'hull_source': 'analytic disc fallback (no lid_hull.json)',
        'circumscribed_diameter_m': 2.0 * radius,
        'height_m': thickness,
        'vertex_count': len(vertices),
    }
    return vertices, meta


def extent(vertices: list[list[float]]) -> tuple[list[float], list[float]]:
    lo = [min(v[i] for v in vertices) for i in range(3)]
    hi = [max(v[i] for v in vertices) for i in range(3)]
    return lo, hi


def lowest_point_gap(position, quaternion, vertices: list[list[float]]) -> float:
    """Height of the lid's lowest vertex above the floor plane (z = 0)."""
    rotation = p.getMatrixFromQuaternion(quaternion)
    lowest = min(
        rotation[6] * v[0] + rotation[7] * v[1] + rotation[8] * v[2] for v in vertices
    )
    return position[2] + lowest


def start_spin_world(physics: dict[str, Any], orientation) -> list[float]:
    """Resolve release angular velocity from lid-local or world axes.

    The baseline uses a modest tipping velocity about a diameter. This makes
    its attitude evolve during free fall without an artificial self-spin.
    """
    vector = [float(v) for v in physics['lid_start_spin']]
    if str(physics.get('lid_start_spin_axis', 'world')).lower() != 'lid':
        return vector
    qx, qy, qz, qw = (float(v) for v in orientation)
    tx = 2.0 * (qy * vector[2] - qz * vector[1])
    ty = 2.0 * (qz * vector[0] - qx * vector[2])
    tz = 2.0 * (qx * vector[1] - qy * vector[0])
    return [
        vector[0] + qw * tx + (qy * tz - qz * ty),
        vector[1] + qw * ty + (qz * tx - qx * tz),
        vector[2] + qw * tz + (qx * ty - qy * tx),
    ]


# ------------------------------------------------------------------- dynamics


# Indices into pybullet's getDynamicsInfo tuple (measured against this
# build: 0 mass, 1 lateral friction, 2 inertia diagonal, 5 restitution,
# 6 rolling friction, 7 spinning friction), one per LIVE_FIELDS entry --
# what lets a timed edit record the value it found before it wrote.
DYNAMICS_INDEX = {
    'mass': 0,
    'lateralFriction': 1,
    'restitution': 5,
    'rollingFriction': 6,
    'spinningFriction': 7,
}


def apply_live_params(client: int, body: int, params: dict[str, Any], *,
                      frame_index: int, time_sec: float,
                      gravity_state: dict[str, float]) -> list[dict[str, Any]]:
    """Write one frame's schedule into the live lid and report what changed.

    Every entry records the frame it landed on, the value read from the
    running body just before the write, and the value written -- the receipt
    that the edit happened inside the simulation rather than in the config.
    ``gravity_state`` carries the live world gravity: pybullet exposes no
    getter for it, so the simulator tracks the value it last set.
    """
    events: list[dict[str, Any]] = []
    for key, value in params.items():
        if key in WORLD_TIMED_FIELDS:
            if key == 'gravity_z':
                previous = gravity_state['z']
                gravity_state['z'] = float(value)
                p.setGravity(0.0, 0.0, float(value), physicsClientId=client)
                events.append({
                    'frame': frame_index,
                    'time_sec': time_sec,
                    'parameter': key,
                    'from_value': previous,
                    'to_value': float(value),
                    'applied_in_simulation': True,
                })
            continue
        if key not in LIVE_FIELDS:
            raise ValueError(
                f'timed edit cannot write {key!r}; this scene accepts '
                f'{sorted(LIVE_FIELDS | WORLD_TIMED_FIELDS)}'
            )
        field, _ = LIVE_FIELDS[key]
        previous = p.getDynamicsInfo(body, -1, physicsClientId=client)[DYNAMICS_INDEX[field]]
        p.changeDynamics(body, -1, physicsClientId=client, **{field: float(value)})
        events.append({
            'frame': frame_index,
            'time_sec': time_sec,
            'parameter': key,
            'from_value': previous,
            'to_value': float(value),
            'applied_in_simulation': True,
        })
    return events


def simulate(
    scenario: dict[str, Any],
    *,
    fps: int,
    duration_sec: float,
    substeps: int,
    hull_path: Path | None,
) -> dict[str, Any]:
    physics = scenario['physics']
    layout = scenario['layout']

    fps = int(fps)
    frame_end = max(2, int(round(float(duration_sec) * fps)))
    substeps = max(1, int(substeps))
    dt = 1.0 / (fps * substeps)

    mass = float(physics['lid_mass'])
    contact_stride = max(1, substeps // 10)
    if mass <= 0.0:
        raise ValueError('lid_mass must be positive')
    for key in ('lid_restitution', 'lid_rolling_friction', 'lid_spinning_friction'):
        if float(physics[key]) < 0.0:
            raise ValueError(f'{key} must be non-negative')
    if not 0.0 <= float(physics['lid_restitution']) <= 1.0:
        raise ValueError('lid_restitution must be in [0, 1]')

    vertices, hull_meta = load_hull(hull_path, physics)
    lo, hi = extent(vertices)
    # Resting pose of a flat lid: its lowest vertex touches the floor.
    rest_center_z = -lo[2]

    tilt = [math.radians(float(a)) for a in physics['lid_start_tilt_deg']]
    tilt_quaternion = p.getQuaternionFromEuler(tilt)
    spin_world = start_spin_world(physics, tilt_quaternion)
    # The release height is measured to the lid's lowest point in the attitude
    # it is released in, so "drop_height" means the same thing at any tilt.
    tilt_rotation = p.getMatrixFromQuaternion(tilt_quaternion)
    release_lowest = min(
        tilt_rotation[6] * v[0] + tilt_rotation[7] * v[1] + tilt_rotation[8] * v[2]
        for v in vertices
    )
    start = [
        float(physics['lid_start_xy'][0]),
        float(physics['lid_start_xy'][1]),
        float(physics['lid_drop_height']) - release_lowest,
    ]

    client = p.connect(p.DIRECT)
    try:
        p.resetSimulation(physicsClientId=client)
        gravity_state = {'z': float(physics['gravity_z'])}
        p.setGravity(0.0, 0.0, gravity_state['z'], physicsClientId=client)
        p.setTimeStep(dt, physicsClientId=client)
        p.setPhysicsEngineParameter(
            fixedTimeStep=dt,
            numSolverIterations=int(physics['solver_iterations']),
            numSubSteps=1,
            # Deliberately tight. A flat disc lying on a flat floor is a
            # face-to-face contact, so it rocks by a couple of degrees while it
            # slides, and this is the threshold that keeps that rock smallest:
            # measured floor-height jitter over the roll is 15 mm here, 15 mm
            # at 6 mm and 47 mm at the engine default of 20 mm.
            contactBreakingThreshold=0.002,
            deterministicOverlappingPairs=1,
            physicsClientId=client,
        )

        floor_shape = p.createCollisionShape(
            p.GEOM_BOX,
            halfExtents=(FLOOR_HALF_EXTENT, FLOOR_HALF_EXTENT, FLOOR_THICKNESS / 2),
            physicsClientId=client,
        )
        floor = p.createMultiBody(
            0.0,
            floor_shape,
            -1,
            (0.0, 0.0, -FLOOR_THICKNESS / 2),
            physicsClientId=client,
        )
        # Restitution is left at 1.0 so the lid's own value is what the video
        # shows (PyBullet multiplies the two). Rolling and spinning friction
        # are NOT left at their defaults: PyBullet *adds* them to the lid's own
        # values, and at the default 1.0 the sum is a rolling resistance large
        # enough to stop every rotation within two substeps. The lid then lands
        # and freezes standing on its edge instead of tipping over its rim,
        # which is exactly the artefact this scene used to have. Measured:
        # floor rolling friction 1.0 leaves the lid with a peak |omega| of 0.00
        # rad/s, 0.01 gives 0.9. The two values below are what let the rim
        # pivot happen at all.
        p.changeDynamics(
            floor,
            -1,
            lateralFriction=float(physics['floor_friction']),
            restitution=1.0,
            rollingFriction=float(physics['floor_rolling_friction']),
            spinningFriction=float(physics['floor_spinning_friction']),
            physicsClientId=client,
        )

        # The ADDed bowl: kitchen_tableware_collision's ceramic rice bowl,
        # scaled to bowl_radius_m. The collision body is the convex hull of
        # that shared lathe profile -- the same closed solid that scene uses
        # -- and the renderer lathes the identical profile for the visible
        # mesh, so what you see and what the solver touches are one shape.
        # The hull fills the bowl's interior; the dropped lid is wider than
        # the mouth, so it always strikes the rim region and can never sink
        # deep enough to rest on the interior ceiling where it would look
        # wrong. The body has real mass and a sub-1 restitution: the falling
        # lid knocks the bowl flying askew instead of passing through it.
        bowl_present = bool((physics.get('bowl_presence') or [0])[0])
        bowl_body = None
        if bowl_present:
            bowl_radius = float(physics['bowl_radius_m'])
            bowl_mass = float(physics['bowl_mass_kg'])
            bx, by, bz = (float(v) for v in physics['bowl_start_position'])
            bowl_scale = bowl_radius / _clean_scene_bundle.BOWL_PROFILE_BASE_RADIUS_M
            bowl_com = _clean_scene_bundle.BOWL_COM_HEIGHT_M * bowl_scale
            bowl_segments = 96
            bowl_hull = [
                [r * math.cos(i * 2.0 * math.pi / bowl_segments),
                 r * math.sin(i * 2.0 * math.pi / bowl_segments),
                 z * bowl_scale - bowl_com]
                for r, z in _clean_scene_bundle.BOWL_PROFILE
                for i in range(bowl_segments)
            ]
            bowl_shape = p.createCollisionShape(
                p.GEOM_MESH, vertices=bowl_hull, physicsClientId=client)
            bowl_body = p.createMultiBody(
                bowl_mass, bowl_shape, -1, (bx, by, bz + bowl_com),
                physicsClientId=client)
            p.changeDynamics(
                bowl_body,
                -1,
                lateralFriction=float(physics.get('bowl_friction', 0.4)),
                restitution=float(physics.get('bowl_restitution', 0.2)),
                rollingFriction=0.0001,
                spinningFriction=0.001,
                linearDamping=0.0,
                angularDamping=0.0,
                collisionMargin=0.0002,
                physicsClientId=client,
            )

        lid_shape = p.createCollisionShape(
            p.GEOM_MESH,
            vertices=vertices,
            physicsClientId=client,
        )
        lid = p.createMultiBody(
            baseMass=mass,
            baseCollisionShapeIndex=lid_shape,
            baseVisualShapeIndex=-1,
            basePosition=start,
            baseOrientation=p.getQuaternionFromEuler(tilt),
            physicsClientId=client,
        )
        p.changeDynamics(
            lid,
            -1,
            lateralFriction=float(physics['lid_friction']),
            rollingFriction=float(physics['lid_rolling_friction']),
            spinningFriction=float(physics['lid_spinning_friction']),
            restitution=float(physics['lid_restitution']),
            linearDamping=float(physics['lid_linear_damping']),
            angularDamping=float(physics['lid_angular_damping']),
            collisionMargin=float(physics.get('lid_collision_margin_m', 0.0002)),
            # A lid balanced on its rim is a stable solver state: the contact
            # patch sits directly under the centre of mass, gravity produces no
            # torque, and if the body is allowed to fall asleep there it stands
            # on edge for the rest of the clip. Real lids always topple, and
            # keeping the body awake is what lets that happen.
            activationState=p.ACTIVATION_STATE_DISABLE_SLEEPING,
            physicsClientId=client,
        )
        p.resetBaseVelocity(
            lid,
            linearVelocity=[float(v) for v in physics['lid_start_velocity']],
            angularVelocity=spin_world,
            physicsClientId=client,
        )

        timed_edits = {
            int(entry['frame']): dict(entry['params'])
            for entry in (physics.get('timed_edits') or [])
        }
        for frame, params in timed_edits.items():
            if not 2 <= frame <= frame_end:
                # Frame 1 is the initial state, which the ordinary parameters
                # already set -- the same rule the shared schedule loader
                # enforces for the scenes that use it.
                raise ValueError(
                    f'timed edit at frame {frame} is outside the clip (2..{frame_end})'
                )
            if set(params) - set(LIVE_FIELDS) - WORLD_TIMED_FIELDS:
                raise ValueError(
                    f'timed edit at frame {frame} sets '
                    f'{sorted(set(params) - set(LIVE_FIELDS) - WORLD_TIMED_FIELDS)}; '
                    f'this scene accepts {sorted(LIVE_FIELDS | WORLD_TIMED_FIELDS)}'
                )

        frames: list[dict[str, Any]] = []
        timed_events: list[dict[str, Any]] = []
        first_contact_frame: int | None = None
        for frame_index in range(1, frame_end + 1):
            touched = False
            if frame_index > 1:
                # A timed edit lands at the top of its frame, before the
                # frame's substeps run: every frame before it is the source
                # video's own physics, and the edit shapes everything after.
                if frame_index in timed_edits:
                    timed_events.extend(apply_live_params(
                        client, lid, timed_edits[frame_index],
                        frame_index=frame_index, time_sec=(frame_index - 1) / float(fps),
                        gravity_state=gravity_state,
                    ))
                for step in range(substeps):
                    p.stepSimulation(physicsClientId=client)
                    # The touchdown is a one- or two-substep event, so it is
                    # looked for on every substep until it has been found;
                    # afterwards a strided check is enough to keep the per-frame
                    # contact flag honest and costs a tenth as much.
                    if first_contact_frame is not None and step % contact_stride:
                        continue
                    if p.getContactPoints(lid, floor, physicsClientId=client):
                        touched = True
                        if first_contact_frame is None:
                            first_contact_frame = frame_index

            position, quaternion = p.getBasePositionAndOrientation(lid, physicsClientId=client)
            linear, angular = p.getBaseVelocity(lid, physicsClientId=client)
            if bowl_body is not None:
                bowl_position, bowl_quaternion = p.getBasePositionAndOrientation(
                    bowl_body, physicsClientId=client)
            else:
                bowl_position = bowl_quaternion = None

            frames.append(
                {
                    'frame_index': frame_index,
                    'time_sec': (frame_index - 1) / float(fps),
                    'lid_location': list(position),
                    'lid_quaternion_xyzw': list(quaternion),
                    'lid_linear_velocity': list(linear),
                    'lid_angular_velocity': list(angular),
                    'lid_point_gap': lowest_point_gap(position, quaternion, vertices),
                    'contacting': touched,
                    'bowl_present': bowl_present,
                    'bowl_location': list(bowl_position) if bowl_body is not None else None,
                    'bowl_quaternion_xyzw': list(bowl_quaternion) if bowl_body is not None else None,
                }
            )

        # How visibly the lid's contact moved the bowl: how far its centre
        # travelled and how far its axis tipped away from vertical. The first
        # number proves the hit, the second proves the knock-over.
        bowl_motion: dict[str, float] | None = None
        if bowl_body is not None:
            start_bx, start_by, _ = (float(v) for v in physics['bowl_start_position'])
            final_bowl = frames[-1]['bowl_location']
            final_quat = frames[-1]['bowl_quaternion_xyzw']
            axis = p.getMatrixFromQuaternion(final_quat)[6:9]
            bowl_motion = {
                'displacement_m': round(math.hypot(final_bowl[0] - start_bx, final_bowl[1] - start_by), 4),
                'final_tilt_deg': round(math.degrees(math.acos(max(-1.0, min(1.0, axis[2])))), 2),
            }

        quality = measure(frames, fps=fps, first_contact_frame=first_contact_frame, hull=vertices, lo=lo)
        return {
            'schema_version': 1,
            'simulator': 'pybullet',
            'fps': fps,
            'frame_start': 1,
            'frame_end': frame_end,
            'duration_sec': float(duration_sec),
            'substeps_per_frame': substeps,
            'physics_dt': dt,
            'coordinate_system': 'simulation coordinates, +Z up, origin on the floor under the drop',
            'bowl_present': bowl_present,
            'bowl_start_position': [float(v) for v in physics.get('bowl_start_position', [0.0, 0.0, 0.0])],
            'bowl_motion': bowl_motion,
            'geometry': {
                'hull': hull_meta,
                'vertex_count': len(vertices),
                'diameter_m': float(max(hi[0] - lo[0], hi[1] - lo[1])),
                'height_m': float(hi[2] - lo[2]),
                'rest_center_z': rest_center_z,
                'start_location': start,
                'start_tilt_deg': [float(a) for a in physics['lid_start_tilt_deg']],
                'start_spin_world': [round(v, 4) for v in spin_world],
            },
            'physics': {k: v for k, v in physics.items() if k != 'timed_edits'},
            'timed_edits': [
                {'frame': frame, 'params': params}
                for frame, params in sorted(timed_edits.items())
            ],
            'timed_events': timed_events,
            'quality': dict(quality, timed_events=timed_events),
            'frames': frames,
        }
    finally:
        p.disconnect(client)


def measure(
    frames: list[dict[str, Any]],
    *,
    fps: int,
    first_contact_frame: int | None,
    hull: list[list[float]],
    lo: list[float],
) -> dict[str, Any]:
    """The numbers the README quotes, all read off the trajectory itself."""
    # A hop is a moment where the lid's *lowest point* is off the floor. Two
    # other definitions were tried and both lie: a local maximum of the centre
    # height counts the lid swinging up over a rim contact as a bounce (that
    # made a lid with restitution 0.05 look bouncier than the baseline), and an
    # unfiltered local maximum counts solver jitter: it turned one landing into
    # twenty-one "hops" of a millimetre each. MIN_HOP is 4 mm off the floor.
    MIN_HOP = 0.004
    apexes: list[dict[str, float]] = []
    for index in range(1, len(frames) - 1):
        current = frames[index]
        z_prev = frames[index - 1]['lid_location'][2]
        z_now = current['lid_location'][2]
        z_next = frames[index + 1]['lid_location'][2]
        if not (z_now > z_prev and z_now >= z_next and current['frame_index'] > 1):
            continue
        if current['lid_point_gap'] < MIN_HOP:
            continue
        apexes.append(
            {
                'frame': current['frame_index'],
                'center_z': round(z_now, 4),
                'point_gap': round(current['lid_point_gap'], 4),
            }
        )
    if first_contact_frame is not None:
        apexes = [a for a in apexes if a['frame'] >= first_contact_frame]

    # Settled = the remainder of the clip stays under a hair of motion.
    quiet_speed, quiet_spin, quiet_frames = 0.03, 0.12, int(0.25 * fps)
    settle_frame = None
    streak = 0
    for record in reversed(frames):
        linear = math.dist(record['lid_linear_velocity'], (0.0, 0.0, 0.0))
        spin = math.dist(record['lid_angular_velocity'], (0.0, 0.0, 0.0))
        if linear < quiet_speed and spin < quiet_spin:
            streak += 1
            if streak >= quiet_frames:
                settle_frame = frames[-streak]['frame_index']
        else:
            break

    start = frames[0]['lid_location']
    end = frames[-1]['lid_location']
    travel = math.dist((start[0], start[1]), (end[0], end[1]))
    touchdown = [f for f in frames if f['contacting']]
    after_contact = [
        f['lid_location'][2]
        for f in frames
        if first_contact_frame is not None and f['frame_index'] >= first_contact_frame
    ]
    # The single number that answers "how bouncy is it": how far the lowest
    # point of the lid ever gets off the floor after it first touches down.
    air_gap = max(
        (f['lid_point_gap'] for f in frames
         if first_contact_frame is not None and f['frame_index'] >= first_contact_frame),
        default=float('nan'),
    )
    return {
        'first_contact_frame': first_contact_frame,
        'contact_frame_count': len(touchdown),
        'apexes_after_contact': apexes,
        'max_center_z_after_contact': round(max(after_contact, default=float('nan')), 4),
        'max_point_gap_after_contact': round(air_gap, 4),
        'settle_frame': settle_frame,
        'horizontal_travel_m': round(travel, 4),
        'final_speed_m_s': round(math.dist(frames[-1]['lid_linear_velocity'], (0.0, 0.0, 0.0)), 4),
        'final_spin_rad_s': round(math.dist(frames[-1]['lid_angular_velocity'], (0.0, 0.0, 0.0)), 4),
        'min_point_gap_m': round(min(f['lid_point_gap'] for f in frames), 5),
        'rest_center_z': round(-lo[2], 5),
        'hull_vertex_count': len(hull),
    }


def main() -> None:
    args = parse_args()
    scenario = scenario_io.load_scenario(args.scenario, args.scenario_overrides_json)
    physics = scenario['physics']

    hull_path = args.lid_hull_json or args.out.parent / 'lid_hull.json'
    records = simulate(
        scenario,
        fps=int(args.fps if args.fps is not None else physics['fps']),
        duration_sec=float(
            args.duration_sec if args.duration_sec is not None else physics['duration_sec']
        ),
        substeps=int(args.substeps if args.substeps is not None else physics['substeps_per_frame']),
        hull_path=hull_path,
    )
    scenario_io.write_json(args.out, records)

    quality = records['quality']
    print(f"frames 1..{records['frame_end']} @ {records['fps']} fps")
    print(f"first contact frame: {quality['first_contact_frame']}")
    print(f"apexes after contact: {[a['frame'] for a in quality['apexes_after_contact']]}")
    print(f"settle frame: {quality['settle_frame']}")
    print(f"horizontal travel: {quality['horizontal_travel_m']} m")
    print(f"final speed/spin: {quality['final_speed_m_s']} m/s, {quality['final_spin_rad_s']} rad/s")
    if records.get('bowl_motion'):
        bowl_motion = records['bowl_motion']
        print(f"bowl knocked: moved {bowl_motion['displacement_m']} m, "
              f"final tilt {bowl_motion['final_tilt_deg']} deg")
    if not hull_path.is_file():
        print(f'[warning] {hull_path.name} missing: simulated with the analytic disc fallback')


if __name__ == '__main__':
    main()

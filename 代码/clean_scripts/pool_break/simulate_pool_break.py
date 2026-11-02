"""PyBullet simulation for a three-ball pool break.

Four rigid spheres -- the white cue ball and a three-ball rack -- on a felt
plane bounded by four cushion walls. Nothing about the spread is authored: the
cue ball is given a launch velocity on frame 1 and Bullet solves the rest. The
apex ball is wedged between the two rear balls, so the cue's impulse travels
through it into both, which is what makes the triangle open up instead of the
apex ball simply rolling away from an untouched pair.

Why the cushion walls and not the model's pockets
-------------------------------------------------
Modelling the six pockets would make this scene a different benchmark: a
three-ball break at these speeds pockets something on most parameter settings,
the outcome turns binary and noisy, and the spread metric stops being
monotonic in cue speed. The walls keep every ball on the table, which is what
the exposed controls are supposed to move. The visual pockets in the GLB are
therefore decoration; the physics boundary is the cushion nose at
``PLAY_HALF_X`` / ``PLAY_HALF_Y``.

Exposed controls (also the CLI flags and the live parameters for mid-clip edits)
  --cue-speed            cue-ball launch speed in m/s
  --cue-contact-offset   signed lateral offset of the cue's line of travel from
                         the apex ball's centre in m; 0 is a full-ball hit,
                         +/- one radius is a half-ball hit
  --cue-mass             cue-ball mass in kg

One loss is integrated by hand: ``--ball-roll-decel``, the cloth drag. Bullet
has no rolling resistance it can apply to a sphere without also cancelling the
spin the contact friction builds (see ``FIXED_PHYSICS``), and a rigid sphere
that has reached rolling-without-slip coasts forever -- so the clip would end
with every ball still moving. See ``cfg.BALL_ROLL_DECEL`` for the value.
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

import pybullet as p

import pcve_timed_edits as timed  # noqa: E402

import scene_support.pool_break.scene_config as cfg  # noqa: E402
from scene_support.pool_break.cache_contract import CACHE_SCHEMA_VERSION, signature

BALL_SLOTS = ("cue_ball", "apex_ball", "left_ball", "right_ball")
# Every pair of balls whose surface gap this scene reports. Named once so the
# per-frame records, the substep contact probe and the quality block cannot
# disagree about which pairs exist.
BALL_PAIRS = {
    "cue_apex": ("cue_ball", "apex_ball"),
    "apex_left": ("apex_ball", "left_ball"),
    "apex_right": ("apex_ball", "right_ball"),
    "cue_left": ("cue_ball", "left_ball"),
    "cue_right": ("cue_ball", "right_ball"),
    "left_right": ("left_ball", "right_ball"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulate a three-ball pool break.")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--fps", type=int, default=cfg.BASELINE_RENDER["fps"])
    parser.add_argument("--duration-sec", type=float, default=cfg.BASELINE_RENDER["duration_sec"])
    parser.add_argument("--substeps", type=int, default=cfg.SUBSTEPS_PER_FRAME)
    parser.add_argument("--ball-radius", type=float, default=cfg.BALL_RADIUS)
    parser.add_argument(
        "--cue-speed", type=float, default=cfg.BASELINE_PHYSICS["cue_speed"],
        help="Cue-ball launch speed in m/s.",
    )
    parser.add_argument(
        "--cue-contact-offset", type=float, default=cfg.BASELINE_PHYSICS["cue_contact_offset"],
        help="Signed lateral offset (m) of the cue's line of travel from the apex "
             "ball's centre. 0 is a full-ball hit, +R is a half-ball hit on the "
             "apex ball's right side, -R on its left.",
    )
    parser.add_argument(
        "--cue-mass", type=float, default=cfg.BASELINE_PHYSICS["cue_mass"],
        help="Cue-ball mass in kg.",
    )
    parser.add_argument("--object-mass", type=float, default=cfg.FIXED_PHYSICS["object_mass"])
    parser.add_argument("--cue-friction", type=float, default=cfg.FIXED_PHYSICS["ball_friction"])
    parser.add_argument("--object-friction", type=float, default=cfg.FIXED_PHYSICS["ball_friction"])
    parser.add_argument("--ball-rolling-friction", type=float,
                        default=cfg.FIXED_PHYSICS["ball_rolling_friction"])
    parser.add_argument("--ball-spinning-friction", type=float,
                        default=cfg.FIXED_PHYSICS["ball_spinning_friction"])
    parser.add_argument("--ball-roll-decel", type=float, default=cfg.BALL_ROLL_DECEL,
                        help="Cloth drag in m/s^2, integrated by hand because a "
                             "rigid sphere on a rigid plane does not stop on its own.")
    parser.add_argument("--cue-restitution", type=float,
                        default=cfg.FIXED_PHYSICS["ball_restitution"])
    parser.add_argument("--object-restitution", type=float,
                        default=cfg.FIXED_PHYSICS["ball_restitution"])
    parser.add_argument("--felt-friction", type=float, default=cfg.FIXED_PHYSICS["felt_friction"])
    parser.add_argument("--felt-restitution", type=float,
                        default=cfg.FIXED_PHYSICS["felt_restitution"])
    parser.add_argument("--cushion-friction", type=float,
                        default=cfg.FIXED_PHYSICS["cushion_friction"])
    parser.add_argument("--cushion-restitution", type=float,
                        default=cfg.FIXED_PHYSICS["cushion_restitution"])
    parser.add_argument("--gravity-z", type=float, default=cfg.FIXED_PHYSICS["gravity_z"])
    # Edits that land partway through the clip:
    # [{"frame": n, "params": {physics_key: new_value}}]. Everything before n is
    # the source clip; at n the params are written into the live simulation.
    parser.add_argument("--timed-edits-json", type=Path, default=None)
    return parser.parse_args()


# ------------------------------------------------------------------ geometry


def make_felt(client: int, *, surface_z: float) -> int:
    """One big static box whose top face is the felt."""
    half = max(cfg.PLAY_HALF_X, cfg.PLAY_HALF_Y) + 0.25
    shape = p.createCollisionShape(
        p.GEOM_BOX, halfExtents=(half, half, 0.01), physicsClientId=client
    )
    body = p.createMultiBody(
        baseMass=0.0, baseCollisionShapeIndex=shape, baseVisualShapeIndex=-1,
        basePosition=(0.0, 0.0, surface_z - 0.01), physicsClientId=client,
    )
    p.changeDynamics(
        body, -1,
        lateralFriction=float(cfg.FIXED_PHYSICS["felt_friction"]),
        # Both left at zero: see ``FIXED_PHYSICS["ball_rolling_friction"]``.
        spinningFriction=0.0,
        rollingFriction=0.0,
        restitution=float(cfg.FIXED_PHYSICS["felt_restitution"]),
        collisionMargin=0.0002,
        physicsClientId=client,
    )
    return body


def make_cushions(client: int) -> list[int]:
    """Four static walls whose inner faces are the cushion noses.

    Height is the real nose height (63.5 % of a ball diameter): tall enough that
    a ball cannot climb over it at any speed this scene reaches, low enough that
    a hard-hit ball is not lifted over the top by the wall's upper edge.
    """
    height = cfg.CUSHION_HEIGHT
    thickness = cfg.CUSHION_THICKNESS
    half_z = height / 2.0
    px, py = cfg.PLAY_HALF_X, cfg.PLAY_HALF_Y

    end_shape = p.createCollisionShape(
        p.GEOM_BOX, halfExtents=(thickness / 2.0, py + thickness, half_z),
        physicsClientId=client,
    )
    side_shape = p.createCollisionShape(
        p.GEOM_BOX, halfExtents=(px + thickness, thickness / 2.0, half_z),
        physicsClientId=client,
    )
    bodies = []
    for x in (px + thickness / 2.0, -(px + thickness / 2.0)):
        bodies.append(p.createMultiBody(
            baseMass=0.0, baseCollisionShapeIndex=end_shape, baseVisualShapeIndex=-1,
            basePosition=(x, 0.0, half_z), physicsClientId=client,
        ))
    for y in (py + thickness / 2.0, -(py + thickness / 2.0)):
        bodies.append(p.createMultiBody(
            baseMass=0.0, baseCollisionShapeIndex=side_shape, baseVisualShapeIndex=-1,
            basePosition=(0.0, y, half_z), physicsClientId=client,
        ))
    for body in bodies:
        p.changeDynamics(
            body, -1,
            lateralFriction=float(cfg.FIXED_PHYSICS["cushion_friction"]),
            restitution=float(cfg.FIXED_PHYSICS["cushion_restitution"]),
            collisionMargin=0.0002,
            physicsClientId=client,
        )
    return bodies


def spawn_layout(cue_contact_offset: float, radius: float, surface_z: float) -> dict[str, tuple]:
    """Initial centres, in the order ``BALL_SLOTS`` names them."""
    rack = cfg.rack_centres()
    z = surface_z + radius
    layout = {
        # The cue ball travels parallel to the table axis; the *offset* is what
        # makes the hit off-centre, not a rotated launch direction. Rotating the
        # direction instead would move the impact point by
        # travel_distance * sin(angle), so a 1.5 degree aim error would already
        # be a half-ball hit -- useless as a knob.
        "cue_ball": (cfg.CUE_START_X, float(cue_contact_offset), z),
    }
    for slot, (x, y) in rack.items():
        layout[slot] = (float(x), float(y), z)
    return layout


# -------------------------------------------------------------- live editing


def apply_timed_params(client: int, params: dict, *, bodies: dict) -> None:
    """Write one frame's worth of edited physics into the running simulation.

    Only what this scene's vocabulary can produce is handled; a parameter it
    does not recognise raises, because an edit that is silently dropped renders
    as a video that looks like the baseline. Launch speed and contact offset are
    starting conditions -- they are set when the cue ball is fired and there is
    nothing left to change afterwards -- so they are rejected here and can only
    be written as whole-clip edits.
    """
    for key, value in params.items():
        if key == "cue_mass":
            timed.set_one(p, client, bodies["cue_ball"], "mass", value)
        elif key == "object_mass":
            for slot in ("apex_ball", "left_ball", "right_ball"):
                timed.set_one(p, client, bodies[slot], "mass", value)
        elif key == "cue_friction":
            timed.set_one(p, client, bodies["cue_ball"], "lateralFriction", value)
        elif key == "object_friction":
            for slot in ("apex_ball", "left_ball", "right_ball"):
                timed.set_one(p, client, bodies[slot], "lateralFriction", value)
        elif key == "cue_restitution":
            timed.set_one(p, client, bodies["cue_ball"], "restitution", value)
        elif key == "object_restitution":
            for slot in ("apex_ball", "left_ball", "right_ball"):
                timed.set_one(p, client, bodies[slot], "restitution", value)
        else:
            raise timed.unknown_param(key)


# ------------------------------------------------------------- kinematics


def _quat_multiply(a: tuple, b: tuple) -> tuple:
    """Hamilton product a * b for scalar-last quaternions (x, y, z, w)."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def rolling_quaternions(locations: list[tuple[float, float, float]], radius: float) -> list[tuple]:
    """Orientations that make a sphere appear to roll along its own path.

    Bullet does spin spheres, but the spin it produces is not reliable at these
    contact settings (a ball that is almost slipping reads as a ball that is
    sliding). Reconstructing roll-without-slip from the position path is exact
    for the visual question -- does the number face rotate the way the ball
    travels -- and the alternative was a ball that skates across the felt.

    The axis is ``up x travel``, not ``travel x up``: rolling in +X means the
    ball turns about +Y (the contact patch is instantaneously pinned, so
    ``v = omega x R z_hat``), and ``z_hat x x_hat = +y_hat``. Taking the cross
    product the other way round is the same rotation with the sign flipped,
    which renders as every ball back-spinning along its own path -- a ball that
    slides while its number turns backwards.
    """
    identity = (0.0, 0.0, 0.0, 1.0)
    quaternions = [identity]
    for i in range(1, len(locations)):
        x0, y0, _ = locations[i - 1]
        x1, y1, _ = locations[i]
        dx, dy = x1 - x0, y1 - y0
        distance = math.hypot(dx, dy)
        if distance < 1e-9:
            quaternions.append(quaternions[-1])
            continue
        # Roll axis = up x travel direction.
        axis_x, axis_y = -dy / distance, dx / distance
        half_angle = distance / (2.0 * radius)
        s, c = math.sin(half_angle), math.cos(half_angle)
        quaternions.append(
            _quat_multiply((axis_x * s, axis_y * s, 0.0, c), quaternions[-1])
        )
    return quaternions


def _spread(centres: dict[str, tuple[float, float]]) -> float:
    """Mean pairwise centre distance among the three racked balls."""
    names = ("apex_ball", "left_ball", "right_ball")
    pairs = [("apex_ball", "left_ball"), ("apex_ball", "right_ball"),
             ("left_ball", "right_ball")]
    return sum(
        math.dist(centres[a][:2], centres[b][:2]) for a, b in pairs
    ) / len(pairs)


def _deflection_deg(start, end) -> float:
    """Signed angle of a displacement away from the cue's direction (-X)."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    if math.hypot(dx, dy) < 1e-6:
        return 0.0
    return math.degrees(math.atan2(dy, -dx))


def _angle_from_axis(start, end, min_dist: float = 0.003) -> float | None:
    """Signed angle of ``start -> end`` away from the cue's line (-X), in degrees."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    if math.hypot(dx, dy) < min_dist:
        return None
    return math.degrees(math.atan2(dy, -dx))


def _rack_centroid(frame: dict) -> tuple[float, float]:
    """Centre of the three racked balls, which is what a break sends off."""
    points = [frame[f"{slot}_location"][:2] for slot in ("apex_ball", "left_ball", "right_ball")]
    return (sum(p[0] for p in points) / 3.0, sum(p[1] for p in points) / 3.0)


def _fmt_angle(value) -> str:
    return "n/a" if value is None else f"{value:+.1f}deg"


# ------------------------------------------------------------------ simulate


def simulate(args: argparse.Namespace) -> dict:
    for name in ("fps", "duration_sec", "substeps", "cue_speed", "ball_radius",
                 "cue_mass", "object_mass", "felt_friction", "cushion_friction"):
        value = getattr(args, name)
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be positive and finite")
    for name in ("cue_contact_offset", "ball_rolling_friction", "ball_spinning_friction",
                 "cue_friction", "object_friction", "cue_restitution",
                 "object_restitution", "felt_restitution", "cushion_restitution",
                 "gravity_z"):
        if not math.isfinite(getattr(args, name)):
            raise ValueError(f"{name} must be finite")
    if not math.isfinite(args.ball_roll_decel) or args.ball_roll_decel < 0.0:
        raise ValueError("ball_roll_decel must be finite and non-negative")
    if abs(float(args.cue_contact_offset)) >= 2.0 * float(args.ball_radius):
        raise ValueError(
            "cue_contact_offset of "
            f"{float(args.cue_contact_offset):.4f} m is at or past a clean miss "
            f"({2.0 * float(args.ball_radius):.4f} m); the cue ball would never "
            "touch the rack"
        )

    fps = int(args.fps)
    frame_end = max(2, int(round(float(args.duration_sec) * fps)))
    substeps = int(args.substeps)
    dt = 1.0 / float(fps * substeps)
    radius = float(args.ball_radius)
    roll_decel = float(args.ball_roll_decel)
    surface_z = 0.0

    timed_edits = timed.load_timed_edits(args.timed_edits_json)
    timed.check_horizon(timed_edits, frame_end)
    for params in timed_edits.values():
        for key in ("cue_speed", "cue_contact_offset"):
            if key in params:
                raise ValueError(
                    f"{key!r} is a starting condition and cannot be timed. "
                    f"Set --{key.replace('_', '-')} outside the schedule to apply it from frame 1."
                )

    layout = spawn_layout(float(args.cue_contact_offset), radius, surface_z)
    start = {slot: layout[slot][:2] for slot in BALL_SLOTS}

    client = p.connect(p.DIRECT)
    try:
        p.resetSimulation(physicsClientId=client)
        p.setGravity(0.0, 0.0, float(args.gravity_z), physicsClientId=client)
        p.setTimeStep(dt, physicsClientId=client)
        p.setPhysicsEngineParameter(
            fixedTimeStep=dt,
            numSolverIterations=200,
            contactBreakingThreshold=0.0002,
            deterministicOverlappingPairs=1,
            enableConeFriction=1,
            physicsClientId=client,
        )

        make_felt(client, surface_z=surface_z)
        make_cushions(client)

        ball_shape = p.createCollisionShape(p.GEOM_SPHERE, radius=radius, physicsClientId=client)
        bodies: dict[str, int] = {}
        for slot in BALL_SLOTS:
            is_cue = slot == "cue_ball"
            body = p.createMultiBody(
                baseMass=float(args.cue_mass if is_cue else args.object_mass),
                baseCollisionShapeIndex=ball_shape,
                baseVisualShapeIndex=-1,
                basePosition=layout[slot],
                physicsClientId=client,
            )
            p.changeDynamics(
                body, -1,
                lateralFriction=float(args.cue_friction if is_cue else args.object_friction),
                rollingFriction=float(args.ball_rolling_friction),
                spinningFriction=float(args.ball_spinning_friction),
                restitution=float(args.cue_restitution if is_cue else args.object_restitution),
                linearDamping=0.0,
                angularDamping=0.0,
                collisionMargin=0.0001,
                # Never let a slow ball fall asleep mid-clip: the clip has to
                # show it come to rest, not freeze mid-roll.
                activationState=p.ACTIVATION_STATE_DISABLE_SLEEPING,
                physicsClientId=client,
            )
            bodies[slot] = body

        p.resetBaseVelocity(
            bodies["cue_ball"],
            linearVelocity=(-float(args.cue_speed), 0.0, 0.0),
            physicsClientId=client,
        )

        zero = (0.0, 0.0, 0.0)
        frames: list[dict] = []
        paths = {slot: [] for slot in BALL_SLOTS}
        min_gap = {name: float("inf") for name in BALL_PAIRS}
        min_gap_frame: dict[str, int] = {}
        contact_frame = None
        max_speed = 0.0
        max_displacement = {slot: 0.0 for slot in BALL_SLOTS}
        spread_max = _spread(start)
        last_pose = {}

        def apply_roll_resistance() -> None:
            """One substep of cloth drag: shave ``decel * dt`` off each ball's speed.

            A rigid sphere that has reached rolling-without-slip has a
            stationary contact patch, so Coulomb friction exerts nothing on it
            and Bullet will let it coast for the rest of the clip. This is the
            missing loss, written as the constant deceleration real cloth
            produces. It runs after the solver, so it can only remove speed the
            solver has already resolved -- it never changes a collision outcome,
            only how far the ball carries afterwards.
            """
            loss = roll_decel * dt
            if loss <= 0.0:
                return
            for body in bodies.values():
                lin, ang = p.getBaseVelocity(body, physicsClientId=client)
                speed = math.hypot(lin[0], lin[1])
                if speed <= loss:
                    p.resetBaseVelocity(
                        body, linearVelocity=(0.0, 0.0, lin[2]), angularVelocity=ang,
                        physicsClientId=client,
                    )
                else:
                    keep = (speed - loss) / speed
                    p.resetBaseVelocity(
                        body, linearVelocity=(lin[0] * keep, lin[1] * keep, lin[2]),
                        angularVelocity=ang, physicsClientId=client,
                    )

        def surface_gap(a, b) -> float:
            return math.dist(a[:2], b[:2]) - 2.0 * radius

        def sample_contacts(frame_index: int) -> None:
            """Minimum surface gap per pair, sampled every substep.

            Sampling at frame boundaries is not enough: the cue reaches the rack
            and stops inside a single frame, so the frame-boundary gap never
            reads near zero and a "did it hit?" test on it answers no. This also
            catches the penetration depth, which is the one number that says
            whether the substep count is high enough.
            """
            nonlocal contact_frame
            probe = {
                slot: p.getBasePositionAndOrientation(body, physicsClientId=client)[0]
                for slot, body in bodies.items() if body is not None
            }
            for name, (a, b) in BALL_PAIRS.items():
                if a not in probe or b not in probe:
                    continue
                gap = surface_gap(probe[a], probe[b])
                if gap < min_gap[name]:
                    min_gap[name] = gap
                    min_gap_frame[name] = frame_index
            if contact_frame is None and min_gap["cue_apex"] <= 0.0005:
                contact_frame = frame_index

        for frame_index in range(1, frame_end + 1):
            if frame_index > 1:
                # A timed edit lands at the top of its frame, before the
                # frame's substeps run (the same convention ball_block_building
                # uses): every frame before it is the source clip, and the
                # edit shapes everything from that frame's own record on.
                if frame_index in timed_edits:
                    apply_timed_params(client, timed_edits[frame_index], bodies=bodies)
                for _ in range(substeps):
                    p.stepSimulation(physicsClientId=client)
                    apply_roll_resistance()
                    sample_contacts(frame_index)

            record = {"frame_index": frame_index, "time_sec": (frame_index - 1) / float(fps)}
            poses = {}
            for slot in BALL_SLOTS:
                body = bodies.get(slot)
                if body is None:
                    pos, quat = last_pose[slot]
                    lin = ang = zero
                    present = False
                else:
                    pos, quat = p.getBasePositionAndOrientation(body, physicsClientId=client)
                    lin, ang = p.getBaseVelocity(body, physicsClientId=client)
                    last_pose[slot] = (pos, quat)
                    present = True
                poses[slot] = pos
                paths[slot].append(tuple(pos))
                max_speed = max(max_speed, math.sqrt(sum(c * c for c in lin)))
                max_displacement[slot] = max(
                    max_displacement[slot], math.dist(start[slot], pos[:2])
                )
                record[f"{slot}_present"] = present
                record[f"{slot}_location"] = list(pos)
                record[f"{slot}_quaternion_xyzw"] = list(quat)
                record[f"{slot}_linear_velocity"] = list(lin)
                record[f"{slot}_angular_velocity"] = list(ang)
                record[f"{slot}_table_gap"] = pos[2] - surface_z - radius

            for name, (a, b) in BALL_PAIRS.items():
                record[f"{name}_gap"] = surface_gap(poses[a], poses[b])
            spread_max = max(spread_max, _spread({k: tuple(v[:2]) for k, v in poses.items()}))
            frames.append(record)

        # Reconstruct rolling orientation from each ball's own path.
        for slot in BALL_SLOTS:
            for frame, quat in zip(frames, rolling_quaternions(paths[slot], radius)):
                frame[f"{slot}_quaternion_xyzw"] = list(quat)

        final = {slot: tuple(frames[-1][f"{slot}_location"][:2]) for slot in BALL_SLOTS}
        spread_initial = _spread(start)

        def rack_speed(frame: dict) -> float:
            return sum(
                math.sqrt(sum(c * c for c in frame[f"{slot}_linear_velocity"]))
                for slot in ("apex_ball", "left_ball", "right_ball")
            )

        # The post-impact frame, not the contact frame.
        #
        # ``contact_frame`` is the frame during whose substeps the gap first
        # closed -- and the impulse often lands in that frame's *last* substeps,
        # so its frame-boundary record can still show the rack at rest and the
        # cue ball at full speed. Reading the launch numbers off that record
        # made them depend on where the substeps happened to fall: adding cloth
        # drag moved the impact by a fraction of a substep and
        # ``rack_launch_speed_sum`` collapsed to 0.00 while the rack visibly
        # opened. Peaking over the three frames after contact removes the
        # window sensitivity and is what the metric means anyway -- how fast the
        # rack was moving when the break hit it.
        launch_index = (
            max(range(contact_frame - 1, min(len(frames), contact_frame + 2)),
                key=lambda i: rack_speed(frames[i]))
            if contact_frame else None
        )
        launch_frame = frames[launch_index] if launch_index is not None else None
        # Where the break sent things, read off six frames of travel (0.25 s).
        #
        # Displacement, not velocity: within a frame or two of the impact the
        # balls are still being shoved by their neighbours, and one velocity
        # sample points somewhere different depending on which frame it lands
        # on. The rack's own centre is used rather than the apex ball -- in a
        # real rack the apex is wedged and stays put, absorbing nothing, while
        # the impulse goes out through the two wings. An "apex ball left at X
        # degrees" reading is therefore blank for a clean break, which is
        # correct but useless; the centroid always moves.
        travel_index = min(launch_index + 6, len(frames) - 1) if launch_index is not None else None
        rack_launch = (
            _angle_from_axis(_rack_centroid(frames[launch_index]),
                             _rack_centroid(frames[travel_index]))
            if launch_index is not None else None
        )
        cue_launch = (
            _angle_from_axis(frames[launch_index]["cue_ball_location"],
                             frames[travel_index]["cue_ball_location"])
            if launch_index is not None else None
        )
        # How hard the rack was actually hit. This, not the widest the balls ever
        # got, is what separates a break from a tap: on a table this size any
        # struck ball eventually reaches a cushion, so the maximum triangle width
        # saturates at "the table" for every speed above a walking pace.
        rack_launch_speed = rack_speed(launch_frame) if launch_frame else 0.0
        spread_final = _spread(final)
        # Every ball has to stay on the felt: the walls make leaving impossible,
        # so a ball outside the cushions means the collision model broke.
        on_table = all(
            abs(final[slot][0]) <= cfg.PLAY_HALF_X + 1e-6
            and abs(final[slot][1]) <= cfg.PLAY_HALF_Y + 1e-6
            for slot in BALL_SLOTS
        )

        parameters = {
            key: getattr(args, key) for key in (
                "fps", "duration_sec", "substeps", "ball_radius", "cue_speed",
                "cue_contact_offset", "cue_mass", "object_mass", "cue_friction",
                "object_friction", "ball_rolling_friction", "ball_spinning_friction",
                "ball_roll_decel",
                "cue_restitution", "object_restitution", "felt_friction",
                "felt_restitution", "cushion_friction", "cushion_restitution",
                "gravity_z",
            )
        }
        parameters["timed_edits"] = [
            {"frame": frame, "params": params} for frame, params in sorted(timed_edits.items())
        ]

        return {
            "schema_version": CACHE_SCHEMA_VERSION,
            "scene": "pool_break",
            "simulation_parameters": parameters,
            "simulation_signature": signature(parameters),
            "simulator": "pybullet",
            "fps": fps,
            "frame_start": 1,
            "frame_end": frame_end,
            "duration_sec": float(args.duration_sec),
            "substeps_per_frame": substeps,
            "physics_dt": dt,
            "surface_z": surface_z,
            "geometry": {
                "play_half_x": cfg.PLAY_HALF_X,
                "play_half_y": cfg.PLAY_HALF_Y,
                "foot_spot_x": cfg.FOOT_SPOT_X,
                "cue_start_x": cfg.CUE_START_X,
                "cushion_height": cfg.CUSHION_HEIGHT,
                "rack_gap": cfg.RACK_GAP,
            },
            "objects": {
                "cue_ball": {
                    "radius": radius,
                    "mass": float(args.cue_mass),
                    "initial_location": list(layout["cue_ball"]),
                    "initial_velocity": [-float(args.cue_speed), 0.0, 0.0],
                },
                "rack": {
                    "ball_radius": radius,
                    "ball_mass": float(args.object_mass),
                    "initial_locations": {
                        slot: list(layout[slot]) for slot in BALL_SLOTS[1:]
                    },
                },
                "table": {
                    "surface_z": surface_z,
                    "play_half_x": cfg.PLAY_HALF_X,
                    "play_half_y": cfg.PLAY_HALF_Y,
                    "felt_friction": float(args.felt_friction),
                    "cushion_friction": float(args.cushion_friction),
                },
            },
            "physics_parameters": {
                "cue_speed": float(args.cue_speed),
                "cue_contact_offset": float(args.cue_contact_offset),
                "cue_mass": float(args.cue_mass),
                "object_mass": float(args.object_mass),
            },
            "timed_edits": parameters["timed_edits"],
            "quality": {
                "cue_apex_min_gap": min_gap["cue_apex"],
                "apex_left_min_gap": min_gap["apex_left"],
                "apex_right_min_gap": min_gap["apex_right"],
                "contact_frame": contact_frame,
                "contact_frame_by_pair": dict(min_gap_frame),
                "spread_initial_m": spread_initial,
                "spread_final_m": spread_final,
                "spread_max_m": spread_max,
                # What a viewer sees over the whole clip. The rear balls bounce
                # off the side cushions, so the final frame can be a tighter
                # triangle than frame 20 was -- report both.
                "spread_gain_m": spread_max - spread_initial,
                "rack_launch_speed_sum": rack_launch_speed,
                "apex_displacement_m": max_displacement["apex_ball"],
                "left_displacement_m": max_displacement["left_ball"],
                "right_displacement_m": max_displacement["right_ball"],
                "cue_displacement_m": max_displacement["cue_ball"],
                "cue_final_displacement_m": math.dist(start["cue_ball"], final["cue_ball"]),
                # The cut, as physics states it: the direction the rack itself
                # was sent and the cue ball's own deflection, both measured from
                # the cue's original line of travel.
                "rack_launch_angle_deg": rack_launch,
                "cue_launch_angle_deg": cue_launch,
                "apex_net_deflection_deg": _deflection_deg(start["apex_ball"], final["apex_ball"]),
                "cue_net_deflection_deg": _deflection_deg(start["cue_ball"], final["cue_ball"]),
                "max_ball_speed": max_speed,
                "max_penetration_mm": -1000.0 * min(min_gap.values()),
                "all_balls_on_table": on_table,
                # What the suite refuses to ship a source clip without: the cue
                # ball reached the rack, and it hit it hard enough to be a break
                # rather than a nudge.
                "rack_struck": bool(contact_frame is not None),
                "visible": bool(rack_launch_speed >= 1.0),
            },
            "frames": frames,
        }
    finally:
        p.disconnect(client)


def main() -> None:
    args = parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    result = simulate(args)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    q = result["quality"]
    print(
        f"[simulate] speed={result['physics_parameters']['cue_speed']:.2f}m/s "
        f"offset={result['physics_parameters']['cue_contact_offset'] * 1000:+.1f}mm "
        f"mass={result['physics_parameters']['cue_mass']:.3f}kg | "
        f"contact={'frame ' + str(q['contact_frame']) if q['contact_frame'] else 'never'} "
        f"spread={q['spread_initial_m'] * 1000:.1f}->{q['spread_max_m'] * 1000:.1f}mm "
        f"rackSpeed={q['rack_launch_speed_sum']:.2f}m/s "
        f"rackLeave={_fmt_angle(q['rack_launch_angle_deg'])} "
        f"cueLeave={_fmt_angle(q['cue_launch_angle_deg'])}"
    )


if __name__ == "__main__":
    main()

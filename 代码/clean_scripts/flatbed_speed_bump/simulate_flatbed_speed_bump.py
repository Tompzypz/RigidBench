"""PyBullet simulation for a loaded flatbed truck crossing a speed bump.

The truck is two rigid bodies: a rigid chassis (frame, cab and four wheel
cylinders as one compound) and the flatbed deck, carried on a prismatic
suspension between them. Two cargo cartons are separate dynamic rigid bodies
riding loose on the deck.

The suspension is what makes this scene work. A rigid truck that clears a bump
flies as one piece, and so does everything on it -- while the vehicle is
ballistic the deck and its cargo share the same acceleration, so the cargo can
never leave the bed however violent the jump looks. With the deck sprung, the
deck overshoots the chassis and is pulled back down at well over 1 g on the
rebound, which is the one condition under which a loose carton separates from
it. Every carton motion below is Bullet solving contacts; nothing is scripted.

The wheels are cylinders fixed to the chassis with no axle of their own, so
they cannot spin; a realistic tyre coefficient would turn them into skids and
stop the truck before it reached the bump. They are given a near-frictionless
contact instead, which is what a free-rolling tyre looks like in this model:
still carrying the full normal load, so the bump still kicks the truck, just not
dragging. Cruise control is then a longitudinal force at the centre of mass --
see :func:`apply_drive_force` for why it must not be a velocity override.

The three scene controls requested by the benchmark are exposed as CLI flags
and as live parameters for mid-clip edits:
  --truck-speed          cruise speed of the truck in m/s
  --speed-bump-height    speed-bump peak height in m
  --cargo-friction       cargo body's friction coefficient against the deck
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

import scene_support.flatbed_speed_bump.scene_config as cfg  # noqa: E402
from scene_support.flatbed_speed_bump.cache_contract import CACHE_SCHEMA_VERSION,signature


# The suspension joint's anchor, measured in the chassis's own frame (whose
# origin is the chassis centre of mass).
BED_ANCHOR_LOCAL = (cfg.DECK_CENTER_X, 0.0, cfg.DECK_Z - cfg.CHASSIS_COM_Z)
BED_ANCHOR_IDENTITY = (0.0, 0.0, 0.0, 1.0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Simulate a loaded flatbed truck striking a rounded speed bump."
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--fps", type=int, default=cfg.BASELINE_RENDER["fps"])
    parser.add_argument("--duration-sec", type=float, default=cfg.BASELINE_RENDER["duration_sec"])
    parser.add_argument("--substeps", type=int, default=60)
    parser.add_argument(
        "--truck-speed", type=float, default=cfg.BASELINE_PHYSICS["truck_speed"],
        help="Powered flatbed-truck speed in m/s. At the default bump this is "
             "deliberately high enough to throw the cargo clear of the deck.",
    )
    parser.add_argument(
        "--speed-bump-height", type=float, default=cfg.BASELINE_PHYSICS["speed_bump_height"],
        help="Peak height of the rounded speed bump in m.",
    )
    parser.add_argument(
        "--cargo-friction", type=float, default=cfg.BASELINE_PHYSICS["cargo_friction"],
        help="Cargo body's friction coefficient against the flatbed deck.",
    )
    parser.add_argument("--speed-bump-width", type=float, default=cfg.SPEED_BUMP_WIDTH)
    parser.add_argument("--start-x", type=float, default=cfg.TRUCK_START_X)
    parser.add_argument("--cargo-mass", type=float, default=cfg.FIXED_PHYSICS["cargo_mass"])
    parser.add_argument("--deck-friction", type=float, default=cfg.FIXED_PHYSICS["deck_friction"])
    parser.add_argument("--road-friction", type=float, default=cfg.FIXED_PHYSICS["road_friction"])
    parser.add_argument("--gravity-z", type=float, default=cfg.FIXED_PHYSICS["gravity_z"])
    # Edits that land partway through the clip, as
    # [{"frame": n, "params": {physics_key: new_value, ...}}]. Frames before n
    # are the source video; at frame n the params are written into the live
    # simulation and the run carries on from the state it had reached.
    parser.add_argument("--timed-edits-json", type=Path, default=None)
    return parser.parse_args()


# ------------------------------------------------------------------ geometry


def make_rounded_speed_bump(client: int, *, height: float, width: float) -> int:
    """Closed static mesh with a sine-profile rounded top, spanning the road."""
    segments = cfg.SPEED_BUMP_SEGMENTS
    y0, y1 = -cfg.ROAD_HALF_WIDTH, cfg.ROAD_HALF_WIDTH
    vertices: list[tuple[float, float, float]] = []
    for i in range(segments + 1):
        t = i / segments
        x = cfg.SPEED_BUMP_CENTER_X + (t - 0.5) * width
        z = float(height) * math.sin(math.pi * t)
        vertices.extend(((x, y0, z), (x, y1, z)))
    bottom_start = len(vertices)
    for i in range(segments + 1):
        t = i / segments
        x = cfg.SPEED_BUMP_CENTER_X + (t - 0.5) * width
        vertices.extend(((x, y0, -0.05), (x, y1, -0.05)))

    indices: list[int] = []
    for i in range(segments):
        a, b = 2 * i, 2 * i + 1
        c, d = 2 * (i + 1), 2 * (i + 1) + 1
        indices.extend((a, c, b, b, c, d))                       # curved skin
        ab, cb = bottom_start + a, bottom_start + c
        indices.extend((a, ab, c, c, ab, cb))                    # near wall
        bb, db = bottom_start + b, bottom_start + d
        indices.extend((b, d, bb, d, db, bb))                    # far wall
    lt0, lt1, lb0, lb1 = 0, 1, bottom_start, bottom_start + 1
    rt0, rt1 = 2 * segments, 2 * segments + 1
    rb0, rb1 = bottom_start + rt0, bottom_start + rt1
    indices.extend((lt0, lt1, lb0, lt1, lb1, lb0))                # end caps
    indices.extend((rt0, rb0, rt1, rt1, rb0, rb1))
    for i in range(segments):
        a, b = bottom_start + 2 * i, bottom_start + 2 * i + 1
        c, d = bottom_start + 2 * (i + 1), bottom_start + 2 * (i + 1) + 1
        indices.extend((a, b, c, b, d, c))                        # underside

    shape = p.createCollisionShape(
        p.GEOM_MESH, vertices=vertices, indices=indices, physicsClientId=client
    )
    bump_id = p.createMultiBody(
        baseMass=0.0, baseCollisionShapeIndex=shape, baseVisualShapeIndex=-1,
        basePosition=(0.0, 0.0, 0.0), physicsClientId=client,
    )
    p.changeDynamics(
        bump_id, -1, lateralFriction=0.92, restitution=0.02,
        collisionMargin=0.001, physicsClientId=client,
    )
    return bump_id


def make_chassis(client: int, *, mass: float, start_x: float) -> int:
    """Frame, cab and four wheels as one rigid (unsprung) body."""
    shape_types = [p.GEOM_BOX, p.GEOM_BOX]
    half_extents = [cfg.FRAME_HALF, cfg.CAB_HALF]
    radii = [0.0, 0.0]
    lengths = [0.0, 0.0]
    positions = [
        (0.0, 0.0, cfg.FRAME_Z - cfg.CHASSIS_COM_Z),
        (cfg.CAB_X, 0.0, cfg.CAB_Z - cfg.CHASSIS_COM_Z),
    ]
    orientations = [BED_ANCHOR_IDENTITY, BED_ANCHOR_IDENTITY]
    wheel_orientation = p.getQuaternionFromEuler((math.pi / 2.0, 0.0, 0.0))
    for x in cfg.WHEEL_XS:
        for y in cfg.WHEEL_YS:
            shape_types.append(p.GEOM_CYLINDER)
            half_extents.append((0.0, 0.0, 0.0))
            radii.append(cfg.WHEEL_RADIUS)
            lengths.append(cfg.WHEEL_WIDTH)
            positions.append((x, y, -cfg.CHASSIS_COM_Z))
            orientations.append(wheel_orientation)
    compound = p.createCollisionShapeArray(
        shapeTypes=shape_types, halfExtents=half_extents, radii=radii, lengths=lengths,
        collisionFramePositions=positions, collisionFrameOrientations=orientations,
        physicsClientId=client,
    )
    chassis = p.createMultiBody(
        baseMass=float(mass), baseCollisionShapeIndex=compound, baseVisualShapeIndex=-1,
        basePosition=(float(start_x), 0.0, cfg.WHEEL_RADIUS + cfg.CHASSIS_COM_Z),
        baseOrientation=BED_ANCHOR_IDENTITY, physicsClientId=client,
    )
    p.changeDynamics(
        chassis, -1, lateralFriction=cfg.WHEEL_ROAD_FRICTION, spinningFriction=0.01,
        rollingFriction=0.001,
        restitution=0.01, linearDamping=0.0,
        angularDamping=cfg.CHASSIS_ANGULAR_DAMPING,
        collisionMargin=0.001, physicsClientId=client,
    )
    return chassis


def make_bed(client: int, *, start_x: float, mass: float, friction: float) -> int:
    """The sprung flatbed deck, as a body of its own."""
    shape = p.createCollisionShape(
        p.GEOM_BOX, halfExtents=cfg.DECK_HALF, physicsClientId=client
    )
    bed = p.createMultiBody(
        baseMass=float(mass), baseCollisionShapeIndex=shape, baseVisualShapeIndex=-1,
        basePosition=(float(start_x) + cfg.DECK_CENTER_X, 0.0, cfg.WHEEL_RADIUS + cfg.DECK_Z),
        baseOrientation=BED_ANCHOR_IDENTITY, physicsClientId=client,
    )
    p.changeDynamics(
        bed, -1, lateralFriction=float(friction), spinningFriction=0.01,
        rollingFriction=0.001, restitution=0.06, linearDamping=0.0,
        angularDamping=0.08, collisionMargin=0.001, physicsClientId=client,
    )
    return bed


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _dot(a, b) -> float:
    return float(a[0] * b[0] + a[1] * b[1] + a[2] * b[2])


def make_bed_suspension(client: int, *, chassis: int, bed: int) -> int:
    """Prismatic joint that lets the deck travel vertically on the chassis.

    The joint carries no force of its own and, because PyBullet user
    constraints expose no joint index, no limits either: the spring-damper and
    the bump/droop stops are both applied explicitly every substep by
    :func:`apply_bed_suspension`. That keeps the whole suspension in the scene
    config where the numbers can be reasoned about, and it means the deck's
    travel is read from the two bodies' relative pose rather than from a joint
    state that does not exist.
    """
    return p.createConstraint(
        parentBodyUniqueId=chassis, parentLinkIndex=-1,
        childBodyUniqueId=bed, childLinkIndex=-1,
        jointType=p.JOINT_PRISMATIC, jointAxis=(0.0, 0.0, 1.0),
        parentFramePosition=BED_ANCHOR_LOCAL, childFramePosition=(0.0, 0.0, 0.0),
        parentFrameOrientation=BED_ANCHOR_IDENTITY,
        childFrameOrientation=BED_ANCHOR_IDENTITY,
        physicsClientId=client,
    )


BED_ANCHOR_Z_LOCAL = cfg.DECK_Z - cfg.CHASSIS_COM_Z


def bed_suspension_state(client: int, *, chassis: int, bed: int) -> tuple[float, float]:
    """Deck travel and travel rate, both in the chassis frame.

    Travel is zero when the deck sits at its design height; negative is
    compression, positive is droop.
    """
    cpos, cquat = p.getBasePositionAndOrientation(chassis, physicsClientId=client)
    bpos, _ = p.getBasePositionAndOrientation(bed, physicsClientId=client)
    inv_pos, inv_quat = p.invertTransform(cpos, cquat)
    local = p.multiplyTransforms(inv_pos, inv_quat, bpos, BED_ANCHOR_IDENTITY)[0]
    travel = float(local[2]) - BED_ANCHOR_Z_LOCAL

    clin, cang = p.getBaseVelocity(chassis, physicsClientId=client)
    blin, _ = p.getBaseVelocity(bed, physicsClientId=client)
    radius = tuple(bpos[i] - cpos[i] for i in range(3))
    dragged = tuple(clin[i] + _cross(cang, radius)[i] for i in range(3))
    relative = tuple(blin[i] - dragged[i] for i in range(3))
    up = p.multiplyTransforms((0.0, 0.0, 0.0), cquat, (0.0, 0.0, 1.0), BED_ANCHOR_IDENTITY)[0]
    return travel, _dot(relative, up)


def apply_bed_suspension(
    client: int, *, chassis: int, bed: int, gravity_z: float
) -> float:
    """Explicit spring-damper plus bump and droop stops for the deck.

    Returns the deck's travel so the caller can report it. The preload balances
    the deck's own weight at zero travel, so travel reads as pure suspension
    motion rather than static sag.
    """
    travel, rate = bed_suspension_state(client, chassis=chassis, bed=bed)
    static = cfg.BED_MASS * abs(float(gravity_z))
    force = static - cfg.SUSPENSION_STIFFNESS * travel - cfg.SUSPENSION_DAMPING * rate
    if travel < -cfg.SUSPENSION_TRAVEL_DOWN:
        overshoot = -cfg.SUSPENSION_TRAVEL_DOWN - travel
        force += cfg.STOP_STIFFNESS * overshoot + cfg.STOP_DAMPING * max(0.0, -rate)
    elif travel > cfg.SUSPENSION_TRAVEL_UP:
        overshoot = travel - cfg.SUSPENSION_TRAVEL_UP
        force -= cfg.STOP_STIFFNESS * overshoot + cfg.STOP_DAMPING * max(0.0, rate)
    # The suspension force is capped at a multiple of the deck's own weight.
    # Without the cap a hard strike makes the explicit stop spring overshoot
    # once and then diverge -- at a 0.16 m bump the deck's travel ran away to
    # tens of metres -- and a real bump stop cannot transmit unbounded force
    # anyway.
    lower = -cfg.SUSPENSION_FORCE_LIMIT_DOWN * static
    upper = cfg.SUSPENSION_FORCE_LIMIT_UP * static
    force = max(lower, min(upper, force))

    chassis_pos, chassis_quat = p.getBasePositionAndOrientation(chassis, physicsClientId=client)
    anchor = p.multiplyTransforms(
        chassis_pos, chassis_quat, BED_ANCHOR_LOCAL, BED_ANCHOR_IDENTITY
    )[0]
    p.applyExternalForce(bed, -1, (0.0, 0.0, force), anchor, p.WORLD_FRAME, physicsClientId=client)
    p.applyExternalForce(chassis, -1, (0.0, 0.0, -force), anchor, p.WORLD_FRAME, physicsClientId=client)
    return travel


def apply_drive_force(client: int, *, chassis: int, target_speed: float) -> float:
    """Cruise control, as a longitudinal force at the chassis centre of mass.

    Applied at the centre of mass on purpose: a force there cannot torque the
    chassis, so every bit of pitch the truck shows is the bump's doing. The
    earlier version of this wrote the target speed straight into the body's
    velocity, which discarded the contact impulse's linear half while keeping
    its angular half and stood the truck on its tail.
    """
    pos, _ = p.getBasePositionAndOrientation(chassis, physicsClientId=client)
    lin, _ = p.getBaseVelocity(chassis, physicsClientId=client)
    force = cfg.DRIVE_FORCE_GAIN * (float(target_speed) - float(lin[0]))
    force = max(-cfg.DRIVE_FORCE_MAX, min(cfg.DRIVE_FORCE_MAX, force))
    p.applyExternalForce(
        chassis, -1, (force, 0.0, 0.0), pos, p.WORLD_FRAME, physicsClientId=client
    )
    return force


def cargo_spawn(index: int, *, start_x: float) -> tuple[float, float, float]:
    half = cfg.CARGO_HALF_EXTENTS[index]
    return (
        float(start_x) + cfg.CARGO_LOCAL_XS[index],
        cfg.CARGO_LOCAL_YS[index],
        cfg.bed_rest_top_z() + half[2] + 0.003,
    )


def make_cargo(client: int, *, start_x: float, speed: float, mass: float, friction: float) -> list[int]:
    cargo_ids: list[int] = []
    for index, half in enumerate(cfg.CARGO_HALF_EXTENTS):
        shape = p.createCollisionShape(p.GEOM_BOX, halfExtents=half, physicsClientId=client)
        body = p.createMultiBody(
            baseMass=float(mass), baseCollisionShapeIndex=shape, baseVisualShapeIndex=-1,
            basePosition=cargo_spawn(index, start_x=start_x),
            baseOrientation=BED_ANCHOR_IDENTITY, physicsClientId=client,
        )
        p.resetBaseVelocity(body, linearVelocity=(float(speed), 0.0, 0.0), physicsClientId=client)
        p.changeDynamics(
            body, -1, lateralFriction=float(friction), spinningFriction=0.01,
            rollingFriction=0.001, restitution=0.06, linearDamping=0.01,
            angularDamping=0.08, collisionMargin=0.001, physicsClientId=client,
        )
        cargo_ids.append(body)
    return cargo_ids


# -------------------------------------------------------------- live editing

# getDynamicsInfo returns the four fields a timed edit can rewrite at fixed
# positions; naming them keeps the event log readable.
_DYNAMICS_FIELDS = {"mass": 0, "lateralFriction": 1, "restitution": 5}


def _live_value(client: int, body: int, field: str) -> float:
    info = p.getDynamicsInfo(body, -1, physicsClientId=client)
    return float(info[_DYNAMICS_FIELDS[field]])


def _body_snapshot(client: int, bodies: dict) -> dict:
    """The motion state a timed edit leaves untouched, for the event log.

    A physics-parameter edit changes one number and no velocities: recording
    both frames of the state is what shows the change came from the parameter
    and not from a scripted nudge.
    """
    chassis_pos, _ = p.getBasePositionAndOrientation(bodies["chassis"], physicsClientId=client)
    chassis_lin, _ = p.getBaseVelocity(bodies["chassis"], physicsClientId=client)
    cargo = []
    for body in bodies["cargo"]:
        if body is None:
            cargo.append(None)
            continue
        pos, _ = p.getBasePositionAndOrientation(body, physicsClientId=client)
        lin, _ = p.getBaseVelocity(body, physicsClientId=client)
        cargo.append({"location": list(pos), "linear_velocity": list(lin)})
    return {
        "chassis_location": list(chassis_pos),
        "chassis_linear_velocity": list(chassis_lin),
        "cargo": cargo,
    }


def apply_timed_params(
    client: int, params: dict, *, bodies: dict, state: dict,
    frame: int | None = None, time_sec: float | None = None,
) -> list[dict]:
    """Write one frame's worth of edited physics into the live simulation.

    ``state`` carries the two values the stepper owns rather than Bullet: the
    powered speed held on the chassis, and the current bump body. Anything this
    scene's vocabulary cannot produce raises, because an edit that is silently
    dropped renders as a video that looks like the baseline.

    Every applied parameter is reported as an event with the value on both
    sides of the write and the body state it did not touch, which is what makes
    a timed case auditable after the fact.
    """
    events: list[dict] = []
    for key, value in params.items():
        before_state = _body_snapshot(client, bodies)
        if key == "truck_speed":
            # The cruise target the drive force chases. The truck's velocity is
            # left alone: the force brings it down over the next few frames,
            # which is what a driver lifting off looks like.
            before = float(state["truck_speed"])
            state["truck_speed"] = float(value)
            after = float(state["truck_speed"])
        elif key == "cargo_friction":
            before = [_live_value(client, body, "lateralFriction") for body in bodies["cargo"]]
            timed.set_dynamics(p, client, bodies["cargo"], value, "lateralFriction")
            after = [_live_value(client, body, "lateralFriction") for body in bodies["cargo"]]
        elif key == "deck_friction":
            before = _live_value(client, bodies["bed"], "lateralFriction")
            timed.set_one(p, client, bodies["bed"], "lateralFriction", value)
            after = _live_value(client, bodies["bed"], "lateralFriction")
        elif key == "cargo_mass":
            before = [_live_value(client, body, "mass") for body in bodies["cargo"]]
            timed.set_dynamics(p, client, bodies["cargo"], value, "mass")
            after = [_live_value(client, body, "mass") for body in bodies["cargo"]]
        elif key == "speed_bump_height":
            before = float(state["bump_height"])
            p.removeBody(bodies["bump"], physicsClientId=client)
            bodies["bump"] = make_rounded_speed_bump(
                client, height=float(value), width=state["bump_width"]
            )
            state["bump_height"] = float(value)
            after = float(state["bump_height"])
        else:
            raise timed.unknown_param(key)
        events.append({
            "frame": frame,
            "time_sec": time_sec,
            "parameter": key,
            "from": before,
            "to": after,
            "state_before": before_state,
            "state_after": _body_snapshot(client, bodies),
        })
    return events



# ---------------------------------------------------------------- measurement


def _lowest_corner_in_frame(
    client: int, body: int, half, frame_pos, frame_quat, inv_pos, inv_quat
) -> float:
    """Local z of a carton's lowest corner, measured in a reference body.

    Two corrections matter and both are got wrong by the obvious shortcut of
    comparing world z against a horizontal deck plane:

    * a tumbling carton's lowest corner sits well below the plane through its
      centre -- up to ~0.1 m at the tilts this scene produces;
    * the deck is a rigid body, so when it pitches the deck tilts with it and a
      horizontal reference is simply the wrong surface.

    Expressing the corner in the deck's own frame fixes both at once: resting on
    the deck it reads ``DECK_HALF[2]`` whatever the truck is doing.
    """
    pos, quat = p.getBasePositionAndOrientation(body, physicsClientId=client)
    lowest = None
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            for sz in (-1.0, 1.0):
                world = p.multiplyTransforms(
                    pos, quat,
                    (sx * half[0], sy * half[1], sz * half[2]),
                    BED_ANCHOR_IDENTITY,
                )[0]
                local = p.multiplyTransforms(inv_pos, inv_quat, world, BED_ANCHOR_IDENTITY)[0]
                if lowest is None or local[2] < lowest:
                    lowest = float(local[2])
    return float(lowest)


# ------------------------------------------------------------------ simulate


def simulate(args: argparse.Namespace) -> dict:
    for name in ('fps','duration_sec','substeps','truck_speed','speed_bump_height','speed_bump_width','cargo_mass'):
        if not math.isfinite(getattr(args,name)) or getattr(args,name)<=0:raise ValueError(name+' must be positive and finite')
    for name in ('cargo_friction','deck_friction','road_friction'):
        if not math.isfinite(getattr(args,name)) or getattr(args,name)<0:raise ValueError(name+' must be nonnegative and finite')
    if not math.isfinite(args.start_x) or not math.isfinite(args.gravity_z):raise ValueError('Nonfinite initial position or gravity')
    fps = int(args.fps)
    frame_end = max(2, int(round(float(args.duration_sec) * fps)))
    substeps = int(args.substeps)
    dt = 1.0 / float(fps * substeps)

    truck_speed = float(args.truck_speed)
    bump_height = float(args.speed_bump_height)
    bump_width = float(args.speed_bump_width)
    cargo_friction = float(args.cargo_friction)
    if truck_speed <= 0:
        raise ValueError("--truck-speed must be positive.")
    if bump_height <= 0:
        raise ValueError("--speed-bump-height must be positive.")
    if bump_width <= 0:
        raise ValueError("--speed-bump-width must be positive.")
    if cargo_friction < 0:
        raise ValueError("--cargo-friction cannot be negative.")

    road_half_length = max(cfg.road_length_for(truck_speed,args.duration_sec),abs(float(args.start_x))+truck_speed*float(args.duration_sec)+12)

    client = p.connect(p.DIRECT)
    try:
        p.resetSimulation(physicsClientId=client)
        p.setGravity(0.0, 0.0, float(args.gravity_z), physicsClientId=client)
        p.setTimeStep(dt, physicsClientId=client)
        p.setPhysicsEngineParameter(
            fixedTimeStep=dt, numSolverIterations=300, numSubSteps=1,
            contactBreakingThreshold=0.0005, deterministicOverlappingPairs=1,
            enableConeFriction=1, physicsClientId=client,
        )

        road_shape = p.createCollisionShape(
            p.GEOM_BOX, halfExtents=(road_half_length, cfg.ROAD_HALF_WIDTH, 0.15),
            physicsClientId=client,
        )
        road = p.createMultiBody(
            baseMass=0.0, baseCollisionShapeIndex=road_shape, baseVisualShapeIndex=-1,
            basePosition=(0.0, 0.0, cfg.ROAD_SURFACE_Z - 0.15), physicsClientId=client,
        )
        p.changeDynamics(
            road, -1, lateralFriction=float(args.road_friction), restitution=0.01,
            collisionMargin=0.001, physicsClientId=client,
        )

        bump = make_rounded_speed_bump(client, height=bump_height, width=bump_width)
        chassis = make_chassis(client, mass=cfg.CHASSIS_MASS, start_x=float(args.start_x))
        bed = make_bed(client, start_x=float(args.start_x), mass=cfg.BED_MASS, friction=args.deck_friction)
        joint = make_bed_suspension(client, chassis=chassis, bed=bed)
        p.resetBaseVelocity(chassis, linearVelocity=(truck_speed, 0.0, 0.0), physicsClientId=client)
        p.resetBaseVelocity(bed, linearVelocity=(truck_speed, 0.0, 0.0), physicsClientId=client)
        cargo = make_cargo(
            client, start_x=float(args.start_x), speed=truck_speed,
            mass=float(args.cargo_mass), friction=cargo_friction,
        )

        bodies = {"chassis": chassis, "bed": bed, "cargo": cargo, "bump": bump, "joint": joint}
        state = {"truck_speed": truck_speed, "bump_height": bump_height, "bump_width": bump_width}

        spawn_z = [cargo_spawn(i, start_x=float(args.start_x))[2] for i in range(len(cargo))]
        max_cargo_z = list(spawn_z)
        max_clearance = [0.0 for _ in cargo]
        # How far each carton travels along the deck, in the deck's own frame.
        # This is the measure the friction control actually moves: the throw
        # itself is vertical and barely cares how grippy the deck is, but how
        # far a carton skids -- and whether it stays on board -- does.
        max_slide = [0.0 for _ in cargo]
        airborne_frames = [0 for _ in cargo]
        airborne_run = [0 for _ in cargo]
        airborne_run_max = [0 for _ in cargo]
        chassis_lift_max = 0.0
        travel_min, travel_max = 0.0, 0.0
        frames: list[dict] = []

        timed_edits = timed.load_timed_edits(args.timed_edits_json)
        timed.check_horizon(timed_edits, frame_end)
        timed_events: list[dict] = []

        for frame_index in range(1, frame_end + 1):
            if frame_index > 1:
                for _ in range(substeps):
                    travel = apply_bed_suspension(
                        client, chassis=chassis, bed=bed, gravity_z=float(args.gravity_z),
                    )
                    travel_min = min(travel_min, travel)
                    travel_max = max(travel_max, travel)
                    p.stepSimulation(physicsClientId=client)
                    apply_drive_force(
                        client, chassis=chassis, target_speed=state["truck_speed"]
                    )

            # The edit lands at the top of its frame: this frame is the first
            # one that shows it, every frame before it is the source video.
            if frame_index in timed_edits:
                timed_events.extend(apply_timed_params(
                    client, timed_edits[frame_index], bodies=bodies, state=state,
                    frame=frame_index, time_sec=(frame_index - 1) / float(fps),
                ))

            chassis_pos, chassis_quat = p.getBasePositionAndOrientation(chassis, physicsClientId=client)
            chassis_lin, chassis_ang = p.getBaseVelocity(chassis, physicsClientId=client)
            bed_pos, bed_quat = p.getBasePositionAndOrientation(bed, physicsClientId=client)
            bed_lin, bed_ang = p.getBaseVelocity(bed, physicsClientId=client)
            chassis_lift_max = max(
                chassis_lift_max,
                float(chassis_pos[2]) - cfg.WHEEL_RADIUS - cfg.CHASSIS_COM_Z,
            )
            inv_pos, inv_quat = p.invertTransform(bed_pos, bed_quat)

            cargo_records = []
            for index, body in enumerate(cargo):
                pos, quat = p.getBasePositionAndOrientation(body, physicsClientId=client)
                lin, ang = p.getBaseVelocity(body, physicsClientId=client)
                max_cargo_z[index] = max(max_cargo_z[index], float(pos[2]))
                # The deck is a rigid body, so "no contact while clear of the
                # deck surface" is an unambiguous airborne state. Cargo that has
                # already dropped to road level is not counted, because its
                # deck-relative clearance has gone negative.
                lowest_local = _lowest_corner_in_frame(
                    client, body, cfg.CARGO_HALF_EXTENTS[index],
                    bed_pos, bed_quat, inv_pos, inv_quat,
                )
                clearance = lowest_local - cfg.DECK_HALF[2]
                max_clearance[index] = max(max_clearance[index], clearance)
                touching_bed = bool(
                    p.getContactPoints(bodyA=body, bodyB=bed, physicsClientId=client)
                )
                airborne = (not touching_bed) and clearance > 0.02
                if airborne:
                    airborne_frames[index] += 1
                    airborne_run[index] += 1
                    airborne_run_max[index] = max(airborne_run_max[index], airborne_run[index])
                else:
                    airborne_run[index] = 0
                bed_local_x = float(
                    p.multiplyTransforms(
                        inv_pos, inv_quat, pos, BED_ANCHOR_IDENTITY
                    )[0][0]
                )
                max_slide[index] = max(
                    max_slide[index], abs(bed_local_x - (cfg.CARGO_LOCAL_XS[index] - cfg.DECK_CENTER_X))
                )
                cargo_records.append({
                    "location": list(pos),
                    "quaternion_xyzw": list(quat),
                    "linear_velocity": list(lin),
                    "angular_velocity": list(ang),
                    "airborne": bool(airborne),
                    "deck_clearance": clearance,
                    "bed_local_x": bed_local_x,
                })

            frames.append({
                "frame_index": frame_index,
                "time_sec": (frame_index - 1) / float(fps),
                "chassis": {
                    "location": list(chassis_pos),
                    "quaternion_xyzw": list(chassis_quat),
                    "linear_velocity": list(chassis_lin),
                    "angular_velocity": list(chassis_ang),
                },
                "bed": {
                    "location": list(bed_pos),
                    "quaternion_xyzw": list(bed_quat),
                    "linear_velocity": list(bed_lin),
                    "angular_velocity": list(bed_ang),
                    "suspension_travel": bed_suspension_state(
                        client, chassis=chassis, bed=bed
                    )[0],
                },
                "cargo": cargo_records,
            })

        # Cargo that ends the clip far below the deck is no longer on the truck:
        # it fell to the road, or was left behind by the time the clip stops.
        off_deck = [bool(rec["deck_clearance"] < -0.25) for rec in frames[-1]["cargo"]]

        parameters={key:getattr(args,key) for key in ('fps','duration_sec','substeps','truck_speed','speed_bump_height','speed_bump_width','start_x','cargo_mass','cargo_friction','deck_friction','road_friction','gravity_z')}
        parameters['timed_edits']=[dict(frame=frame,params=params) for frame,params in sorted(timed_edits.items())]
        return {
            "schema_version": CACHE_SCHEMA_VERSION,
            "scene": "flatbed_speed_bump",
            "simulation_parameters": parameters,
            "simulation_signature": signature(parameters),
            "simulator": "pybullet",
            "fps": fps,
            "frame_start": 1,
            "frame_end": frame_end,
            "duration_sec": float(args.duration_sec),
            "substeps_per_frame": substeps,
            "physics_dt": dt,
            "geometry": {
                "speed_bump_center_x": cfg.SPEED_BUMP_CENTER_X,
                "speed_bump_width": bump_width,
                "speed_bump_height": state["bump_height"],
                "wheel_radius": cfg.WHEEL_RADIUS,
                "wheelbase": cfg.WHEEL_XS[1] - cfg.WHEEL_XS[0],
                "deck_center_x": cfg.DECK_CENTER_X,
                "deck_half_extents": list(cfg.DECK_HALF),
                "deck_top_z": cfg.bed_rest_top_z(),
                "chassis_com_z": cfg.CHASSIS_COM_Z,
                "road_half_length": road_half_length,
            },
            "objects": {
                "flatbed_truck": {
                    "chassis_mass": cfg.CHASSIS_MASS,
                    "bed_mass": cfg.BED_MASS,
                    "initial_speed": truck_speed,
                    "initial_location": [float(args.start_x), 0.0, cfg.WHEEL_RADIUS + cfg.CHASSIS_COM_Z],
                },
                "cargo": [
                    {
                        "id": f"cargo_{i + 1}",
                        "half_extents": list(half),
                        "mass": float(args.cargo_mass),
                        "spawn_location": list(cargo_spawn(i, start_x=float(args.start_x))),
                    }
                    for i, half in enumerate(cfg.CARGO_HALF_EXTENTS)
                ],
            },
            "suspension": {
                "stiffness": cfg.SUSPENSION_STIFFNESS,
                "damping": cfg.SUSPENSION_DAMPING,
                "travel_down": cfg.SUSPENSION_TRAVEL_DOWN,
                "travel_up": cfg.SUSPENSION_TRAVEL_UP,
            },
            "physics_parameters": {
                "truck_speed": truck_speed,
                "speed_bump_height": bump_height,
                "cargo_friction": cargo_friction,
                "deck_friction": float(args.deck_friction),
                "road_friction": float(args.road_friction),
            },
            "timed_edits": [
                {"frame": frame, "params": params}
                for frame, params in sorted(timed_edits.items())
            ],
            # What each schedule entry did when it fired: the parameter on both
            # sides of the write, plus the body state the write left alone.
            "timed_events": timed_events,
            "quality": {
                "truck_final_x": float(frames[-1]["chassis"]["location"][0]),
                "chassis_max_lift": chassis_lift_max,
                "suspension_travel_min": travel_min,
                "suspension_travel_max": travel_max,
                "cargo_max_height": [float(v) for v in max_cargo_z],
                "cargo_max_deck_clearance": [float(v) for v in max_clearance],
                "cargo_max_slide": [float(v) for v in max_slide],
                "cargo_final_bed_local_x": [
                    float(rec["bed_local_x"]) for rec in frames[-1]["cargo"]
                ],
                "cargo_airborne_frames": airborne_frames,
                "cargo_longest_airborne_run": airborne_run_max,
                "cargo_off_deck_at_end": off_deck,
                "any_cargo_airborne": bool(any(c >= 2 for c in airborne_frames)),
                "any_cargo_left_truck": bool(any(off_deck)),
                "visible": bool(max(max_clearance) >= 0.06),
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
        f"[simulate] speed={result['physics_parameters']['truck_speed']:.2f}m/s "
        f"bump={result['physics_parameters']['speed_bump_height']:.3f}m "
        f"mu={result['physics_parameters']['cargo_friction']:.2f} | "
        f"lift={q['chassis_max_lift']:.3f} "
        f"travel=[{q['suspension_travel_min']:+.3f},{q['suspension_travel_max']:+.3f}] "
        f"clearance={[round(v, 3) for v in q['cargo_max_deck_clearance']]} "
        f"airborne={q['cargo_airborne_frames']} off_deck={q['cargo_off_deck_at_end']}"
    )


if __name__ == "__main__":
    main()

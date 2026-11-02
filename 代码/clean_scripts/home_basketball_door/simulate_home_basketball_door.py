"""PyBullet trajectory for a basketball thrown at a half-open door.

Two rigid bodies and one hinge:

* the **ball** is a sphere launched from ``ball_start_xyz`` at ``ball_speed``
  along the line to a contact point on the door leaf, with a first-order
  gravity lead so that the throw actually arrives where it was aimed;
* the **door** is a slab on a vertical revolute joint, hinged on the jamb, so
  gravity exerts no torque on it -- it swings only because the ball pushed it,
  and it stops only because the hinge takes energy out. That is what makes
  ``door_hinge_damping`` the interesting knob in this scene;
* the **room** is four static walls with the door aperture cut through one of
  them. They are not decoration: without them the ball rolls through the wall
  and settles inside the wardrobe fitted behind it.

Metres, kilograms, seconds, +Z up. Simulation coordinates put the origin on
the floor at the hinge, XY parallel to world XY; closed_yaw_deg gives the
closed leaf's direction. The ball is
thrown from inside the room, so it can only push the leaf towards closed: the
clip is a door being slammed shut, not swung open.

Run standalone (the renderer normally writes ``door_leaf.json`` first):
    .runtime/sim/python.exe scripts/home_basketball_door/simulate_home_basketball_door.py \
        --out renders/home_basketball_door/physics_transforms.json
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
import math
import sys
from pathlib import Path
from typing import Any

import pybullet as p

HERE = Path(__file__).resolve().parent
from scene_support.home_basketball_door import scenario_io  # noqa: E402

FLOOR_HALF_EXTENT = 6.0
FLOOR_THICKNESS = 0.1
LEAF_NAME = 'door_leaf.json'

# Physics keys a timed edit may rewrite. Everything else (the throw geometry,
# the door's start angle, the ball's radius) is baked in when the body is
# created, so changing it mid-clip would be an edit that renders as nothing.
LIVE_FIELDS = {
    'door_mass': ('body', 0, 'mass', 'door mass'),
    'door_hinge_damping': ('body', 0, 'jointDamping', 'hinge damping'),
    'ball_mass': ('body', -1, 'mass', 'ball mass'),
    'ball_restitution': ('body', -1, 'restitution', 'restitution'),
    'ball_friction': ('body', -1, 'lateralFriction', 'lateral friction'),
}
# Hinge friction is not a PyBullet parameter in this build, so it is applied as
# a scripted resisting torque and kept in a dict the substep loop reads.
SCRIPTED_FIELDS = {'door_hinge_friction'}

# Where the value a timed edit rewrites can be read back from, so the event log
# records both sides of the write: field -> (kind, index into the engine's info
# tuple). getDynamicsInfo is (mass, lateralFriction, ..., restitution, ...);
# getJointInfo is (index, name, type, ..., jointDamping, ...).
_TIMED_READBACK = {'mass': ('dynamics', 0), 'lateralFriction': ('dynamics', 1),
                   'restitution': ('dynamics', 5), 'jointDamping': ('joint', 6)}


def live_value(physics_client: int, body: int, link: int, field: str):
    kind, index = _TIMED_READBACK[field]
    if kind == 'joint':
        return float(p.getJointInfo(body, 0, physicsClientId=physics_client)[index])
    return float(p.getDynamicsInfo(body, link, physicsClientId=physics_client)[index])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--scenario', type=Path, default=None)
    parser.add_argument('--scenario-overrides-json', type=Path, default=None)
    parser.add_argument('--door-leaf-json', type=Path, default=None)
    parser.add_argument('--fps', type=int, default=None)
    parser.add_argument('--duration-sec', type=float, default=None)
    parser.add_argument('--substeps', type=int, default=None)
    return parser.parse_args()


# ------------------------------------------------------------------- geometry


def load_leaf(path: Path | None, physics: dict[str, Any]) -> dict[str, Any]:
    """Door dimensions, measured off the room mesh by the renderer.

    Falls back to the scenario's own numbers so the simulator runs without
    Blender; the fallback is not a guess, it is the same measurement rounded.
    """
    if path is not None and Path(path).is_file():
        payload = scenario_io.read_json(Path(path))
        payload['leaf_source'] = str(Path(path).resolve())
        return payload
    return {
        'width_m': float(physics.get('door_width_m', 0.947)),
        'height_m': float(physics['door_height_m']),
        'thickness_m': float(physics['door_thickness_m']),
        'leaf_source': 'scenario fallback (no door_leaf.json)',
    }


def leaf_direction(angle: float) -> tuple[float, float]:
    """Unit vector of the closed->open leaf, in the ground plane.

    ``angle`` is measured from the closed leaf, which lies along +X; opening
    rotates it towards +Y, i.e. into the room. That is the direction the ball
    pushes it: the ball arrives from the room, hits the room-facing side of the
    leaf and drives it towards the jamb, so the clip's action is a door being
    knocked shut rather than deeper into a wall that the asset does not model.
    """
    return math.cos(angle), math.sin(angle)


def launch(
    physics: dict[str, Any], leaf: dict[str, Any], angle: float
) -> tuple[list[float], list[float], list[float]]:
    """Start point, launch velocity and the contact point the throw is aimed at.

    ``angle`` is the leaf's opening angle in radians. The aim point is given as
    a fraction of the leaf width and an absolute height, so it rides with the
    door: edit the door's opening angle and the ball still arrives at the same
    spot on the leaf. The vertical component gets a first-order gravity lead
    (``0.5 g t`` at the flight time) so a throw of any speed lands on that spot
    rather than below it.
    """
    start = [float(v) for v in physics['ball_start_xyz']]
    ux, uy = leaf_direction(angle + math.radians(float(leaf.get('closed_yaw_deg', 0))))
    reach = float(physics['ball_aim_width_frac']) * float(leaf['width_m'])
    aim = [ux * reach, uy * reach, float(physics['ball_aim_z_m'])]

    delta = [aim[i] - start[i] for i in range(3)]
    distance = math.sqrt(sum(d * d for d in delta))
    speed = float(physics['ball_speed'])
    if distance <= 0.0:
        raise ValueError('ball_start_xyz is on the aim point')
    direction = [d / distance for d in delta]
    flight = distance / speed
    velocity = [
        direction[0] * speed,
        direction[1] * speed,
        direction[2] * speed + 0.5 * abs(float(physics['gravity_z'])) * flight,
    ]
    return start, velocity, aim


# ------------------------------------------------------------------- dynamics


def motion_state(physics_client: int, bodies: dict[str, int]) -> dict[str, Any]:
    """Door angle and rate plus the ball's pose, for the event log."""
    angle, rate = p.getJointState(bodies['door'], 0, physicsClientId=physics_client)[:2]
    position, _ = p.getBasePositionAndOrientation(bodies['ball'], physicsClientId=physics_client)
    linear, angular = p.getBaseVelocity(bodies['ball'], physicsClientId=physics_client)
    return {'door_angle_deg': math.degrees(float(angle)),
            'door_angular_velocity': float(rate),
            'ball_location': list(position),
            'ball_linear_velocity': list(linear),
            'ball_angular_velocity': list(angular)}


def apply_live_params(
    physics_client: int,
    bodies: dict[str, int],
    params: dict[str, Any],
    scripted: dict[str, float],
    *,
    frame: int | None = None,
    time_sec: float | None = None,
) -> list[dict[str, Any]]:
    """Write one frame's edited physics into the running simulation.

    Every write is reported with the value on both sides of it and the motion
    state it did not touch -- a parameter edit changes one number and no
    velocities, and recording both is what shows that.
    """
    events: list[dict[str, Any]] = []
    for key, value in params.items():
        before_state = motion_state(physics_client, bodies)
        if key in SCRIPTED_FIELDS:
            before = float(scripted[key])
            scripted[key] = float(value)
            after = float(scripted[key])
        else:
            if key not in LIVE_FIELDS:
                raise ValueError(
                    f'timed edit cannot write {key!r}; this scene accepts '
                    f'{sorted(LIVE_FIELDS | SCRIPTED_FIELDS)}'
                )
            _, link, field, _ = LIVE_FIELDS[key]
            body = bodies['door'] if key.startswith('door') else bodies['ball']
            before = live_value(physics_client, body, link, field)
            p.changeDynamics(body, link, physicsClientId=physics_client, **{field: float(value)})
            after = live_value(physics_client, body, link, field)
        events.append({'frame': frame, 'time_sec': time_sec, 'parameter': key,
                       'from': before, 'to': after,
                       'state_before': before_state,
                       'state_after': motion_state(physics_client, bodies)})
    return events


def apply_hinge_friction(physics_client: int, door: int, torque: float) -> None:
    """Coulomb friction in the hinge, as a resisting torque about its axis.

    PyBullet's changeDynamics in this build has no ``jointFriction``, and plain
    ``jointDamping`` is viscous: it leaves a door coasting for tens of seconds
    (measured time constant I/b = 49 s at the value this scene started with)
    and, worse, makes the swing angle *independent of the door's mass* --
    the inertia cancels between the impulse and the decay. A constant
    resisting torque is both what a hinge actually does and what decouples the
    knobs: the leaf stops dead, and how far it gets before it stops is
    proportional to its kinetic energy, so ball mass, ball speed and door mass
    all change it.

    The axis is world +Z, which is the direction a positive joint angle turns,
    so the braking torque is -Z for a leaf that is opening.
    """
    if torque <= 0.0:
        return
    rate = p.getJointState(door, 0, physicsClientId=physics_client)[1]
    if abs(rate) < 1e-4:
        return
    p.applyExternalTorque(
        door, 0, torqueObj=(0.0, 0.0, -torque if rate > 0.0 else torque),
        flags=p.WORLD_FRAME, physicsClientId=physics_client,
    )


def simulate(
    scenario: dict[str, Any],
    *,
    fps: int,
    duration_sec: float,
    substeps: int,
    leaf_path: Path | None,
) -> dict[str, Any]:
    physics = scenario['physics']
    # Validate direct JSON schedules before creating or stepping any bodies.
    for entry in physics.get('timed_edits') or []:
        if 'ball_speed' in entry['params']:
            raise ValueError(
                "'ball_speed' is a starting condition and cannot be timed. "
                "Set physics.ball_speed outside timed_edits to apply it from frame 1."
            )
    layout = scenario['layout']

    fps = int(fps)
    frame_end = max(2, int(round(float(duration_sec) * fps)))
    substeps = max(1, int(substeps))
    dt = 1.0 / (fps * substeps)
    contact_stride = max(1, substeps // 10)

    leaf = load_leaf(leaf_path, physics)
    width = float(leaf['width_m'])
    height = float(leaf['height_m'])
    thickness = float(leaf['thickness_m'])
    closed_yaw = math.radians(float(leaf.get('closed_yaw_deg', 0)))
    bottom = float(leaf.get('bottom_clearance_m', 0))
    front_hinge = bool(leaf.get('hinge_front_edge', False))
    slab_y = -thickness / 2 if front_hinge else 0.0
    door_mass = float(physics['door_mass'])
    ball_mass = float(physics['ball_mass'])
    radius = float(physics['ball_radius_m'])
    start_angle = math.radians(float(physics['door_start_angle_deg']))
    closed_limit = math.radians(float(physics['door_closed_limit_deg']))
    open_limit = math.radians(float(physics['door_open_limit_deg']))
    if door_mass <= 0.0 or ball_mass <= 0.0:
        raise ValueError('door_mass and ball_mass must be positive')
    if open_limit <= start_angle:
        raise ValueError('door_open_limit_deg must be past door_start_angle_deg')
    if float(physics['door_hinge_friction']) < 0.0:
        raise ValueError('door_hinge_friction must be non-negative')

    start, velocity, aim = launch(physics, leaf, start_angle)

    client = p.connect(p.DIRECT)
    try:
        p.resetSimulation(physicsClientId=client)
        p.setGravity(0.0, 0.0, float(physics['gravity_z']), physicsClientId=client)
        p.setTimeStep(dt, physicsClientId=client)
        p.setPhysicsEngineParameter(
            fixedTimeStep=dt,
            numSolverIterations=int(physics['solver_iterations']),
            numSubSteps=1,
            # The ball and the leaf are both thin against the solver's default
            # margin, and a 4 mm margin would hold the two apart for a frame or
            # two at the moment of contact. It costs a little solver noise to
            # tighten it, which is why the solver iterations are high.
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
            0.0, floor_shape, -1, (0.0, 0.0, -FLOOR_THICKNESS / 2), physicsClientId=client
        )
        p.changeDynamics(
            floor,
            -1,
            lateralFriction=float(physics['floor_friction']),
            restitution=float(physics['floor_restitution']),
            rollingFriction=0.0005,
            spinningFriction=0.0003,
            physicsClientId=client,
        )

        # The room. Four walls, with the door aperture cut through the -Y one.
        # They matter: without them the ball rolls straight through the wall
        # and comes to rest inside the wardrobe fitted behind it -- measured at
        # x = -2.91, half a metre past the wall plane of -2.81.
        #
        # The -Y wall is thick enough to be a jamb (door_jamb_depth_m) and the
        # leaf hangs inside that thickness, which is why the door plane sits
        # 0.15 m behind the room's own wall face. That recess is measured off
        # the room asset, not invented: layout.room_bounds is the interior of
        # the bedroom as the GLB places it.
        bounds = layout['room_bounds']
        hinge_world = leaf.get('hinge_world') or [0.0, 0.0, 0.0]
        hinge_x, hinge_y = float(hinge_world[0]), float(hinge_world[1])
        x_lo = float(bounds['x'][0]) - hinge_x
        x_hi = float(bounds['x'][1]) - hinge_x
        y_lo = float(bounds['y'][0]) - hinge_y
        y_hi = float(bounds['y'][1]) - hinge_y
        ceiling = float(bounds['ceiling_m'])
        wall_t = float(physics['wall_thickness_m'])
        depth = float(physics['door_jamb_depth_m'])
        span_x = (x_hi - x_lo) / 2.0
        span_y = (y_hi - y_lo) / 2.0

        static_walls = []
        def wall(half_extents, centre, yaw=0.0):
            shape = p.createCollisionShape(
                p.GEOM_BOX, halfExtents=half_extents, physicsClientId=client
            )
            body = p.createMultiBody(0.0, shape, -1, centre,
                p.getQuaternionFromEuler((0, 0, yaw)), physicsClientId=client)
            static_walls.append(body)
            p.changeDynamics(
                body,
                -1,
                lateralFriction=float(physics['wall_friction']),
                restitution=float(physics['wall_restitution']),
                physicsClientId=client,
            )
            return body

        # Side walls and the wall behind the camera.
        wall((wall_t / 2, span_y + wall_t, ceiling / 2), (x_lo - wall_t / 2, (y_lo + y_hi) / 2, ceiling / 2))
        wall((wall_t / 2, span_y + wall_t, ceiling / 2), (x_hi + wall_t / 2, (y_lo + y_hi) / 2, ceiling / 2))
        wall((span_x + wall_t, wall_t / 2, ceiling / 2), ((x_lo + x_hi) / 2, y_hi + wall_t / 2, ceiling / 2))
        # The door wall: a pier either side of the aperture, and a header over it.
        # The aperture is one leaf-thickness wider than the leaf on each side:
        # flush jambs would put the leaf's own corner 1.6 cm inside the pier at
        # 45 deg, and a body that starts the clip interpenetrating a wall gets
        # ejected -- measured, that threw the ball out of the room at 10.7 m/s.
        clear = float(leaf.get('side_clearance_m', thickness))
        if front_hinge:
            ux, uy = math.cos(closed_yaw), math.sin(closed_yaw)
            nx, ny = -uy, ux
            panel_left, panel_right = leaf['wall_panel_world_x']
            local_left = (panel_left - hinge_x) / ux
            local_right = (panel_right - hinge_x) / ux
            front_y = float(leaf['wall_front_offset_from_hinge_m'])
            door_depth = float(leaf['wall_depth_m'])
            def panel(a, b, z0, z1):
                cx, cy = (a+b)/2, front_y-door_depth/2
                wall(((b-a)/2, door_depth/2, (z1-z0)/2),
                     (ux*cx+nx*cy, uy*cx+ny*cy, (z0+z1)/2), closed_yaw)
            panel(local_left, -clear, 0, ceiling)
            panel(width+clear, local_right, 0, ceiling)
            panel(-clear, width+clear, bottom+height+clear, ceiling)
            skirt = layout.get('hallway') or {}
            skirt_depth = float(skirt.get('skirt_proud_m', .035))
            skirt_height = float(skirt.get('skirt_height_m', .152))
            for a, b in ((local_left, -clear), (width+clear, local_right)):
                cx, cy = (a+b)/2, front_y+skirt_depth/2
                wall(((b-a)/2, skirt_depth/2, skirt_height/2),
                     (ux*cx+nx*cy, uy*cx+ny*cy, skirt_height/2), closed_yaw)
            # Straight wall sections adjoining the measured diagonal panel.
            wall(((panel_left-hinge_x-x_lo)/2, wall_t/2, ceiling/2),
                 ((x_lo+panel_left-hinge_x)/2, y_lo-wall_t/2, ceiling/2))
            right_world = leaf['opening_right_world']
            panel_right_y = right_world[1] + (panel_right-right_world[0])*uy/ux - hinge_y
            wall(((x_hi-panel_right+hinge_x)/2, wall_t/2, ceiling/2),
                 ((panel_right-hinge_x+x_hi)/2, panel_right_y-wall_t/2, ceiling/2))
        else:
            wall((abs(x_lo + clear) / 2, depth / 2, ceiling / 2),
                 ((x_lo - clear) / 2, y_lo - depth / 2, ceiling / 2))
            wall((abs(x_hi - width - clear) / 2, depth / 2, ceiling / 2),
                 ((x_hi + width + clear) / 2, y_lo - depth / 2, ceiling / 2))
            wall((width / 2 + clear, depth / 2, (ceiling - height - clear) / 2),
                 (width / 2, y_lo - depth / 2, height + clear + (ceiling - height - clear) / 2))

        # The slab is offset from the link frame, and the link frame sits on the
        # hinge line. PyBullet puts a link's revolute joint at the link frame
        # origin, so a slab modelled about its own centre would swing about its
        # centre -- a revolving door -- and a ball aimed at the leaf would sail
        # straight past the 0.86 m aperture the closed leaf covers. The inertia
        # frame goes with the shape, so the mass still sits where the leaf is.
        slab = p.createCollisionShape(
            p.GEOM_BOX,
            halfExtents=(width / 2, thickness / 2, height / 2),
            collisionFramePosition=[width / 2, slab_y, bottom + height / 2],
            physicsClientId=client,
        )
        door = p.createMultiBody(
            baseMass=0.0,
            baseCollisionShapeIndex=-1,
            basePosition=(0.0, 0.0, 0.0),
            linkMasses=[door_mass],
            linkCollisionShapeIndices=[slab],
            linkVisualShapeIndices=[-1],
            linkPositions=[[0.0, 0.0, 0.0]],
            linkOrientations=[p.getQuaternionFromEuler((0, 0, closed_yaw))],
            linkInertialFramePositions=[[width / 2, slab_y, bottom + height / 2]],
            linkInertialFrameOrientations=[[0.0, 0.0, 0.0, 1.0]],
            linkParentIndices=[0],
            linkJointTypes=[p.JOINT_REVOLUTE],
            # Axis +Z, so a positive joint angle is "further open" towards the
            # room: the leaf is along +X when closed and rotates towards +Y.
            linkJointAxis=[[0.0, 0.0, 1.0]],
            physicsClientId=client,
        )
        p.changeDynamics(
            door,
            0,
            lateralFriction=0.4,
            # Left at 1.0, as the floor is in pot_lid_drop: PyBullet multiplies
            # the two restitutions of a contact, so anything below 1 here
            # quietly overrides the ball's own 0.75 and the rebound dies.
            restitution=1.0,
            jointDamping=float(physics['door_hinge_damping']),
            jointLowerLimit=closed_limit,
            jointUpperLimit=open_limit,
            physicsClientId=client,
        )
        # A joint made by createMultiBody arrives with a velocity motor that
        # holds it at zero speed, and it wins: the hinge behaves as if it were
        # welded, so a ball bounced off the leaf leaves the door at exactly its
        # start angle (measured: 50.00 deg before and after the hit). Setting
        # the motor's force to zero is what makes the hinge passive. Nothing
        # else in the scene moves as silently for the same reason.
        p.setJointMotorControl2(
            door, 0, p.VELOCITY_CONTROL, targetVelocity=0.0, force=0.0, physicsClientId=client
        )
        p.resetJointState(door, 0, start_angle, 0.0, physicsClientId=client)

        ball_shape = p.createCollisionShape(
            p.GEOM_SPHERE, radius=radius, physicsClientId=client
        )
        ball = p.createMultiBody(
            baseMass=ball_mass,
            baseCollisionShapeIndex=ball_shape,
            baseVisualShapeIndex=-1,
            basePosition=start,
            physicsClientId=client,
        )
        p.changeDynamics(
            ball,
            -1,
            lateralFriction=float(physics['ball_friction']),
            rollingFriction=float(physics['ball_rolling_friction']),
            spinningFriction=float(physics['ball_spinning_friction']),
            restitution=float(physics['ball_restitution']),
            linearDamping=float(physics['ball_linear_damping']),
            angularDamping=float(physics['ball_angular_damping']),
            physicsClientId=client,
        )
        p.resetBaseVelocity(ball, linearVelocity=velocity, physicsClientId=client)

        timed_edits = {
            int(entry['frame']): dict(entry['params'])
            for entry in (physics.get('timed_edits') or [])
        }
        for frame in timed_edits:
            if not 1 <= frame <= frame_end:
                raise ValueError(f'timed edit at frame {frame} is outside the clip (1..{frame_end})')

        frames: list[dict[str, Any]] = []
        impact_frame: int | None = None
        scripted = {'door_hinge_friction': float(physics['door_hinge_friction'])}
        timed_events: list[dict[str, Any]] = []
        for frame_index in range(1, frame_end + 1):
            bounced = False
            if frame_index > 1:
                for step in range(substeps):
                    apply_hinge_friction(
                        client, door, scripted['door_hinge_friction']
                    )
                    p.stepSimulation(physicsClientId=client)
                    # The hit is a one- or two-substep event, so it is looked
                    # for on every substep until it has been found; after that
                    # the per-frame contact flag is enough.
                    if impact_frame is None or not step % contact_stride:
                        if p.getContactPoints(ball, door, -1, 0, physicsClientId=client):
                            bounced = True
                            if impact_frame is None:
                                impact_frame = frame_index

            if frame_index in timed_edits:
                timed_events.extend(apply_live_params(
                    client,
                    {'door': door, 'ball': ball},
                    timed_edits[frame_index],
                    scripted,
                    frame=frame_index,
                    time_sec=(frame_index - 1) / float(fps),
                ))

            angle, angle_rate = p.getJointState(door, 0, physicsClientId=client)[:2]
            position, quaternion = p.getBasePositionAndOrientation(ball, physicsClientId=client)
            linear, angular = p.getBaseVelocity(ball, physicsClientId=client)
            link = p.getLinkState(door, 0, physicsClientId=client)

            frames.append(
                {
                    'frame_index': frame_index,
                    'time_sec': (frame_index - 1) / float(fps),
                    'door_angle_rad': float(angle),
                    'door_world_yaw_rad': float(closed_yaw + angle),
                    'door_angular_velocity': float(angle_rate),
                    'door_link_position': list(link[4]),
                    'ball_location': list(position),
                    'ball_quaternion_xyzw': list(quaternion),
                    'ball_linear_velocity': list(linear),
                    'ball_angular_velocity': list(angular),
                    'ball_contacting_door': bounced,
                }
            )

        quality = measure(
            frames,
            fps=fps,
            impact_frame=impact_frame,
            closed_limit_deg=float(physics['door_closed_limit_deg']),
            open_limit_deg=float(physics['door_open_limit_deg']),
            start=start,
            aim=aim,
        )
        return {
            'schema_version': 1,
            'simulator': 'pybullet',
            'fps': fps,
            'frame_start': 1,
            'frame_end': frame_end,
            'duration_sec': float(duration_sec),
            'substeps_per_frame': substeps,
            'physics_dt': dt,
            'coordinate_system': (
                'simulation coordinates, +Z up, origin on the floor at the door hinge, '
                'XY parallel to world XY; door angle relative to geometry.leaf.closed_yaw_deg'
            ),
            'geometry': {
                'leaf': leaf,
                'door_width_m': width,
                'door_height_m': height,
                'door_thickness_m': thickness,
                'door_start_angle_deg': float(physics['door_start_angle_deg']),
                'door_open_limit_deg': float(physics['door_open_limit_deg']),
                'ball_radius_m': radius,
                'ball_start': start,
                'ball_velocity': velocity,
                'ball_aim': aim,
            },
            'physics': {k: v for k, v in physics.items() if k != 'timed_edits'},
            'timed_edits': [
                {'frame': frame, 'params': params}
                for frame, params in sorted(timed_edits.items())
            ],
            # What each schedule entry did when it fired: the value on both
            # sides of the write plus the motion state it left alone.
            'timed_events': timed_events,
            'quality': quality,
            'frames': frames,
        }
    finally:
        p.disconnect(client)


def measure(
    frames: list[dict[str, Any]],
    *,
    fps: int,
    impact_frame: int | None,
    closed_limit_deg: float,
    open_limit_deg: float,
    start: list[float],
    aim: list[float],
) -> dict[str, Any]:
    """The numbers the README quotes, read off the trajectory itself."""
    angles = [math.degrees(f['door_angle_rad']) for f in frames]
    rates = [abs(f['door_angular_velocity']) for f in frames]
    speeds = [math.dist(f['ball_linear_velocity'], (0.0, 0.0, 0.0)) for f in frames]

    # The door has stopped once it stays within half a degree of where it ends.
    # A single frame at the end value is a solver overshoot, not a stop, so the
    # whole tail has to agree.
    stop_frame = None
    final_angle = angles[-1]
    for index in range(len(angles)):
        if all(abs(a - final_angle) < 0.5 for a in angles[index:]):
            stop_frame = frames[index]['frame_index']
            break

    # Settle: the tail of the clip stays under a hair of motion, for both
    # bodies at once.
    quiet_speed, quiet_spin, quiet_need = 0.06, 0.15, int(0.25 * fps)
    settle_frame = None
    streak = 0
    for record in reversed(frames):
        linear = math.dist(record['ball_linear_velocity'], (0.0, 0.0, 0.0))
        spin = math.dist(record['ball_angular_velocity'], (0.0, 0.0, 0.0))
        door_rates = abs(record['door_angular_velocity'])
        if linear < quiet_speed and spin < quiet_spin and door_rates < 0.05:
            streak += 1
            if streak >= quiet_need:
                settle_frame = frames[-streak]['frame_index']
        else:
            break

    path = 0.0
    for previous, current in zip(frames, frames[1:]):
        path += math.dist(previous['ball_location'], current['ball_location'])

    before = speeds[impact_frame - 2] if impact_frame and impact_frame >= 2 else None
    after = speeds[min(impact_frame, len(speeds)-1)] if impact_frame else None
    final = frames[-1]['ball_location']
    return {
        'impact_frame': impact_frame,
        'door_angle_start_deg': round(angles[0], 2),
        'door_angle_end_deg': round(angles[-1], 2),
        'door_angle_max_deg': round(max(angles), 2),
        'door_angle_min_deg': round(min(angles), 2),
        'door_travel_deg': round(abs(angles[-1] - angles[0]), 2),
        'door_peak_rate_rad_s': round(max(rates), 3),
        'door_stop_frame': stop_frame,
        'door_rebound_deg': round(abs(max(angles) - angles[-1]) + abs(min(angles) - angles[-1]), 2),
        'door_at_closed_limit': abs(angles[-1] - closed_limit_deg) < 1.0,
        'door_at_open_limit': abs(angles[-1] - open_limit_deg) < 1.0,
        'ball_speed_before_m_s': round(before, 3) if before is not None else None,
        'ball_speed_after_m_s': round(after, 3) if after is not None else None,
        'ball_path_m': round(path, 3),
        'ball_final_xyz': [round(v, 3) for v in final],
        'ball_aim_xyz': [round(v, 3) for v in aim],
        'ball_start_xyz': [round(v, 3) for v in start],
        'settle_frame': settle_frame,
        'final_ball_speed_m_s': round(speeds[-1], 3),
        'final_door_rate_rad_s': round(rates[-1], 4),
    }


def main() -> None:
    args = parse_args()
    scenario = scenario_io.load_scenario(args.scenario, args.scenario_overrides_json)
    physics = scenario['physics']

    leaf_path = args.door_leaf_json or args.out.parent / LEAF_NAME
    records = simulate(
        scenario,
        fps=int(args.fps if args.fps is not None else physics['fps']),
        duration_sec=float(
            args.duration_sec if args.duration_sec is not None else physics['duration_sec']
        ),
        substeps=int(args.substeps if args.substeps is not None else physics['substeps_per_frame']),
        leaf_path=leaf_path,
    )
    scenario_io.write_json(args.out, records)

    quality = records['quality']
    print(f"frames 1..{records['frame_end']} @ {records['fps']} fps")
    print(f"impact frame: {quality['impact_frame']}")
    print(f"door: {quality['door_angle_start_deg']} -> {quality['door_angle_end_deg']} deg "
          f"(travel {quality['door_travel_deg']} deg), stop frame {quality['door_stop_frame']}, "
          f"at closed limit: {quality['door_at_closed_limit']}")
    print(f"door peak rate: {quality['door_peak_rate_rad_s']} rad/s")
    print(f"ball: {quality['ball_speed_before_m_s']} -> {quality['ball_speed_after_m_s']} m/s, "
          f"path {quality['ball_path_m']} m, final {quality['ball_final_xyz']}")
    print(f"settle frame: {quality['settle_frame']}")
    if not leaf_path.is_file():
        print(f'[warning] {leaf_path.name} missing: used the scenario fallback dimensions')


if __name__ == '__main__':
    main()

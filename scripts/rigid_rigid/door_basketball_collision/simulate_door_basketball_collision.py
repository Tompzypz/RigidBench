"""Passive hinged door strikes an initially stationary basketball; SI units."""
# PCVE_UNIFIED_ENTRY_BEGIN
from __future__ import annotations

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
import math
import sys
from pathlib import Path
from typing import Any

import pybullet as p

HERE = Path(__file__).resolve().parent
import scene_config  # noqa: E402

FLOOR_HALF_EXTENT = 6.0
FLOOR_THICKNESS = 0.1
LEAF_NAME = 'door_leaf.json'
import pcve_timed_edits as timed

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--scenario', type=Path, default=None)
    parser.add_argument('--scenario-overrides-json', type=Path, default=None)
    parser.add_argument('--door-leaf-json', type=Path, default=None)
    parser.add_argument('--fps', type=int, default=None)
    parser.add_argument('--duration-sec', type=float, default=None)
    parser.add_argument('--substeps', type=int, default=None)
    scene_config.add_parameter_arguments(parser)
    return parser.parse_args()


# ------------------------------------------------------------------- geometry


def load_leaf(path: Path | None, physics: dict[str, Any]) -> dict[str, Any]:
    """Require measured geometry so standalone physics agrees with Blender."""
    if path is not None and Path(path).is_file():
        payload = scene_config.read_json(Path(path))
        payload['leaf_source'] = str(Path(path).resolve())
        return payload
    raise FileNotFoundError('Measured door_leaf.json is required for consistent geometry')


def initial_ball_state(physics, leaf):
    # Fixed start geometry, independent of the three editable parameters.
    # Ball rests ahead of the door's opening sweep, 72 cm from the hinge.
    yaw = math.radians(float(leaf['closed_yaw_deg'])) + math.radians(40.0)
    reach = 0.72
    start = [reach * math.cos(yaw), reach * math.sin(yaw), float(physics['ball_radius_m'])]
    return start, [0.0, 0.0, 0.0], list(start)


def apply_hinge_friction(physics_client: int, door: int, torque: float, inertia: float, dt: float) -> None:
    """Passive Coulomb hinge friction, capped at the stopping impulse."""
    if torque <= 0.0:
        return
    rate = p.getJointState(door, 0, physicsClientId=physics_client)[1]
    if abs(rate) < 1e-4:
        return
    # A friction impulse cannot reverse velocity or add kinetic energy.
    torque = min(torque, inertia * abs(rate) / dt)
    p.applyExternalTorque(
        door, 0, torqueObj=(0.0, 0.0, -torque if rate > 0.0 else torque),
        flags=p.WORLD_FRAME, physicsClientId=physics_client,
    )


def hinge_inertia_of(door_mass: float, width: float, thickness: float, slab_y: float) -> float:
    """Moment of inertia of the leaf about its hinge, which is what the
    friction cap is measured against."""
    return door_mass * (width * width / 3 + thickness * thickness / 12 + slab_y * slab_y)


def apply_timed_params(physics_client, frame, params, door, bodies, scripted, physics, fps):
    """Write a scheduled parameter set into the live scene and report both ends.

    ``door_hinge_friction`` is the torque the substep loop applies, so a change
    here takes effect on the next substep of the same frame; a mass change
    rewrites the body the contact acts on. Poses are read on both sides so the
    record shows a parameter was redefined rather than a body being kicked.
    """
    def current(name):
        if name == 'door_hinge_friction':
            return scripted['door_hinge_friction']
        if name == 'ball_active':
            return bodies['ball'] is not None
        return physics[name]

    ball = bodies['ball']
    angle_before, rate_before = p.getJointState(door, 0, physicsClientId=physics_client)[:2]
    ball_before = None
    if ball is not None:
        position, _ = p.getBasePositionAndOrientation(ball, physicsClientId=physics_client)
        velocity, _ = p.getBaseVelocity(ball, physicsClientId=physics_client)
        ball_before = {'location': list(position), 'linear_velocity': list(velocity)}
    before_params = {name: current(name) for name in params}
    before_state = {'door_angle_rad': float(angle_before),
                    'door_angular_velocity': float(rate_before),
                    'ball': ball_before, 'ball_active': ball is not None}

    if 'door_hinge_friction' in params:
        scripted['door_hinge_friction'] = float(params['door_hinge_friction'])
        physics['door_hinge_friction'] = float(params['door_hinge_friction'])
    if 'door_mass' in params:
        physics['door_mass'] = float(params['door_mass'])
        p.changeDynamics(door, 0, mass=physics['door_mass'], physicsClientId=physics_client)
        scripted['hinge_inertia'] = hinge_inertia_of(physics['door_mass'], *scripted['geometry'])
    if 'ball_mass' in params and ball is not None:
        physics['ball_mass'] = float(params['ball_mass'])
        p.changeDynamics(ball, -1, mass=physics['ball_mass'], physicsClientId=physics_client)
    if 'ball_active' in params and not scene_config.ball_active(params['ball_active']) and ball is not None:
        # A real removeBody: the ball stops colliding from this frame on.
        p.removeBody(ball, physicsClientId=physics_client)
        bodies['ball'] = None
        physics['ball_active'] = [0]

    ball_after = bodies['ball']
    angle_after, rate_after = p.getJointState(door, 0, physicsClientId=physics_client)[:2]
    ball_state = None
    if ball_after is not None:
        position, _ = p.getBasePositionAndOrientation(ball_after, physicsClientId=physics_client)
        velocity, _ = p.getBaseVelocity(ball_after, physicsClientId=physics_client)
        ball_state = {'location': list(position), 'linear_velocity': list(velocity)}
        if ball_before is not None and (ball_state['location'] != ball_before['location']
                                        or ball_state['linear_velocity'] != ball_before['linear_velocity']):
            raise RuntimeError('A mass change moved the ball; that is a kick, not an edit')
    if float(angle_before) != float(angle_after):
        raise RuntimeError('A parameter change moved the leaf; that is a kick, not an edit')
    return {'frame': frame, 'time_sec': (frame - 1) / fps, 'params': params,
            'before': {'params': before_params, 'state': before_state},
            'after': {'params': {name: current(name) for name in params},
                      'state': {'door_angle_rad': float(angle_after),
                                'door_angular_velocity': float(rate_after),
                                'ball': ball_state, 'ball_active': ball_after is not None}},
            'status': 'applied', 'effective_from_frame': frame}


def simulate(
    scenario: dict[str, Any],
    *,
    fps: int,
    duration_sec: float,
    substeps: int,
    leaf_path: Path | None,
) -> dict[str, Any]:
    physics = scenario['physics']
    scene_config.validate(scenario)
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

    start, velocity, aim = initial_ball_state(physics, leaf)
    hinge_inertia = door_mass * (width * width / 3 + thickness * thickness / 12 + slab_y * slab_y)

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
        p.resetJointState(door, 0, start_angle, float(physics['door_initial_velocity']), physicsClientId=client)

        ball = None
        if scene_config.ball_active(physics.get('ball_active', [1])):
            ball_shape = p.createCollisionShape(p.GEOM_SPHERE, radius=radius, physicsClientId=client)
            ball = p.createMultiBody(baseMass=ball_mass, baseCollisionShapeIndex=ball_shape,
                                     baseVisualShapeIndex=-1, basePosition=start, physicsClientId=client)
            p.changeDynamics(
                ball, -1, lateralFriction=float(physics['ball_friction']),
                rollingFriction=float(physics['ball_rolling_friction']),
                spinningFriction=float(physics['ball_spinning_friction']),
                restitution=float(physics['ball_restitution']),
                linearDamping=float(physics['ball_linear_damping']),
                angularDamping=float(physics['ball_angular_damping']), physicsClientId=client)
            p.resetBaseVelocity(ball, linearVelocity=velocity, physicsClientId=client)

        schedule = {event['frame']: event['params'] for event in physics.get('timed_edits', [])}
        timed.check_horizon(schedule, frame_end)

        frames: list[dict[str, Any]] = []
        impact_frame: int | None = None
        # The hinge torque is applied every substep, so it lives beside the
        # scenario dict rather than inside it: a timed edit rewrites this value
        # and the next substep runs on the new one.
        scripted = {'door_hinge_friction': float(physics['door_hinge_friction']),
                    'hinge_inertia': hinge_inertia,
                    'geometry': (width, thickness, slab_y)}
        bodies = {'ball': ball}
        timed_events: list[dict[str, Any]] = []
        for frame_index in range(1, frame_end + 1):
            # The edit lands at the top of its frame: frames 1..n-1 have already
            # been stepped on the source physics, and this frame's substeps run
            # on the edited value from the state the source had reached.
            if frame_index in schedule:
                timed_events.append(apply_timed_params(
                    client, frame_index, schedule[frame_index], door, bodies, scripted,
                    physics, fps))
                ball = bodies['ball']
            bounced = False
            if frame_index > 1:
                for step in range(substeps):
                    apply_hinge_friction(
                        client, door, scripted['door_hinge_friction'],
                        scripted['hinge_inertia'], dt
                    )
                    p.stepSimulation(physicsClientId=client)
                    # The hit is a one- or two-substep event, so it is looked
                    # for on every substep until it has been found; after that
                    # the per-frame contact flag is enough.
                    if impact_frame is None or not step % contact_stride:
                        if ball is not None and p.getContactPoints(ball, door, -1, 0, physicsClientId=client):
                            bounced = True
                            if impact_frame is None:
                                impact_frame = frame_index

            angle, angle_rate = p.getJointState(door, 0, physicsClientId=client)[:2]
            position = quaternion = linear = angular = None
            if ball is not None:
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
                    'ball_active': ball is not None,
                    'ball_location': list(position) if position is not None else None,
                    'ball_quaternion_xyzw': list(quaternion) if quaternion is not None else None,
                    'ball_linear_velocity': list(linear) if linear is not None else None,
                    'ball_angular_velocity': list(angular) if angular is not None else None,
                    'ball_contacting_door': bounced and ball is not None,
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
        visible = [f for f in frames if f['ball_active']]
        quality.update(
            initial_ball_speed_m_s=math.dist(frames[0]['ball_linear_velocity'], (0, 0, 0)) if frames[0]['ball_active'] else None,
            initial_door_velocity_rad_s=frames[0]['door_angular_velocity'],
            ball_displacement_m=math.dist(visible[0]['ball_location'], visible[-1]['ball_location']) if visible else None,
            peak_ball_speed_m_s=max(math.dist(f['ball_linear_velocity'], (0, 0, 0)) for f in visible) if visible else None,
            initial_door_energy_j=0.5 * hinge_inertia * physics['door_initial_velocity'] ** 2,
            transmission_observed=impact_frame is not None and any(math.dist(f['ball_linear_velocity'][:2], (0, 0)) > .1 for f in visible),
            ball_present_at_start=frames[0]['ball_active'],
            ball_present_at_end=frames[-1]['ball_active'],
            ball_removal_frame=next((f['frame_index'] for f in frames if not f['ball_active']), None),
            ball_visible_frames=len(visible),
            timed_events=timed_events,
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
            'scenario': scenario,
            'timed_edits': physics.get('timed_edits', []),
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
    speeds = [math.dist(f['ball_linear_velocity'], (0.0, 0.0, 0.0)) if f['ball_active'] else 0.0 for f in frames]

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
        linear = math.dist(record['ball_linear_velocity'], (0.0, 0.0, 0.0)) if record['ball_active'] else 0.0
        spin = math.dist(record['ball_angular_velocity'], (0.0, 0.0, 0.0)) if record['ball_active'] else 0.0
        door_rates = abs(record['door_angular_velocity'])
        if linear < quiet_speed and spin < quiet_spin and door_rates < 0.05:
            streak += 1
            if streak >= quiet_need:
                settle_frame = frames[-streak]['frame_index']
        else:
            break

    path = 0.0
    for previous, current in zip(frames, frames[1:]):
        if previous['ball_active'] and current['ball_active']:
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
        'door_rebound_deg': round(sum(max(0, previous - current)
                                     for previous, current in zip(angles, angles[1:])), 2),
        'door_at_closed_limit': abs(angles[-1] - closed_limit_deg) < 1.0,
        'door_at_open_limit': abs(angles[-1] - open_limit_deg) < 1.0,
        'ball_speed_before_m_s': round(before, 3) if before is not None else None,
        'ball_speed_after_m_s': round(after, 3) if after is not None else None,
        'ball_path_m': round(path, 3) if any(f['ball_active'] for f in frames) else None,
        'ball_final_xyz': [round(v, 3) for v in final] if final is not None else None,
        'ball_aim_xyz': [round(v, 3) for v in aim],
        'ball_start_xyz': [round(v, 3) for v in start],
        'settle_frame': settle_frame,
        'final_ball_speed_m_s': round(speeds[-1], 3) if frames[-1]['ball_active'] else None,
        'final_door_rate_rad_s': round(rates[-1], 4),
    }


def main() -> None:
    args = parse_args()
    scenario = scene_config.load_scenario(args.scenario, args.scenario_overrides_json, args)
    physics = scenario['physics']

    leaf_path = args.door_leaf_json or _PCVE_PROJECT_ROOT / 'assets' / 'scenarios' / 'door_basketball_collision' / LEAF_NAME
    records = simulate(
        scenario,
        fps=int(args.fps if args.fps is not None else physics['fps']),
        duration_sec=float(
            args.duration_sec if args.duration_sec is not None else physics['duration_sec']
        ),
        substeps=int(args.substeps if args.substeps is not None else physics['substeps_per_frame']),
        leaf_path=leaf_path,
    )
    scene_config.write_json(args.out, records)
    scene_config.write_json(args.out.parent / 'simulation_metrics.json', records['quality'])

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


if __name__ == '__main__':
    main()

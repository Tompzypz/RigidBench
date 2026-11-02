"""Rigid-body impact; metres, kilograms, seconds. No scripted post-impact motion."""
# Resolve this scene folder and the repository assets directory.
import sys as _pcve_local_sys
from pathlib import Path as _PcveLocalPath
_pcve_scene_dir = _PcveLocalPath(__file__).resolve().parent
_pcve_scripts_root = _pcve_scene_dir.parent
_pcve_local_sys.path.insert(0, str(_pcve_scripts_root))
_PCVE_PROJECT_ROOT = next(p for p in _pcve_scene_dir.parents if (p / "assets").is_dir())
import argparse
import copy
import json
import math
from pathlib import Path

import pybullet as p
from edit_vocab import prepare_config


_ALLOWED_TIMED_FIELDS = {"bottle_restitution", "initial_velocity"}


def _bottle_vertices(height, radius):
    vertices = []
    for z, ring_radius in [(-height / 2, radius * .82), (-height * .44, radius),
                           (height * .22, radius), (height * .35, radius * .48),
                           (height / 2, radius * .48)]:
        for i in range(32):
            angle = i * math.tau / 32
            vertices.append([ring_radius * math.cos(angle), ring_radius * math.sin(angle), z])
    return vertices


def _validate_timed_edits(events, frame_count):
    if not isinstance(events, list):
        raise ValueError("timed_edits must be a list")
    schedule = {}
    for index, event in enumerate(events):
        if not isinstance(event, dict) or set(event) != {"frame", "params"}:
            raise ValueError(f"timed_edits[{index}] must contain exactly frame and params")
        frame = event["frame"]
        if isinstance(frame, bool) or not isinstance(frame, int) or not 2 <= frame <= frame_count:
            raise ValueError(f"timed_edits[{index}].frame must be an integer from 2 to {frame_count}")
        if frame in schedule:
            raise ValueError(f"More than one timed event targets frame {frame}")
        params = event["params"]
        if not isinstance(params, dict) or not params:
            raise ValueError(f"timed_edits[{index}].params must be a non-empty object")
        unknown = set(params) - _ALLOWED_TIMED_FIELDS
        if unknown:
            raise ValueError(f"Unsupported timed physics fields: {sorted(unknown)}")
        for name, value in params.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"timed_edits[{index}].params.{name} must be a finite number")
            if name == "bottle_restitution" and not 0 <= value <= 1:
                raise ValueError("Timed bottle_restitution must be between 0 and 1")
            if name == "initial_velocity" and value <= 0:
                raise ValueError("Timed car initial_velocity must be positive")
        schedule[frame] = dict(params)
    return schedule


def simulate(config, fps=24, duration=4.0, substeps=80):
    config = prepare_config(copy.deepcopy(config))
    c = config["physics"]
    layout = config["layout"]
    if fps <= 0 or duration <= 0 or substeps < 1:
        raise ValueError("fps, duration and substeps must be positive")
    frame_count = round(fps * duration)
    if frame_count < 1:
        raise ValueError("The simulation must contain at least one frame")
    unknown = set(c) - {*BASELINE_PHYSICS_KEYS, "timed_edits"}
    if unknown:
        raise ValueError(f"Unknown physics parameters: {sorted(unknown)}")
    for key in ("car_mass", "bottle_mass", "bottle_2_mass"):
        if c[key] <= 0:
            raise ValueError(key + " must be positive")
    presence = c["bottle_presence"]
    if (not isinstance(presence, list) or len(presence) != 2
            or any(type(value) is not int or value not in (0, 1) for value in presence)
            or presence[0] != 1):
        raise ValueError("bottle_presence must be [1, 0] or [1, 1]")
    schedule = _validate_timed_edits(c.get("timed_edits", []), frame_count)

    client = p.connect(p.DIRECT)
    try:
        dt = 1 / (fps * substeps)
        p.setTimeStep(dt)
        p.setGravity(0, 0, c["gravity_z"])
        p.setPhysicsEngineParameter(numSolverIterations=100)
        # Bullet drops restitution below this approach speed. A light hollow bottle
        # only ever meets the floor at a few tenths of a m/s, so the default gate
        # makes it land dead; the scene lowers it to give the empty PET a little bounce.
        p.setPhysicsEngineParameter(restitutionVelocityThreshold=c.get("restitution_velocity_threshold", .2))
        floor = p.createMultiBody(0, p.createCollisionShape(p.GEOM_PLANE))
        p.changeDynamics(floor, -1, lateralFriction=c["floor_friction"], restitution=c.get("floor_restitution", .1))
        length = layout["car_length"]
        # Local X is the long axis; renderer rotates the GLB's -Y nose to +X.
        half = [length / 2, layout["car_width"] / 2, layout["car_height"] / 2]
        car = p.createMultiBody(c["car_mass"], p.createCollisionShape(p.GEOM_BOX, halfExtents=half),
                                basePosition=[c["car_start_x"], 0, half[2] + 0.0005])
        h, r = layout["bottle_height"], layout["bottle_radius"]
        bottle_shape = p.createCollisionShape(p.GEOM_MESH, vertices=_bottle_vertices(h, r))

        def create_bottle(name, mass, position, friction, restitution,
                          linear_damping, angular_damping, rolling_friction):
            body = p.createMultiBody(mass, bottle_shape, basePosition=position)
            p.changeDynamics(body, -1, lateralFriction=friction, restitution=restitution,
                             linearDamping=linear_damping, angularDamping=angular_damping,
                             rollingFriction=rolling_friction, collisionMargin=.0005)
            return body

        bottle = create_bottle(
            "bottle", c["bottle_mass"],
            [c["bottle_start_x"], c["bottle_start_y"], h / 2 + .001],
            c["bottle_friction"], c["bottle_restitution"],
            c.get("bottle_linear_damping", .04), c.get("bottle_angular_damping", .08),
            c.get("bottle_rolling_friction", .002))
        bodies = [("car", car), ("bottle", bottle)]
        if presence[1]:
            bottle_2 = create_bottle(
                "bottle_2", c["bottle_2_mass"], c["bottle_2_start_position"],
                c["bottle_2_friction"], c["bottle_2_restitution"],
                c["bottle_2_linear_damping"], c["bottle_2_angular_damping"],
                c["bottle_2_rolling_friction"])
            bodies.append(("bottle_2", bottle_2))

        for _ in range(int(.3 / dt)):
            p.stepSimulation()
        p.resetBaseVelocity(car, [c["initial_velocity"], 0, 0])
        frames, contact_frame = [], None
        first_contacts = {}
        timed_event_log = []
        for frame in range(1, frame_count + 1):
            events_this_frame = []
            if frame in schedule:
                params = schedule[frame]
                before = {name: c[name] for name in params}
                state_before = None
                if "initial_velocity" in params:
                    car_position, _ = p.getBasePositionAndOrientation(car)
                    car_linear, car_angular = p.getBaseVelocity(car)
                    state_before = {"car_position": list(car_position),
                                    "car_linear_velocity": list(car_linear)}
                c.update(params)
                if "bottle_restitution" in params:
                    p.changeDynamics(bottle, -1, restitution=c["bottle_restitution"])
                if "initial_velocity" in params:
                    p.resetBaseVelocity(car,
                        linearVelocity=[c["initial_velocity"], car_linear[1], car_linear[2]],
                        angularVelocity=car_angular)
                event = {"frame": frame, "params": params, "before": before,
                         "after": {name: c[name] for name in params},
                         "status": "applied", "effective_from_frame": frame}
                if state_before is not None:
                    car_position_after, _ = p.getBasePositionAndOrientation(car)
                    car_linear_after, _ = p.getBaseVelocity(car)
                    event.update(state_before=state_before,
                                 state_after={"car_position": list(car_position_after),
                                              "car_linear_velocity": list(car_linear_after)})
                timed_event_log.append(event)
                events_this_frame.append(event)

            objects = {}
            for name, body in bodies:
                pos, quat = p.getBasePositionAndOrientation(body)
                vel, angular = p.getBaseVelocity(body)
                objects[name] = dict(present=True, position=list(pos), quaternion_xyzw=list(quat),
                                     linear_velocity=list(vel), angular_velocity=list(angular))
            if not presence[1]:
                objects["bottle_2"] = dict(present=False, position=None, quaternion_xyzw=None,
                                           linear_velocity=None, angular_velocity=None)
            frames.append(dict(frame=frame, time=(frame - 1) / fps, objects=objects,
                               timed_events=events_this_frame))
            if frame < frame_count:
                for _ in range(substeps):
                    p.stepSimulation()
                    for i, (name_a, body_a) in enumerate(bodies):
                        for name_b, body_b in bodies[i + 1:]:
                            pair = f"{name_a}:{name_b}"
                            if pair not in first_contacts and p.getContactPoints(body_a, body_b):
                                first_contacts[pair] = frame + 1
                    if contact_frame is None and p.getContactPoints(car, bottle):
                        contact_frame = frame + 1
        return dict(fps=fps, duration_sec=duration, frame_count=len(frames),
                    first_contact_frame=contact_frame, first_contact_frames=first_contacts,
                    timed_events=timed_event_log, frames=frames, config=config)
    finally:
        p.disconnect(client)


# Set at import time by the scene vocabulary so simulation and DSL share one allowlist.
from edit_vocab import BASELINE_PHYSICS as _BASELINE_PHYSICS
BASELINE_PHYSICS_KEYS = frozenset(_BASELINE_PHYSICS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--scenario-overrides-json", type=Path)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--duration-sec", type=float, default=4)
    args = parser.parse_args()
    config = prepare_config(json.loads((_PCVE_PROJECT_ROOT / "assets" / "scenarios" / "toy_car_bottle" / "scenario.json").read_text(encoding="utf-8")))
    if args.scenario_overrides_json:
        payload = json.loads(args.scenario_overrides_json.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Scenario overrides must be a JSON object")
        if "physics" in payload:
            unknown_groups = set(payload) - {"physics", "assets", "layout"}
            if unknown_groups:
                raise ValueError(f"Unknown scenario override groups: {sorted(unknown_groups)}")
            overrides = payload["physics"]
        else:
            overrides = payload
        if not isinstance(overrides, dict):
            raise ValueError("Physics overrides must be a JSON object")
        unknown = set(overrides) - (set(BASELINE_PHYSICS_KEYS) | {"timed_edits"})
        if unknown:
            raise ValueError(f"Unknown physics overrides: {sorted(unknown)}")
        config["physics"].update(overrides)
    result = simulate(config, args.fps, args.duration_sec)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print("First contact frame:", result["first_contact_frame"])
    print("First object contacts:", result["first_contact_frames"])
    print("Timed events:", result["timed_events"])
    print("Final velocities:", {k: v["linear_velocity"] for k, v in result["frames"][-1]["objects"].items() if v["present"]})

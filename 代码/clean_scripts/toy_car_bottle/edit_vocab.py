"""Single-variable physical edits for the existing toy-car/bottle simulation."""

# Resolve this scene folder and the repository assets directory.
import sys as _pcve_local_sys
from pathlib import Path as _PcveLocalPath
_pcve_scene_dir = _PcveLocalPath(__file__).resolve().parent
_pcve_scripts_root = _pcve_scene_dir.parent
_pcve_local_sys.path.insert(0, str(_pcve_scripts_root))
_PCVE_PROJECT_ROOT = next(p for p in _pcve_scene_dir.parents if (p / "assets").is_dir())
import json

import pcve_edit_dsl as dsl


_BASE_CONFIG = json.loads((_PCVE_PROJECT_ROOT / "assets" / "scenarios" / "toy_car_bottle" / "scenario.json").read_text(encoding="utf-8"))
_BASE_LAYOUT = _BASE_CONFIG["layout"]
_BASE_PHYSICS = _BASE_CONFIG["physics"]


def prepare_config(config):
    """Add this scene's dormant second-bottle slot and geometry anchors."""
    physics = config["physics"]
    layout = config["layout"]
    car_position = [physics["car_start_x"], 0.0, layout["car_height"] / 2 + 0.0005]
    bottle_position = [physics["bottle_start_x"], physics["bottle_start_y"], layout["bottle_height"] / 2 + 0.001]
    # ADD placement is resolved on the shared action plane; using the car's
    # lower centre height would put an upright bottle midpoint below the floor.
    car_add_anchor = [car_position[0], car_position[1], bottle_position[2]]
    midpoint = [(a + b) / 2 for a, b in zip(car_add_anchor, bottle_position)]
    physics.setdefault("car_start_position", car_position)
    physics.setdefault("car_add_anchor_position", car_add_anchor)
    physics.setdefault("car_geometry_radius", layout["car_length"] / 2)
    physics.setdefault("bottle_radius", layout["bottle_radius"])
    physics.setdefault("bottle_start_position", bottle_position)
    physics.setdefault("bottle_presence", [1, 0])
    physics.setdefault("bottle_2_mass", physics["bottle_mass"])
    physics.setdefault("bottle_2_friction", physics["bottle_friction"])
    physics.setdefault("bottle_2_restitution", physics["bottle_restitution"])
    physics.setdefault("bottle_2_linear_damping", physics.get("bottle_linear_damping", 0.02))
    physics.setdefault("bottle_2_angular_damping", physics.get("bottle_angular_damping", 0.04))
    physics.setdefault("bottle_2_rolling_friction", physics.get("bottle_rolling_friction", 0.002))
    physics.setdefault("bottle_2_start_position", midpoint)
    return config


BASELINE_CONFIG = prepare_config(json.loads(json.dumps(_BASE_CONFIG)))
BASELINE_PHYSICS = BASELINE_CONFIG["physics"]

VOCAB = dsl.Vocabulary(
    objects={"car": {"zh": "玩具车", "en": "the toy car"},
             "bottle": {"zh": "塑料水瓶", "en": "the plastic water bottle"},
             "bottle_2": {"zh": "第二个塑料水瓶", "en": "an additional plastic water bottle"}},
    properties={"mass": dsl.PropertySpec("scalar", "kg", "质量", "mass"),
                "initial_velocity": dsl.PropertySpec("scalar", "m/s", "初速度", "initial speed", initial_condition=True),
                "speed": dsl.PropertySpec("scalar", "m/s", "速度", "speed"),
                "friction": dsl.PropertySpec("scalar", "", "摩擦因数", "friction coefficient"),
                "restitution": dsl.PropertySpec("scalar", "", "恢复系数", "restitution")},
    sim_bindings={(obj, prop): dsl.SimBinding(key) for obj, prop, key in [
        ("car", "mass", "car_mass"), ("car", "initial_velocity", "initial_velocity"),
        ("car", "speed", "initial_velocity"),
        ("car", "friction", "car_friction"), ("bottle", "mass", "bottle_mass"),
        ("bottle", "friction", "bottle_friction"), ("bottle", "restitution", "bottle_restitution")]},
    delete_bindings={},
    geometry={
        "car": dsl.GeometryAnchor("car_add_anchor_position", "car_geometry_radius"),
        "bottle": dsl.GeometryAnchor("bottle_start_position", "bottle_radius"),
        "bottle_2": dsl.GeometryAnchor("bottle_2_start_position", "bottle_radius"),
    },
    add_bindings={"bottle_2": dsl.AddBinding(
        presence_key="bottle_presence", presence_index=1,
        location_key="bottle_2_start_position",
        defaults=tuple((key, BASELINE_PHYSICS[key]) for key in (
            "bottle_2_mass", "bottle_2_friction", "bottle_2_restitution",
            "bottle_2_linear_damping", "bottle_2_angular_damping",
            "bottle_2_rolling_friction")))},
    baseline_physics=BASELINE_PHYSICS, total_frames=96)

EDIT_CASES = (
    ("edit_heavy_bottle", "SET bottle.mass TIMES 4"),
    ("edit_fast_car", "SET car.initial_velocity TIMES 1.5"),
    ("edit_slippery_bottle", "SET bottle.friction TIMES 0.25"),
    ("edit_add_midpoint_bottle", "ADD bottle_2 BETWEEN car AND bottle AT MIDPOINT"),
    ("edit_fast_car_midflight", "SET car.speed TIMES 1.5 AT FRAME 5"),
)

DESCRIPTION = {
    "vague": {"zh": "玩具车撞向塑料水瓶，水瓶倾倒、滑动并停下。",
              "en": "A toy car strikes a plastic water bottle, which topples, slides and comes to rest."},
    "quantitative": {"zh": f"质量 {BASELINE_PHYSICS['car_mass']:g} kg 的玩具车以 {BASELINE_PHYSICS['initial_velocity']:g} m/s 撞向质量 {BASELINE_PHYSICS['bottle_mass']:g} kg 的塑料水瓶。",
                     "en": f"A {BASELINE_PHYSICS['car_mass']:g} kg toy car starts at {BASELINE_PHYSICS['initial_velocity']:g} m/s and strikes a {BASELINE_PHYSICS['bottle_mass']:g} kg plastic water bottle."}}

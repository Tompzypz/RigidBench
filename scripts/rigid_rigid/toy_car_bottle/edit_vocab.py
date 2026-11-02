"""Single-variable physical edits for the existing toy-car/bottle simulation."""
# PCVE_UNIFIED_ENTRY_BEGIN

# Resolve this scene folder and the repository assets directory.
import sys as _pcve_local_sys
from pathlib import Path as _PcveLocalPath
_pcve_scene_dir = _PcveLocalPath(__file__).resolve().parent
_pcve_scripts_root = _pcve_scene_dir.parents[1]
_pcve_local_sys.path.insert(0, str(_pcve_scripts_root))
_PCVE_PROJECT_ROOT = next(p for p in _pcve_scene_dir.parents if (p / "assets").is_dir())
# Shared modules live in scripts/; scene-local modules live in this directory and
# its physics/, appearance/ and tools/ subdirectories.
for _scene_sub in ("", "physics", "appearance", "tools"):
    _scene_sub_dir = _pcve_scene_dir / _scene_sub if _scene_sub else _pcve_scene_dir
    if _scene_sub_dir.is_dir() and str(_scene_sub_dir) not in _pcve_local_sys.path:
        _pcve_local_sys.path.insert(1, str(_scene_sub_dir))
# PCVE_UNIFIED_ENTRY_END
import pcve_edit_dsl as dsl

from scene_config import BASELINE_CONFIG, BASELINE_PHYSICS, prepare_config

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

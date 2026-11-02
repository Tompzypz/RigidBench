"""Edit vocabulary for the loaded-flatbed speed-bump scene.

The vocabulary exposes the three causal controls the scene was built to
demonstrate: powered truck speed, the bump's physical height, and the
cargo/deck friction pairing.  It is kept separate from the simulation so
PCVE-style edit prompts stay data-driven.
"""
# PCVE_UNIFIED_ENTRY_BEGIN
# Scene-local modules live in this directory and its physics/, appearance/ and
# tools/ subdirectories; shared modules live in scripts/.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_BUNDLE_SCENE = _ScenePath(__file__).resolve().parent
_BUNDLE_SCRIPTS = _BUNDLE_SCENE.parents[1]
_PCVE_PROJECT_ROOT = next(p for p in _BUNDLE_SCENE.parents if (p / "assets").is_dir())
for _scene_sub in (_BUNDLE_SCRIPTS, _BUNDLE_SCENE, *(_BUNDLE_SCENE / _s for _s in ("physics", "appearance", "tools"))):
    if _scene_sub.is_dir() and str(_scene_sub) not in _scene_sys.path:
        _scene_sys.path.insert(1, str(_scene_sub))
# PCVE_UNIFIED_ENTRY_END




# Resolve the shared scripts bundle in both scripts/<scene> and scripts/rigid_rigid/<scene> layouts.
import sys as _pcve_sys
from pathlib import Path as _PcvePath
for _pcve_parent in _PcvePath(__file__).resolve().parents:
    if (_pcve_parent / "pcve_edit_dsl.py").is_file() and (_pcve_parent / "pcve_edit_dsl.py").is_file():
        _pcve_sys.path.insert(0, str(_pcve_parent))
        break
# Find the repository root for both scripts/<scene> and scripts/rigid_rigid/<scene> layouts.
_PCVE_PROJECT_ROOT = next((p for p in _PcvePath(__file__).resolve().parents if (p / "assets").is_dir() and (p / "scripts").is_dir()), _PcvePath(__file__).resolve().parents[-1])


import sys
from pathlib import Path

import pcve_edit_dsl as dsl  # noqa: E402

from scene_config import BASELINE_PHYSICS, BASELINE_RENDER  # noqa: E402


OBJECTS = {
    "flatbed_truck": {"zh": "载物平板卡车", "en": "the loaded flatbed truck"},
    "speed_bump": {"zh": "减速带", "en": "the speed bump"},
    "cargo": {"zh": "货箱", "en": "the cargo cartons"},
}

PROPERTIES = {
    # The launch condition: the cruise target the drive force is started on.
    # Named ``initial_*`` because it is fixed when the clip starts, which is
    # also what stops the DSL from offering it an AT FRAME clause.
    "initial_velocity": dsl.PropertySpec("scalar", "m/s", "起步速度", "initial driving speed",
                                         initial_condition=True),
    # The same cruise target, but as a live control the truck holds while it
    # runs: the drive force in the simulator reads it every substep, so
    # rewriting it partway through is a real change of what the truck does
    # next. That is what makes a timed braking edit expressible at all.
    "speed": dsl.PropertySpec("scalar", "m/s", "行驶速度", "driving speed"),
    "height": dsl.PropertySpec("scalar", "m", "减速带高度", "bump height"),
    "friction": dsl.PropertySpec("scalar", "", "摩擦因数", "friction coefficient"),
}

SIM_BINDINGS = {
    ("flatbed_truck", "initial_velocity"): dsl.SimBinding("truck_speed"),
    ("flatbed_truck", "speed"): dsl.SimBinding("truck_speed"),
    ("speed_bump", "height"): dsl.SimBinding("speed_bump_height"),
    ("cargo", "friction"): dsl.SimBinding("cargo_friction"),
}

VOCAB = dsl.Vocabulary(
    objects=OBJECTS,
    properties=PROPERTIES,
    sim_bindings=SIM_BINDINGS,
    delete_bindings={},
    baseline_physics=dict(BASELINE_PHYSICS),
    total_frames=round(BASELINE_RENDER["fps"] * BASELINE_RENDER["duration_sec"]),
)

# Exactly five single-variable cases. Each one moves one declared control (or,
# for the last, writes the truck's live speed target partway through) and how
# far the cartons are thrown is then whatever PyBullet solves.
#
# Multipliers are chosen against measured outcomes, not by eye. Baseline, at
# 24 fps: the front axle meets the bump on frame 14, the deck rebounds and the
# cartons separate on frame 26-27, the near-side carton slides aft and goes over
# the tail (11.0 m of deck-relative travel), the far-side one rides it out.
#   * 2 x speed (18 m/s)     : both leave for 21 and 22 frames, chassis lift
#                              1.82 m against 0.45 m, the truck ends at 64 m.
#   * 0.3 x bump (0.051 m)   : chassis lift collapses to 0.03 m, clearance
#                              0.029 m, 2 airborne frames -- nothing separates.
#   * 1.5 x bump (0.255 m)   : both leave, 0.65 m of clearance -- the load is
#                              thrown clear of the deck, not just loosened.
#   * 0.25 x friction (0.05) : both skid aft and leave; the throw is vertical
#                              and barely moves, the skid is what doubles.
#   * brake to 0.4 x at frame 8: the truck visibly slows on the approach and
#                              crosses at 3.6 m/s, so neither carton separates
#                              (0.007 m) and it ends 9.5 m down the road instead
#                              of 28.6 m. Frames 1-8 are the source clip.
EDIT_CASES = (
    ("edit_fast_truck", "SET flatbed_truck.initial_velocity TIMES 2"),
    ("edit_low_bump", "SET speed_bump.height TIMES 0.3"),
    ("edit_high_bump", "SET speed_bump.height TIMES 1.5"),
    ("edit_slippery_cargo", "SET cargo.friction TIMES 0.25"),
    ("edit_brake_before_bump", "SET flatbed_truck.speed TIMES 0.4 AT FRAME 8"),
)

# Prompts for the source clip. Every number here is read from the baseline
# parameters above, so the description cannot drift away from the simulation.
DESCRIPTION = {
    "vague": {
        "zh": "一辆载着两个货箱的平板卡车高速驶过减速带，货箱被颠离车厢，靠近车尾的那个滑出车板掉到路上。",
        "en": "A flatbed truck carrying two cargo cartons crosses a speed bump fast enough that the cartons are thrown off the deck, and the rear-facing one slides over the tail onto the road.",
    },
    "quantitative": {
        "zh": (f"卡车以 {BASELINE_PHYSICS['truck_speed']:g} m/s 通过高 "
               f"{BASELINE_PHYSICS['speed_bump_height']:g} m、宽 1.34 m 的圆顶减速带；"
               "车板为弹簧悬挂（刚度 40 kN/m、阻尼 1.87 kN·s/m，行程 -0.09/+0.07 m），"
               f"货箱与车板的摩擦因数为 {BASELINE_PHYSICS['cargo_friction']:g}，每个货箱质量 42 kg。"),
        "en": (f"The truck crosses a {BASELINE_PHYSICS['speed_bump_height']:g} m high, 1.34 m wide rounded bump at "
               f"{BASELINE_PHYSICS['truck_speed']:g} m/s; the deck is sprung (40 kN/m, 1.87 kN.s/m, -0.09/+0.07 m travel) "
               f"and cargo-to-deck friction is {BASELINE_PHYSICS['cargo_friction']:g}, each carton 42 kg."),
    },
}

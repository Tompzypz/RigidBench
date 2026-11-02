"""Edit vocabulary for the pool-break scene.

The three causal controls the scene was built to demonstrate: how hard the cue
ball is struck, where on the apex ball it lands, and how heavy the cue ball is.
Kept separate from the simulation so PCVE-style edit prompts stay data-driven --
the same three names appear in the DSL, in the prompts JSON and in the physics
dict the simulator reads.

Why the contact point is a signed distance and not an angle
-----------------------------------------------------------
"Hit it a bit to the left" is an impact parameter: the perpendicular distance
between the cue ball's line of travel and the apex ball's centre. Expressed as
an aim *angle* the same shot is 1.4 degrees, which is both useless as a prompt
("increase the angle by a little") and wrong as a knob -- the cue starts a metre
away, so a 1.4 degree aim error moves the impact point by a full ball radius.
Metres are what the physics actually uses, so metres are what the vocabulary
says. Positive is the apex ball's right side, i.e. the right of the frame in the
default camera; +/- one ball radius (0.0286 m) is a half-ball hit.
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

from scene_config import BASELINE_PHYSICS, BASELINE_RENDER, FIXED_PHYSICS  # noqa: E402


OBJECTS = {
    "cue_ball": {"zh": "母球", "en": "the cue ball"},
    "rack": {"zh": "三颗目标球", "en": "the three racked balls"},
}

PROPERTIES = {
    "initial_velocity": dsl.PropertySpec("scalar", "m/s", "出杆速度", "cue speed"),
    "contact_offset": dsl.PropertySpec("scalar", "m", "击球点横向偏移", "contact offset", initial_condition=True),
    "mass": dsl.PropertySpec("scalar", "kg", "质量", "mass"),
    "friction": dsl.PropertySpec("scalar", "", "摩擦系数", "friction coefficient"),
    "restitution": dsl.PropertySpec("scalar", "", "恢复系数", "restitution"),
}

SIM_BINDINGS = {
    ("cue_ball", "initial_velocity"): dsl.SimBinding("cue_speed"),
    ("cue_ball", "contact_offset"): dsl.SimBinding("cue_contact_offset"),
    ("cue_ball", "mass"): dsl.SimBinding("cue_mass"),
    # The three racked balls are edited as one group: a viewer of a break can
    # say "the object balls got bouncier", not "the left wing ball did".
    ("rack", "mass"): dsl.SimBinding("object_mass"),
    ("rack", "friction"): dsl.SimBinding("object_friction"),
    ("rack", "restitution"): dsl.SimBinding("object_restitution"),
}

# Deliberately NOT editable: the felt and the cushions. The knobs above are
# the ones a viewer of a break can name from the picture; cloth friction or
# cushion restitution would each be a single-variable edit that no one
# watching the clip could attribute to the thing that changed.
# The vocabulary's baseline view carries the rack-side fixed physics too:
# a "TIMES n" edit multiplies the value the scene actually starts from, and
# physics_diff reads its "from" side from here. The simulator wires the
# rack's friction and restitution to the shared ball values by default
# (see simulate_pool_break.py's CLI defaults), so the baseline view does the
# same. The scenario's own physics block keeps only the three cue controls,
# as before.
VOCAB = dsl.Vocabulary(
    objects=OBJECTS,
    properties=PROPERTIES,
    sim_bindings=SIM_BINDINGS,
    delete_bindings={},
    baseline_physics={
        **BASELINE_PHYSICS, **FIXED_PHYSICS,
        "object_friction": FIXED_PHYSICS["ball_friction"],
        "object_restitution": FIXED_PHYSICS["ball_restitution"],
    },
    total_frames=round(BASELINE_RENDER["fps"] * BASELINE_RENDER["duration_sec"]),
)

# Five cases. Four hold from frame 1; the last one lands partway through --
# the baseline cue ball reaches the rack on frame 8, so the schedule deadens
# the object balls' restitution at frame 13, once the break has already sent
# them flying: the break itself is the baseline clip bit for bit, and what
# the edit changes is how the flying balls come off the first cushion (they
# thud and stop near the rail instead of kicking back across the table --
# measured spread 1285.8 mm vs the baseline's 1082.0 mm).
EDIT_CASES = (
    # 2.5 gives 9.0 m/s: everything runs the rails.
    ("edit_power_break", "SET cue_ball.initial_velocity TIMES 2.5"),
    # Half-ball cuts either side of the apex ball. The triangle opens toward the
    # side the cue does *not* hit, and the cue ball itself leaves along the
    # cushion, which is the clearest possible read of "the contact point moved".
    ("edit_cut_left", 'SET cue_ball.contact_offset TO -0.0143 HINT "向左偏"'),
    ("edit_cut_right", 'SET cue_ball.contact_offset TO 0.0143 HINT "向右偏"'),
    # 0.051 kg: the light cue ball rebounds off the break instead of following through.
    ("edit_light_cue", "SET cue_ball.mass TIMES 0.3"),
    ("edit_dead_rack_timed", "SET rack.restitution TIMES 0.1 AT FRAME 13"),
)

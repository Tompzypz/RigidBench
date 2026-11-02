"""Edit vocabulary for the home_basketball_door scene.

Two bodies can be edited, and both of them are the point of the clip:

* **the ball** -- ``mass`` and ``speed`` decide how much momentum arrives at
  the leaf, which decides how far the door swings;
* **the door** -- ``mass`` decides how much of that momentum turns into
  rotation, and ``friction`` (a Coulomb resisting torque in the hinge, N m)
  decides how much of the rotation survives.

A viscous model would leave the swing angle independent of the leaf's inertia
(the inertia cancels between the impulse that starts the swing and the decay
that ends it), which is why this scene brakes with a constant torque instead.
With a constant torque the leaf stops after ``I w^2 / (2 tau)`` radians, and
``w`` itself goes as ``1/I``, so the swing scales as ``1/I``: three times the
leaf mass measured 32.73 -> 12.22 deg of travel (ratio 2.68, ideal 3), and four
times the hinge friction measured 32.73 -> 8.34 deg (ratio 3.92, ideal 4).

That scaling only reads on screen while the leaf has room to stop *before* the
jamb. With a slack hinge it reaches 0 deg every time and every edit looks the
same -- measured at tau = 0.45 N m, all six candidate cases travelled 43-45 deg.
The baseline therefore brakes at 4.0 N m and settles 12.3 deg ajar.

The baseline is read from ``scenario.json`` rather than copied here, so the
DSL, the prompts and the physics diffs cannot drift away from the scene.
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
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
import pcve_edit_dsl as dsl  # noqa: E402
import scene_config  # noqa: E402


SCENARIO = scene_config.load_scenario()
BASELINE_PHYSICS = SCENARIO['physics']


OBJECTS = {
    'ball': {'zh': '篮球', 'en': 'the basketball'},
    'door': {'zh': '门', 'en': 'the door'},
}
# Deliberately NOT editable: the room, the jamb and the floor. They are what
# the two bodies move against, not props.


PROPERTIES = {
    'mass':    dsl.PropertySpec('scalar', 'kg',  '质量',   'mass'),
    'speed':   dsl.PropertySpec('scalar', 'm/s', '初速度', 'throw speed', initial_condition=True),
    'friction': dsl.PropertySpec('scalar', 'N·m', '门轴摩擦', 'hinge friction'),
}


SIM_BINDINGS = {
    ('ball', 'mass'):  dsl.SimBinding('ball_mass'),
    ('ball', 'speed'): dsl.SimBinding('ball_speed'),
    ('door', 'mass'):  dsl.SimBinding('door_mass'),
    # The hinge friction torque the simulator applies every substep. It is a
    # real physics key, not a derived one: write it and the leaf brakes harder.
    ('door', 'friction'): dsl.SimBinding('door_hinge_friction'),
}


DELETE_BINDINGS: dict[str, dsl.DeleteBinding] = {}


# 4.0 s at 24 fps, which is what build_pcve_home_basketball_door.py renders. An "AT
# FRAME n" edit is bounded by this, and the vague prompt reads n against it to
# say whether the edit lands early, midway or late in the clip.
TOTAL_FRAMES = 96


VOCAB = dsl.Vocabulary(
    objects=OBJECTS,
    properties=PROPERTIES,
    sim_bindings=SIM_BINDINGS,
    delete_bindings=DELETE_BINDINGS,
    baseline_physics=BASELINE_PHYSICS,
    total_frames=TOTAL_FRAMES,
)


# --------------------------------------------------------------- edit cases
#
# Five single-variable cases. The source clip, measured on this simulator with
# the leaf the renderer measures off the room mesh: impact on frame 11, the leaf
# swings 45.0 -> 0.07 deg (44.93 deg of travel, peaking at 1.01 rad/s) and rests
# against the jamb from frame 33; the ball leaves the impact at 3.92 m/s, traces
# 6.27 m of floor and ends at (0.91, 3.24).
#
# The source slams the door shut, so the interesting direction is anything that
# stops it short of the jamb. Each summary below quotes what this simulator
# produced for that case, not what the knobs are expected to do: door travel is
# I w^2 / (2 tau), so travel scales as 1/I against leaf mass and as 1/tau
# against hinge friction, and only reads on screen while the leaf has room to
# stop before it hits the jamb.
@dataclass(frozen=True)
class EditCase:
    case_id: str
    seed: int
    dsl: str
    edit_summary: str


SOURCE_CASE_ID = 'home_basketball_door_baseline'


EDIT_CASES: tuple[EditCase, ...] = (
    EditCase(
        case_id='edit_light_ball',
        seed=7102,
        dsl='SET ball.mass TIMES 0.3',
        edit_summary=(
            'Ball 0.62 -> 0.186 kg at the same 7.2 m/s. A fifth of the momentum '
            'arrives on the same frame (11) and barely moves the leaf: 9.92 deg '
            'of travel instead of 44.93, so it hangs 35.08 deg open and never '
            'reaches the jamb. The lighter ball rebounds faster (4.23 m/s) and '
            'runs 6.76 m of floor.'
        ),
    ),
    EditCase(
        case_id='edit_heavy_door',
        seed=7103,
        dsl='SET door.mass TIMES 10',
        edit_summary=(
            'Leaf 12 -> 120 kg, ten times the inertia. The same impulse buys a '
            'tenth of the spin: 10.64 deg of travel, so the leaf is still 34.36 '
            'deg open at the end of the clip and only comes to rest on frame 77 '
            'against 33. The ball rebounds harder (4.33 m/s) because the leaf '
            'takes less of its normal velocity, and that pace carries it 6.78 m.'
        ),
    ),
    EditCase(
        case_id='edit_stiff_hinge',
        seed=7104,
        dsl='SET door.friction TIMES 4',
        edit_summary=(
            'Hinge friction 1.0 -> 4.0 N m. A four times larger braking torque '
            'eats the swing in a quarter of the distance: 25.16 deg of travel, '
            'at rest on frame 29 with the leaf 19.84 deg open instead of shut. '
            'The ball is pixel-identical to the source -- it has left the leaf '
            'two frames after impact, so nothing the hinge does afterwards can '
            'reach it.'
        ),
    ),
    EditCase(
        case_id='edit_slow_throw',
        seed=7105,
        dsl='SET ball.speed TIMES 0.5',
        edit_summary=(
            'Thrown at 3.6 m/s instead of 7.2 -- half the launch speed, and the '
            'ball now drops onto the leaf nine frames later (impact 20 instead '
            'of 11). It still gets there, but it arrives lower and slower, so '
            'the leaf travels 22.06 deg and settles 22.94 deg open; the slower '
            'rebound (3.84 m/s) dies after 5.52 m of floor, on frame 53.'
        ),
    ),
    EditCase(
        case_id='edit_stiff_hinge_late',
        seed=7106,
        dsl='SET door.friction TIMES 5 AT FRAME 12',
        edit_summary=(
            'Frames 1-12 are the source clip by construction: the impact is on '
            'frame 11, so at frame 12 the leaf has only just started to move '
            '(41.28 deg, 0.99 rad/s) and the hinge friction is still the source '
            '1.0 N m. At frame 12 it is written into the running simulation as '
            '5.0 N m and the swing dies at 23.05 deg of travel, at rest on '
            'frame 26 with the leaf 21.95 deg open instead of shut.'
        ),
    ),
)


DESCRIPTION = {
    'vague': {
        'zh': '在卧室里把篮球扔向一扇半开着的门，球把门撞得几乎关上，自己从门板上弹回来，在木地板上滚了一段后停住。',
        'en': 'A basketball is thrown across a bedroom at a half-open door, knocks it almost shut, rebounds off the leaf and rolls across the floor until it stops.',
    },
    'quantitative': {
        'zh': (f'篮球以 {BASELINE_PHYSICS["ball_speed"]:g} m/s 从门前抛出，第 11 帧撞上门板。'
               f'质量 {BASELINE_PHYSICS["door_mass"]:g} kg 的门从 '
               f'{BASELINE_PHYSICS["door_start_angle_deg"]:g}° 摆到 0.07°（行程 44.93°，'
               f'峰值角速度 1.01 rad/s），第 33 帧起静止；'
               f'球以 3.92 m/s 离开碰撞，在地面上滚过 6.27 m。'),
        'en': (f'The {BASELINE_PHYSICS["ball_mass"]:g} kg ball is thrown at {BASELINE_PHYSICS["ball_speed"]:g} m/s '
               f'and hits the leaf on frame 11. The {BASELINE_PHYSICS["door_mass"]:g} kg leaf swings from '
               f'{BASELINE_PHYSICS["door_start_angle_deg"]:g} deg to 0.07 deg (44.93 deg of travel, peaking at '
               '1.01 rad/s) and is at rest from frame 33; the ball leaves the impact at 3.92 m/s and '
               'traces 6.27 m of floor.'),
    },
}


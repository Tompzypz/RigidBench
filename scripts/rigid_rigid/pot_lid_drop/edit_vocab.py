"""Edit vocabulary for the pot_lid_drop scene.

The lid is the only body that moves, so it is the only editable object: the
pot, the counter and the kitchen are the set it falls into, not props. The
three knobs the scene exposes are mass, restitution and rolling friction.

Restitution controls the rebound; friction controls the settling motion.
Measurements for the aligned full-mesh collision model are recorded in the
render validation file.

The baseline is read from ``scenario.json`` rather than copied here. A scene
whose vocabulary and scenario disagree produces prompts that describe a video
nobody rendered, and that is exactly the bug this avoids: change the scene's
physics and the DSL, the prompts and the diffs follow.
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

HERE = Path(__file__).resolve().parent
import pcve_edit_dsl as dsl  # noqa: E402
import scene_config  # noqa: E402


SCENARIO = scene_config.load_scenario()
BASELINE_PHYSICS = SCENARIO['physics']


OBJECTS = {
    'lid': {'zh': '锅盖', 'en': 'the pot lid'},
    'world': {'zh': '世界（重力场）', 'en': 'the world'},
    'bowl': {'zh': '碗', 'en': 'a bowl'},
}
# Deliberately NOT editable: the pot, the counter and the floor. They are the
# kitchen the lid lands in, not props.


PROPERTIES = {
    'mass':             dsl.PropertySpec('scalar', 'kg',    '质量',         'mass'),
    'rolling_friction': dsl.PropertySpec('scalar', '',      '滚动摩擦因数', 'rolling friction coefficient'),
    'restitution':      dsl.PropertySpec('scalar', '',      '弹性因数',     'restitution'),
    'gravity':          dsl.PropertySpec('scalar', 'm/s²',  '重力加速度',   'gravity magnitude'),
}

SIM_BINDINGS = {
    ('lid', 'mass'):             dsl.SimBinding('lid_mass'),
    ('lid', 'rolling_friction'): dsl.SimBinding('lid_rolling_friction'),
    ('lid', 'restitution'):      dsl.SimBinding('lid_restitution'),
    # Gravity is a world-level knob bound straight onto the scenario's
    # gravity_z physics key, the same way ball_block_building binds
    # world.gravity -> gravity_strength.
    ('world', 'gravity'):        dsl.SimBinding('gravity_z'),
}


DELETE_BINDINGS: dict[str, dsl.DeleteBinding] = {}


# 4.0 s at 24 fps, which is what build_pcve_pot_lid_drop.py renders. An "AT
# FRAME n" edit is bounded by this, and the vague prompt reads n against it to
# say whether the edit lands early, midway or late in the clip.
TOTAL_FRAMES = 96


# The bowl ADD's anchor set: the DSL only places an ADD strictly between two
# endpoints, so the 'world' anchor sits at 2P - lid_start (P = the baseline
# lid's measured resting point); the MIDPOINT of that anchor and the lid's
# start anchor resolves back to exactly P, on the floor. The bowl's material
# defaults ride along in the AddBinding; the collision builder in the
# simulator reads the same keys.
_BOWL_LANDING = [0.174, 0.243, 0.0]
_WORLD_ADD_ANCHOR = [2.0 * _BOWL_LANDING[0] - 0.0,
                     2.0 * _BOWL_LANDING[1] - 0.0,
                     2.0 * _BOWL_LANDING[2] - 1.16]
# The bowl reuses kitchen_tableware_collision's ceramic rice bowl: a shared
# lathe cross-section (closed solid, foot -> lip -> inner floor) whose convex
# hull is the collision body in that scene. The simulator builds the hull from
# the same PROFILE scaled to bowl_radius_m, and the renderer lathes the same
# PROFILE for the visible mesh, so visual and collision shapes cannot drift
# apart. Unlike the earlier static compound this bowl has mass -- the falling
# lid genuinely knocks it over, which is the visible proof of contact.
BOWL_PROFILE_BASE_RADIUS_M = 0.085
BOWL_COM_HEIGHT_M = 0.018
BOWL_PROFILE_TOP_Z_M = 0.042
BOWL_PROFILE = ((0.,.004),(.030,.004),(.037,.000),(.044,.000),(.046,.003),(.047,.008),
                (.055,.012),(.067,.020),(.078,.030),(.0835,.036),(.085,.039),
                (.0845,.041),(.0825,.042),(.0805,.040),(.077,.034),(.066,.025),
                (.054,.019),(.043,.014),(.030,.011),(0.,.011))
_BOWL_DEFAULTS = (
    ('bowl_mass_kg', 0.08),
    ('bowl_radius_m', 0.11),
    ('bowl_restitution', 0.2),
    ('bowl_friction', 0.4),
)

VOCAB = dsl.Vocabulary(
    objects=OBJECTS,
    properties=PROPERTIES,
    sim_bindings=SIM_BINDINGS,
    delete_bindings=DELETE_BINDINGS,
    baseline_physics={
        **BASELINE_PHYSICS,
        'bowl_presence': [0],
        'bowl_start_position': list(_BOWL_LANDING),
        'world_add_anchor': list(_WORLD_ADD_ANCHOR),
        'lid_start_position': [0.0, 0.0, 1.16],
        **dict(_BOWL_DEFAULTS),
    },
    total_frames=TOTAL_FRAMES,
    geometry={
        'lid': dsl.GeometryAnchor('lid_start_position', 'lid_radius_m'),
        'world': dsl.GeometryAnchor('world_add_anchor', 'bowl_radius_m'),
        'bowl': dsl.GeometryAnchor('bowl_start_position', 'bowl_radius_m'),
    },
    add_bindings={'bowl': dsl.AddBinding(
        presence_key='bowl_presence', presence_index=0,
        location_key='bowl_start_position', value_when_present=1,
        defaults=_BOWL_DEFAULTS)},
)


# Exactly five single-variable edits. Four hold from frame 1; the last one
# lands partway through -- the baseline lid first touches down during frame
# 13 and its rebound carries it up through frame 14, so at the top of frame
# 14 the schedule switches gravity off inside the running simulation: the
# free fall, the impact and the start of the rebound (frames 1-13) are the
# baseline clip bit for bit, and from there the lid coasts upward instead of
# ever coming back down.
EDIT_CASES = [
    ('edit_light_gravity', 'SET world.gravity TIMES 0.3'),
    ('edit_add_bowl_at_landing', 'ADD bowl BETWEEN lid AND world AT MIDPOINT HINT "在锅盖落点处"'),
    ('edit_slick_rim', 'SET lid.rolling_friction TIMES 0.1'),
    ('edit_bouncy_lid', 'SET lid.restitution TO 0.45'),
    ('edit_zero_gravity_timed', 'SET world.gravity TO 0 AT FRAME 14'),
]

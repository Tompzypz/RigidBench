"""Object-level SET/DELETE bindings, matching the older rigid-body scenes."""
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



import runtime_support
import pcve_edit_dsl as dsl
from scene_config import BASELINE_PHYSICS, TOTAL_FRAMES
from scene_geometry import RADIUS

OBJECTS = {
    'ball_a': {'zh': '初始位于左侧的足球', 'en': 'the initially left soccer ball'},
    'ball_b': {'zh': '初始位于右侧的足球', 'en': 'the initially right soccer ball'},
    'ball_c': {'zh': '额外加入的静止足球', 'en': 'an additional stationary soccer ball'},
}
PROPERTIES = {
    'mass': dsl.PropertySpec('scalar', 'kg', '质量', 'mass'),
    'friction': dsl.PropertySpec('scalar', '', '摩擦系数', 'friction coefficient'),
    'restitution': dsl.PropertySpec('scalar', '', '恢复系数', 'restitution'),
    'initial_velocity': dsl.PropertySpec('scalar', 'm/s', '沿草地 X 轴的初速度',
                                         'initial velocity along the field X axis'),
    'spin': dsl.PropertySpec('scalar', 'rad/s', '绕水平 Y 轴的自旋角速度',
                             'spin rate about the horizontal Y axis'),
}
SIM_BINDINGS = {}
for obj, prefix, speed_key in (
    ('ball_a', 'driver', 'initial_velocity'),
    ('ball_b', 'receiver', 'receiver_initial_velocity'),
):
    SIM_BINDINGS[(obj, 'mass')] = dsl.SimBinding(f'{prefix}_mass')
    SIM_BINDINGS[(obj, 'restitution')] = dsl.SimBinding(f'{prefix}_restitution')
    SIM_BINDINGS[(obj, 'initial_velocity')] = dsl.SimBinding(speed_key)
    # Like ball_block, lateral and rolling friction form ONE semantic knob.
    # Lateral friction alone does not slow a ball that rolls without slipping.
    SIM_BINDINGS[(obj, 'friction')] = dsl.CompoundBinding(components=(
        dsl.SimBinding(f'{prefix}_friction'),
        dsl.SimBinding(f'{prefix}_rolling_friction'),
    ))
    # Spin is a timed-only knob: the simulator writes the initial spin as
    # speed / RADIUS, so the vocabulary's baseline view carries exactly that
    # value under the binding key a timed schedule writes.
    SIM_BINDINGS[(obj, 'spin')] = dsl.SimBinding(f'{prefix}_angular_velocity')
DELETE_BINDINGS = {
    key: dsl.DeleteBinding('ball_active', index=i, value_when_removed=0)
    for i, key in enumerate(OBJECTS)
}
# ADD resolves its position from where the two moving balls start: the anchor
# keys live on the scenario's physics dict (the simulator reads the third
# ball's spawn point from the same keys), and the vocabulary's baseline view
# carries the third ball's slot (off at baseline) plus its material defaults.
_ball_c_defaults = (
    ('ball_c_mass', BASELINE_PHYSICS['driver_mass']),
    ('ball_c_friction', BASELINE_PHYSICS['driver_friction']),
    ('ball_c_rolling_friction', BASELINE_PHYSICS['driver_rolling_friction']),
    ('ball_c_restitution', BASELINE_PHYSICS['driver_restitution']),
)
VOCAB = dsl.Vocabulary(objects=OBJECTS, properties=PROPERTIES,
                       sim_bindings=SIM_BINDINGS, delete_bindings=DELETE_BINDINGS,
                       baseline_physics={
                           **BASELINE_PHYSICS,
                           # Spin baseline values the simulator writes at
                           # creation (speed / RADIUS, signed by travel
                           # direction); TIMES edits on spin resolve against
                           # these, and the timed schedule writes the result.
                           'driver_angular_velocity': BASELINE_PHYSICS['initial_velocity'] / RADIUS,
                           'receiver_angular_velocity': BASELINE_PHYSICS['receiver_initial_velocity'] / RADIUS,
                           'ball_c_start_position': [0., 0., RADIUS],
                           'soccer_ball_radius_m': RADIUS,
                           **dict(_ball_c_defaults),
                       },
                       total_frames=TOTAL_FRAMES,
                       geometry={
                           'ball_a': dsl.GeometryAnchor('ball_a_anchor_position', 'soccer_ball_radius_m'),
                           'ball_b': dsl.GeometryAnchor('ball_b_anchor_position', 'soccer_ball_radius_m'),
                           'ball_c': dsl.GeometryAnchor('ball_c_start_position', 'soccer_ball_radius_m'),
                       },
                       add_bindings={'ball_c': dsl.AddBinding(
                           presence_key='ball_active', presence_index=2,
                           location_key='ball_c_start_position', value_when_present=1,
                           defaults=_ball_c_defaults)})

# One single-variable edit per case. Three hold from frame 1; the ADD places
# a stationary third ball exactly where the two moving ones will meet, so
# both runners hit it instead of each other; the last one lands partway
# through -- the baseline collision resolves during frame 31 and by frame 32
# both balls are nearly stopped, so at the top of frame 32 the schedule
# multiplies the receiver's spin by ten inside the running simulation: a ball
# that had almost stopped is suddenly overspun at about -57 rad/s, and
# friction converts that into a violent skid -- the receiver surges away
# while the driver, untouched since the impact, stays put.
EDIT_CASES = [
    ('edit_fast_driver', 'SET ball_a.initial_velocity TIMES 2'),
    ('edit_heavy_receiver', 'SET ball_b.mass TIMES 3'),
    ('edit_dead_receiver', 'SET ball_b.restitution TIMES 0.1'),
    ('edit_add_midpoint_ball', 'ADD ball_c BETWEEN ball_a AND ball_b AT MIDPOINT'),
    ('edit_overspin_receiver_timed', 'SET ball_b.spin TIMES 10 AT FRAME 32'),
]

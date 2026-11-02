"""Use the project's shared PCVE DSL; all five edits start at frame one."""
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


# The edit vocabulary for this scene: what a viewer of the clip may change, how
# each change lands in the simulator's own parameters, and the five edits the
# suite ships. Everything downstream (prompts, scenario overrides, physics_diff)
# is generated from this declaration by the shared DSL.
import sys
from pathlib import Path
from dataclasses import dataclass

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import pcve_edit_dsl as dsl
from scene_config import load_scenario

BASELINE_PHYSICS = load_scenario()['physics']
TOTAL_FRAMES = round(BASELINE_PHYSICS['fps'] * BASELINE_PHYSICS['duration_sec'])

OBJECTS = {'ball': {'zh': '篮球', 'en': 'the basketball'},
           'world': {'zh': '场景', 'en': 'the scene'}}

PROPERTIES = {
    'mass': dsl.PropertySpec('scalar', 'kg', '质量', 'mass'),
    'initial_velocity': dsl.PropertySpec('scalar', 'm/s', '初始速度大小',
                                         'initial speed', initial_condition=True),
    'restitution': dsl.PropertySpec('scalar', '', '恢复系数', 'restitution'),
    'friction': dsl.PropertySpec('scalar', '', '摩擦系数', 'friction coefficient'),
    'spin': dsl.PropertySpec('scalar', '×', '自旋角速度', 'spin rate'),
    'gravity': dsl.PropertySpec('scalar', 'm/s²', '重力加速度', 'gravity'),
}

SIM_BINDINGS = {('ball', prop): dsl.SimBinding(key) for prop, key in {
    'mass': 'ball_mass', 'initial_velocity': 'ball_initial_speed',
    'restitution': 'ball_restitution', 'friction': 'ball_friction',
    # The ball carries real angular velocity (pure rolling at launch), so a spin
    # edit is quoted as a multiple of the rotation it already has.
    'spin': 'ball_spin_scale',
}.items()}
SIM_BINDINGS[('world', 'gravity')] = dsl.SimBinding('gravity_z')

VOCAB = dsl.Vocabulary(objects=OBJECTS, properties=PROPERTIES,
                       sim_bindings=SIM_BINDINGS, delete_bindings={},
                       baseline_physics=BASELINE_PHYSICS, total_frames=TOTAL_FRAMES)


@dataclass(frozen=True)
class EditCase:
    """One instruction, plus the outcome a viewer is meant to see."""
    case_id: str
    dsl: str
    summary: str


# The first wall is struck on frame 21 and the second on frame 32 of the
# baseline, so a mid-clip spin edit lands on a ball that is already rolling:
# the first 27 frames are the source video frame for frame, and only the rest of
# the roll is redefined.
EDIT_CASES = (
    EditCase('edit_fast_ball', 'SET ball.initial_velocity TIMES 2',
             '篮球初始速度加倍到 4 m/s：两面墙的反弹提前到约第 11、16 帧，出墙角后滚到房间中部，'
             '终止位置比原片远约 3 m。'),
    EditCase('edit_slow_ball', 'SET ball.initial_velocity TIMES 0.3',
             '篮球初始速度降到 0.6 m/s：滚动摩擦在球抵达墙角之前就把它停住，全程一次墙都没撞'
             '（原片第 21、32 帧两度反弹），总路径由 3.40 m 缩到 1.21 m，球停在房间中部，'
             '终止位置离原片约 1.27 m。'),
    EditCase('edit_slick_ball', 'SET ball.friction TIMES 0.15',
             '篮球摩擦系数降到 0.15 倍：墙面切向冲量变小，球在两次贴墙中打滑，'
             '反弹后的回程更长（路径 3.4 m 增至 4.3 m）。'),
    EditCase('edit_low_gravity', 'SET world.gravity TIMES 0.4',
             '重力加速度降到 0.4 倍（-9.81 降至 -3.924 m/s²）：压在地面上的正压力变小、滚动摩擦随之变小，'
             '球一路滑得更远，第二次撞墙提前到第 31 帧，总路径由 3.40 m 增至 3.83 m，终止位置外移 0.46 m。'),
    EditCase('edit_spin_midway', 'SET ball.spin TIMES 5 AT FRAME 28',
             '在第 28 帧（第一次撞墙之后、第二次撞墙之前）把球的自旋乘 5（8.8 rad/s 增至 44.2 rad/s）：'
             '球面相对地面立刻打滑，摩擦把自旋转成前进速度，球被"抽"着冲向第二面墙，'
             '第二次撞墙提前到第 31 帧，终止位置比原片远 1.9 m；前 27 帧与原片完全一致。'),
)

DESCRIPTION = {
    'vague': {'zh': '篮球斜向滚入室内直角墙角，先后从两面墙反弹后滚回房间中部。',
              'en': 'A basketball rolls into a room corner, rebounds off one wall and then the other, '
                    'and rolls back out into the room.'},
    'quantitative': {
        'zh': f"质量 {BASELINE_PHYSICS['ball_mass']:g} kg、半径 {BASELINE_PHYSICS['ball_radius']:g} m 的篮球"
              f"以 {BASELINE_PHYSICS['ball_initial_speed']:g} m/s 沿斜向滚入 8 m × 8 m 的房间墙角，"
              f"恢复系数 {BASELINE_PHYSICS['ball_restitution']:g}、摩擦系数 {BASELINE_PHYSICS['ball_friction']:g}；"
              f"约第 21 帧撞上第一面墙，第 32 帧撞上第二面墙。",
        'en': f"A {BASELINE_PHYSICS['ball_mass']:g} kg basketball of radius {BASELINE_PHYSICS['ball_radius']:g} m "
              f"rolls into the corner of an 8 m by 8 m room at {BASELINE_PHYSICS['ball_initial_speed']:g} m/s with "
              f"restitution {BASELINE_PHYSICS['ball_restitution']:g} and friction {BASELINE_PHYSICS['ball_friction']:g}; "
              f"it meets the first wall around frame 21 and the second around frame 32."},
}

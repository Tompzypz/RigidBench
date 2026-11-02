"""Editable objects and simulator bindings, using the shared PCVE edit DSL."""
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
# suite ships. Prompts, scenario overrides and physics_diff all come from here.
import sys
from pathlib import Path
from dataclasses import dataclass

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# Match the older scenes: share the parser, binding rules and prompt renderer.
import pcve_edit_dsl as dsl

try:
    import scene_config
except ImportError:
    import scene_config

BASELINE_PHYSICS = scene_config.read_json(scene_config.SCENARIO_PATH)['physics']
TOTAL_FRAMES = round(BASELINE_PHYSICS['fps'] * BASELINE_PHYSICS['duration_sec'])

OBJECTS = {
    'door': {'zh': '房门', 'en': 'the hinged door'},
    'ball': {'zh': '篮球', 'en': 'the basketball'},
}

PROPERTIES = {
    'mass': dsl.PropertySpec('scalar', 'kg', '质量', 'mass'),
    'initial_velocity': dsl.PropertySpec('scalar', 'rad/s', '初始角速度',
                                          'initial angular velocity', initial_condition=True),
    'hinge_friction': dsl.PropertySpec('scalar', 'N·m', '铰链摩擦',
                                        'hinge friction torque'),
}

SIM_BINDINGS = {
    ('door', 'initial_velocity'): dsl.SimBinding('door_initial_velocity'),
    ('door', 'mass'): dsl.SimBinding('door_mass'),
    ('door', 'hinge_friction'): dsl.SimBinding('door_hinge_friction'),
    ('ball', 'mass'): dsl.SimBinding('ball_mass'),
}
# Removing the ball leaves the initially moving door as a useful control.
DELETE_BINDINGS = {'ball': dsl.DeleteBinding('ball_active', index=0)}

VOCAB = dsl.Vocabulary(objects=OBJECTS, properties=PROPERTIES,
                       sim_bindings=SIM_BINDINGS, delete_bindings=DELETE_BINDINGS,
                       baseline_physics=BASELINE_PHYSICS, total_frames=TOTAL_FRAMES)


@dataclass(frozen=True)
class EditCase:
    """One instruction, plus the outcome a viewer is meant to see."""
    case_id: str
    dsl: str
    summary: str


# The leaf reaches the ball on frame 5 of the baseline (about 33 deg open), so a
# 3 lands while it is still swinging: the first two frames are the source video
# and the swing that follows is the edited one.
EDIT_CASES = (
    EditCase('edit_fast_door', 'SET door.initial_velocity TIMES 2',
             '门初始角速度加倍到 3.3 rad/s：约第 3 帧就撞上篮球，球被甩到 4.3 m 外（原片 1.7 m），'
             '门冲到 105 度限位后回弹，最后停在 102 度。'),
    EditCase('edit_heavy_door', 'SET door.mass TIMES 4',
             '门质量加到 32 kg、角速度不变：转动惯量增大，撞击篮球时冲量更大，球滚出 3.1 m，'
             '门被 105 度限位挡住并停在那里。'),
    EditCase('edit_heavy_ball', 'SET ball.mass TIMES 6',
             '篮球质量加到 3.72 kg：球只被推出去 0.73 m（原片 1.7 m），门也被这颗重球顶住，'
             '只开到约 37 度就停住。'),
    EditCase('edit_remove_ball', 'DELETE ball',
             '把篮球整个移出场景：门在没有阻挡的情况下摆到 101 度才被铰链摩擦停住，'
             '画面里从头到尾没有球。'),
    EditCase('edit_stiff_hinge_midway', 'SET door.hinge_friction TIMES 15 AT FRAME 3',
             '在第 3 帧开始时（门刚摆到约 22 度，还没碰到球）把铰链摩擦从 2 N·m 提到 30 N·m：'
             '门在约 27.6 度、第 5 帧就停住，原片这一帧球被撞出去，这里球始终没动；前 2 帧与原片逐比特一致。'),
)

DESCRIPTION = {
    'vague': {'zh': '房门向屋内打开，撞动地面上静止的篮球，篮球滚进房间。',
              'en': 'A hinged door swings into the room, strikes a stationary basketball and sends it rolling.'},
    'quantitative': {
        'zh': f"质量 {BASELINE_PHYSICS['door_mass']:g} kg 的房门从 {BASELINE_PHYSICS['door_start_angle_deg']:g} 度"
              f"以 {BASELINE_PHYSICS['door_initial_velocity']:g} rad/s 向屋内摆开，铰链摩擦 "
              f"{BASELINE_PHYSICS['door_hinge_friction']:g} N·m；质量为 "
              f"{BASELINE_PHYSICS['ball_mass']:g} kg 的篮球静止在门前，约第 5 帧被门撞到。",
        'en': f"A {BASELINE_PHYSICS['door_mass']:g} kg door swings open from "
              f"{BASELINE_PHYSICS['door_start_angle_deg']:g} deg at "
              f"{BASELINE_PHYSICS['door_initial_velocity']:g} rad/s against a "
              f"{BASELINE_PHYSICS['door_hinge_friction']:g} N·m hinge friction; a "
              f"{BASELINE_PHYSICS['ball_mass']:g} kg basketball rests in its path and is struck around frame 5."},
}

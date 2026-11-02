"""Only the three requested physical edits are exposed."""
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


# The edit vocabulary for this scene: objects a viewer can name, the property
# each one exposes, where that property lives in the simulator's parameters, and
# the five edits the suite ships. Prompts, overrides and physics_diff are all
# generated from this declaration by the shared DSL.
import sys
from pathlib import Path
from dataclasses import dataclass

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import pcve_edit_dsl as dsl
from scene_config import BASELINE_PHYSICS, TOTAL_FRAMES
from scene_geometry import COUNT

# A timed edit travels as a schedule inside the physics block, so the key is
# declared on the baseline the validator compares against.
BASELINE_PHYSICS.setdefault('timed_edits', [])

OBJECTS = {
    'eraser': {'zh': '板擦', 'en': 'the board eraser'},
    'chalk_boxes': {'zh': '粉笔盒堆叠', 'en': 'the chalk-box stack'},
}

PROPERTIES = {
    'initial_velocity': dsl.PropertySpec('scalar', 'm/s', '初速度大小',
                                         'initial speed', initial_condition=True),
    'friction': dsl.PropertySpec('scalar', '', '摩擦因数', 'friction coefficient'),
}

SIM_BINDINGS = {
    ('eraser', 'initial_velocity'): dsl.SimBinding('eraser_speed'),
    ('eraser', 'friction'): dsl.SimBinding('eraser_friction'),
    ('chalk_boxes', 'friction'): dsl.SimBinding('box_friction'),
}

VOCAB = dsl.Vocabulary(objects=OBJECTS, properties=PROPERTIES,
                       sim_bindings=SIM_BINDINGS, delete_bindings={},
                       baseline_physics=BASELINE_PHYSICS, total_frames=TOTAL_FRAMES)


@dataclass(frozen=True)
class EditCase:
    """One instruction, plus the outcome a viewer is meant to see."""
    case_id: str
    dsl: str
    summary: str


# The eraser reaches the bottom carton on frame 12 of the baseline (0.443 s) and
# then drags it for a third of a second, so a timed edit at frame 20 lands after
# the sliding is already under way: frames 1..19 are the source video frame for
# frame, and only the tail of the extraction is redefined.
EDIT_CASES = (
    EditCase('edit_fast_eraser', 'SET eraser.initial_velocity TIMES 2',
             '板擦初速度加倍到 5.6 m/s：约第 6 帧就撞上粉笔堆（原片第 12 帧），底盒被撞下桌面，'
             '板擦自己也跟着冲出去，两者越过地板边缘继续下落；上层盒留在桌面原位，'
             '整段视频的差异量达 39.8 m。'),
    EditCase('edit_slow_eraser', 'SET eraser.initial_velocity TIMES 0.5',
             '板擦初速度降到 1.4 m/s：桌面摩擦在抵达粉笔堆前就把它停住，全程没有任何接触，'
             '两只粉笔盒保持原位，只有板擦滑到桌子中段停住。'),
    EditCase('edit_slick_eraser', 'SET eraser.friction TIMES 0.2',
             '板擦与桌面的摩擦因数降到 0.2 倍：板擦几乎不减速，撞上底盒后继续推着它滑过桌面，'
             '底盒被推离原位 2.5 m 以上。'),
    EditCase('edit_slippery_boxes', 'SET chalk_boxes.friction TIMES 0.15',
             '粉笔盒摩擦因数降到 0.15 倍：底盒被抽出后滑得更远（约 0.93 m，原片 0.46 m），'
             '上层盒仍落下一层停稳。'),
    EditCase('edit_frictionless_midway', 'SET chalk_boxes.friction TO 0 AT FRAME 20',
             '先让板擦推着底盒靠摩擦滑了约 0.35 s，到第 20 帧把粉笔盒摩擦因数直接归零：'
             '底盒失去桌面约束，被板擦一路推到桌沿、翻下桌面滑到 2.7 m 外，'
             '上层盒不再被带着走，原地落到桌面；前 19 帧与原片完全一致。'),
)

DESCRIPTION = {
    'vague': {'zh': '板擦横向撞开两只叠放粉笔盒的下层盒，上层盒落下一层后停住。',
              'en': 'A board eraser swipes the bottom carton out from under a stack of two chalk boxes; '
                    'the upper carton drops one level and stops.'},
    'quantitative': {
        'zh': f"质量 {BASELINE_PHYSICS['eraser_mass']:g} kg 的板擦以 {BASELINE_PHYSICS['eraser_speed']:g} m/s "
              f"撞击 {COUNT} 只叠放粉笔盒的底盒，盒间与盒桌摩擦因数为 {BASELINE_PHYSICS['box_friction']:g}；"
              f"板擦约在第 12 帧接触底盒。",
        'en': f"A {BASELINE_PHYSICS['eraser_mass']:g} kg eraser strikes the bottom carton of a {COUNT}-box stack "
              f"at {BASELINE_PHYSICS['eraser_speed']:g} m/s; box friction is {BASELINE_PHYSICS['box_friction']:g} "
              f"and the first contact lands near frame 12."},
}

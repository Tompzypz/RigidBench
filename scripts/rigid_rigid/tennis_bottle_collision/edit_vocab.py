"""Explicit spatial additions plus independent physical and deletion edits."""
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
# Imported through the same alias path the simulate/build/render scripts use,
# so the vocabulary and the validator read one shared BASELINE_PHYSICS.
from scene_config import BASELINE_PHYSICS
from scene_geometry import SIM_HZ

# The suite's videos are 4 s at 24 fps; the vocabulary needs the frame count
# to accept AT FRAME edits.
TOTAL_FRAMES = 96

VOCAB = dsl.Vocabulary(
    objects={'tennis_ball': {'zh': '网球', 'en': 'the tennis ball'},
             'bottles': {'zh': '两个塑料瓶', 'en': 'the two plastic bottles'},
             'bottle_left': {'zh': '左侧塑料瓶', 'en': 'the left plastic bottle'},
             'bottle_right': {'zh': '右侧塑料瓶', 'en': 'the right plastic bottle'},
             'bottle_added': {'zh': '新增的塑料瓶', 'en': 'an additional plastic bottle'}},
    properties={'mass': dsl.PropertySpec('scalar', 'kg', '质量', 'mass'),
                'initial_velocity': dsl.PropertySpec('scalar', 'm/s', '初速度', 'initial speed', initial_condition=True),
                'restitution': dsl.PropertySpec('scalar', '', '恢复系数', 'restitution')},
    sim_bindings={('tennis_ball', 'mass'): dsl.SimBinding('ball_mass'),
                  ('tennis_ball', 'initial_velocity'): dsl.SimBinding('initial_velocity'),
                  ('bottles', 'mass'): dsl.SimBinding('bottle_mass'),
                  ('bottles', 'restitution'): dsl.SimBinding('bottle_restitution')},
    delete_bindings={'bottle_left': dsl.DeleteBinding('bottle_presence', 0, 0),
                     'bottle_right': dsl.DeleteBinding('bottle_presence', 1, 0)},
    geometry={'tennis_ball': dsl.GeometryAnchor('ball_add_anchor_position', 'ball_radius'),
              'bottle_left': dsl.GeometryAnchor('bottle_left_position', 'bottle_radius'),
              'bottle_added': dsl.GeometryAnchor('bottle_added_position', 'bottle_radius')},
    add_bindings={'bottle_added': dsl.AddBinding(
        presence_key='bottle_presence', presence_index=2,
        location_key='bottle_added_position')},
    baseline_physics=BASELINE_PHYSICS, total_frames=TOTAL_FRAMES)

EDIT_CASES = [
    ('edit_fast_ball', 'SET tennis_ball.initial_velocity TIMES 3'),
    ('edit_heavy_bottles', 'SET bottles.mass TIMES 10'),
    ('edit_remove_far_bottle', 'DELETE bottle_right'),
    ('edit_add_lane_bottle', 'ADD bottle_added BETWEEN tennis_ball AND bottle_left AT MIDPOINT'),
    ('edit_heavy_bottles_midfall', 'SET bottles.mass TIMES 10 AT FRAME 16'),
]

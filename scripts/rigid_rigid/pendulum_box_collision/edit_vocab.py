"""The four requested knobs, and nothing else, expressed in the edit DSL.

Two bodies carry two properties each: the bob's mass and its speed along the
arc, the block's mass and its speed along the bench. Restitution, friction,
thread length and the release geometry are deliberately *not* in the
vocabulary, so no edit can quietly change two things at once.

``initial_velocity`` is bound to a scalar speed, not a vector. Both bodies
start on the axis of the impact and their directions are fixed by the scene
(the block towards +X, the bob towards -X), so a vector edit would only offer
the chance to write a number that the simulator ignores along two of its
components. The prompt therefore reads "initial speed", which is exactly the
quantity the parameter names.
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
from scene_config import BASELINE_PHYSICS, PHYSICS_LIMITS, TOTAL_FRAMES  # noqa: E402

# Scene-only edit controls, registered on the embedded schema's own dicts so
# its validator (which requires the physics dict to carry exactly the keys of
# BASELINE_PHYSICS, each within PHYSICS_LIMITS) accepts them:
#   * ``restitution`` joins the editable parameters -- the pair coefficient the
#     simulator used to hard-code as a module constant, now an ordinary physics
#     key so it can be edited whole-clip or mid-run;
#   * ``timed_edits`` carries the mid-run schedule the simulator applies frame
#     by frame.

VOCAB = dsl.Vocabulary(
    objects={'bob': {'zh': '摆锤', 'en': 'the pendulum bob'},
             'wooden_block': {'zh': '木盒', 'en': 'the wooden block'},
             'pair': {'zh': '摆锤与木盒之间的碰撞', 'en': 'the bob-block collision'}},
    properties={'mass': dsl.PropertySpec('scalar', 'kg', '质量', 'mass'),
                'initial_velocity': dsl.PropertySpec('scalar', 'm/s', '初速度大小', 'initial speed'),
                'restitution': dsl.PropertySpec('scalar', '', '碰撞恢复系数', 'collision restitution coefficient')},
    sim_bindings={('bob', 'mass'): dsl.SimBinding('bob_mass'),
                  ('bob', 'initial_velocity'): dsl.SimBinding('bob_speed'),
                  ('wooden_block', 'mass'): dsl.SimBinding('box_mass'),
                  ('wooden_block', 'initial_velocity'): dsl.SimBinding('box_speed'),
                  ('pair', 'restitution'): dsl.SimBinding('restitution')},
    delete_bindings={}, baseline_physics=BASELINE_PHYSICS, geometry={},
    total_frames=TOTAL_FRAMES)

# Five cases, one number each: the four original knobs once (at their
# exaggerated settings -- a 4 kg bob, a bob released at rest, a 2 kg block, a
# 3.25 m/s block), then a timed pair-restitution drop to near zero that lands
# between the first face impact (about frame 15) and the pendulum's return
# trip (about frame 30), so the clip runs on baseline physics up to the edit
# and the second collision lands almost perfectly dead.
# Every factor stays inside ``scene_config.PHYSICS_LIMITS``.
EDIT_CASES = (
    ('edit_heavy_bob', 'SET bob.mass TIMES 10'),
    ('edit_still_bob', 'SET bob.initial_velocity TO 0'),
    ('edit_heavy_block', 'SET wooden_block.mass TIMES 5'),
    ('edit_fast_block', 'SET wooden_block.initial_velocity TIMES 2.5'),
    ('edit_soft_bounce_timed', 'SET pair.restitution TIMES 0.1 AT FRAME 18'),
)

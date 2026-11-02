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

from pathlib import Path
import sys
import pcve_edit_dsl as dsl
from scene_config import BASELINE_PHYSICS,TOTAL_FRAMES

# Extend the embedded scene schema locally; its validator accepts only keys
# registered in BASELINE_PHYSICS, so these scene-only controls live here.

OBJECTS={
    'ball':{'zh':'木质球','en':'the wooden ball'},
    'blocks':{'zh':'积木','en':'the blocks'},
    'block_01':{'zh':'上层积木','en':'the top block'},
    'world':{'zh':'场景','en':'the scene'},
}
PROPERTIES={
    'mass':dsl.PropertySpec('scalar','kg','质量','mass'),
    'initial_velocity':dsl.PropertySpec('scalar','m/s','水平初速度','initial horizontal speed',initial_condition=True),
    'friction':dsl.PropertySpec('scalar','','摩擦系数','friction'),
    'gravity':dsl.PropertySpec('scalar','m/s²','重力加速度','gravity magnitude'),
}
SIM_BINDINGS={
    ('ball','mass'):dsl.SimBinding('ball_mass'),
    ('ball','initial_velocity'):dsl.SimBinding('ball_speed'),
    ('blocks','friction'):dsl.SimBinding('block_friction'),
    ('world','gravity'):dsl.SimBinding('gravity_strength'),
}
DELETE_BINDINGS={'block_01':dsl.DeleteBinding('block_presence',1,0)}
VOCAB=dsl.Vocabulary(objects=OBJECTS,properties=PROPERTIES,sim_bindings=SIM_BINDINGS,
    delete_bindings=DELETE_BINDINGS,baseline_physics=BASELINE_PHYSICS,total_frames=TOTAL_FRAMES)
EDIT_CASES=[
    ('edit_heavy_ball','SET ball.mass TIMES 2'),
    ('edit_fast_ball','SET ball.initial_velocity TIMES 1.5'),
    ('edit_low_block_friction','SET blocks.friction TIMES 0.4'),
    ('delete_block_01','DELETE block_01'),
    ('edit_stronger_gravity_timed','SET world.gravity TIMES 1.5 AT FRAME 12'),
]

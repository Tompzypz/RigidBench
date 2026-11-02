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

# The timed braking edit writes its schedule through this key; the simulator
# applies it inside the frame loop and carries on from the live state.

# Mass is deliberately not editable here: on this slope the trajectory is
# mass-independent (gravity, Coulomb friction and rolling resistance all scale
# with the normal force), so a mass change produces no visible difference.
OBJECTS={'ball':{'zh':'玩具球','en':'the toy ball'}}
PROPERTIES={'initial_velocity':dsl.PropertySpec('scalar','m/s','沿地面初速度','initial tangential speed'),
    'friction':dsl.PropertySpec('scalar','','滑动摩擦因数','sliding friction coefficient'),
    'rolling_resistance':dsl.PropertySpec('scalar','','滚动阻力系数','rolling resistance coefficient')}
SIM_BINDINGS={('ball','initial_velocity'):dsl.SimBinding('ball_speed'),
    ('ball','friction'):dsl.SimBinding('ball_friction'),
    ('ball','rolling_resistance'):dsl.SimBinding('ball_rolling_friction')}
VOCAB=dsl.Vocabulary(objects=OBJECTS,properties=PROPERTIES,sim_bindings=SIM_BINDINGS,delete_bindings={},baseline_physics=BASELINE_PHYSICS,total_frames=TOTAL_FRAMES)
EDIT_CASES=[('edit_slow_ball','SET ball.initial_velocity TIMES 0.5'),
    ('edit_fast_ball','SET ball.initial_velocity TIMES 2.5'),
    ('edit_low_friction','SET ball.friction TIMES 0.25'),
    ('edit_high_rolling_resistance','SET ball.rolling_resistance TIMES 20'),
    ('edit_braking_timed','SET ball.rolling_resistance TIMES 10 AT FRAME 36')]

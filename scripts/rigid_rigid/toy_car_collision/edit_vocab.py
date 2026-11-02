"""The requested five single-variable edits."""
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
# so the schedule slot declared here is visible to the one shared validator.
from scene_config import BASELINE_PHYSICS,TOTAL_FRAMES

# The mid-run friction edit rides in the schedule slot declared here; the
# schema validator only accepts physics keys registered on BASELINE_PHYSICS,
# so the slot has to exist before any scenario can carry it.

VOCAB=dsl.Vocabulary(
    objects={'car_a':{'zh':'主动车','en':'the initially moving toy car'},'car_b':{'zh':'传动车','en':'the initially stationary toy car'}},
    properties={'mass':dsl.PropertySpec('scalar','kg','质量','mass'),
                'initial_velocity':dsl.PropertySpec('scalar','m/s','初速度','initial speed',initial_condition=True),
                'friction':dsl.PropertySpec('scalar','','有效地面摩擦系数','effective floor friction coefficient'),
                'speed':dsl.PropertySpec('scalar','m/s','速度','speed')},
    sim_bindings={('car_a','mass'):dsl.SimBinding('driver_mass'),('car_b','mass'):dsl.SimBinding('receiver_mass'),
                  ('car_a','initial_velocity'):dsl.SimBinding('initial_velocity'),
                  ('car_a','friction'):dsl.SimBinding('driver_friction'),
                  ('car_b','friction'):dsl.SimBinding('receiver_friction'),
                  ('car_b','speed'):dsl.SimBinding('receiver_speed_multiplier')},
    delete_bindings={'car_b':dsl.DeleteBinding('present',1)},baseline_physics=BASELINE_PHYSICS,total_frames=TOTAL_FRAMES)
EDIT_CASES=[
    ('edit_driver_mass_x3','SET car_a.mass TIMES 3'),
    ('edit_driver_speed_x3','SET car_a.initial_velocity TIMES 3'),
    ('edit_driver_friction_quarter','SET car_a.friction TIMES 0.25'),
    ('edit_delete_receiver','DELETE car_b'),
    ('edit_receiver_speed_boost_timed','SET car_b.speed TIMES 5 AT FRAME 16')]

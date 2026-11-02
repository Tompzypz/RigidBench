"""The existing project DSL generates prompts and physical overrides together."""
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
from scene_config import BASELINE_PHYSICS

# The mid-run speed edit rides in the schedule slot declared here; the schema
# validator only accepts physics keys registered on BASELINE_PHYSICS, so the
# slot has to exist before any scenario can carry it.

OBJECTS={
    'soccer':dict(zh='足球',en='the soccer ball'),
    'basketball':dict(zh='篮球',en='the basketball'),
    'platform':dict(zh='台面',en='the raised platform')}
# 'speed' and 'initial_velocity' name the same launch condition; the alias
# exists so a mid-run edit can say "half the speed" the way a viewer would,
# while the from-frame-1 edit keeps the launch wording.
PROPERTIES={
    'mass':dsl.PropertySpec('scalar','kg','质量','mass'),
    'initial_velocity':dsl.PropertySpec('scalar','m/s','初始滚动速度','initial rolling speed',initial_condition=True),
    'speed':dsl.PropertySpec('scalar','m/s','速度','speed'),
    'height':dsl.PropertySpec('scalar','m','台阶高度','step height'),
    'rolling_friction':dsl.PropertySpec('scalar','','滚动摩擦系数','rolling friction coefficient')}
VOCAB=dsl.Vocabulary(objects=OBJECTS,properties=PROPERTIES,
    delete_bindings={},
    sim_bindings={('soccer','mass'):dsl.SimBinding('soccer_mass'),
        ('basketball','mass'):dsl.SimBinding('basketball_mass'),
        ('soccer','initial_velocity'):dsl.SimBinding('launch_speed'),
        ('soccer','speed'):dsl.SimBinding('launch_speed'),
        ('platform','height'):dsl.SimBinding('step_height'),
        ('platform','rolling_friction'):dsl.SimBinding('surface_rolling_friction')},
    baseline_physics=BASELINE_PHYSICS,total_frames=96)
EDIT_CASES=[
    ('edit_soccer_mass_x3','SET soccer.mass TIMES 3'),
    ('edit_basketball_mass_x3','SET basketball.mass TIMES 3'),
    ('edit_soccer_speed_x05','SET soccer.initial_velocity TIMES 0.5'),
    ('edit_step_height_x2','SET platform.height TIMES 2'),
    ('edit_soccer_speed_halved_midrun','SET soccer.speed TIMES 0.5 AT FRAME 18')]

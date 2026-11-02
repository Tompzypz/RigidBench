"""Five representative edits: two masses, speed, restitution and target deletion."""
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
# Import through the same module alias the simulator, builder and renderer use,
# so the scene-only edits below land on the one BASELINE_PHYSICS everyone reads.
from scene_config import BASELINE_PHYSICS,PHYSICS_LIMITS,TOTAL_FRAMES

# Scene-only edit controls, registered on the embedded schema's own dicts so
# its validator (which requires the physics dict to carry exactly the keys of
# BASELINE_PHYSICS, scalars within PHYSICS_LIMITS) accepts them:
#   * ``tableware_friction`` -- the lateral friction the simulator used to
#     hard-code as a geometry constant, now an ordinary physics key so a
#     friction edit can be whole-clip or land partway through;
#   * ``timed_edits`` -- the mid-run schedule the simulator applies frame by
#     frame.

OBJECTS={'bowl_a':{'zh':'左侧青瓷碗','en':'the left celadon bowl'},
         'bowl_b':{'zh':'右侧米白瓷碗','en':'the right ivory bowl'},
         'pair':{'zh':'两只碗之间的碰撞','en':'the collision between the two bowls'},
         'bowls':{'zh':'两只碗','en':'the two bowls'}}
PROPERTIES={'mass':dsl.PropertySpec('scalar','kg','质量','mass'),
            'initial_velocity':dsl.PropertySpec('scalar','m/s','沿台面 X 轴的初速度','initial velocity along the counter X axis'),
            'restitution':dsl.PropertySpec('scalar','','碰撞恢复系数','coefficient of restitution'),
            'friction':dsl.PropertySpec('scalar','','台面摩擦系数','friction coefficient on the counter')}
SIM_BINDINGS={('bowl_a','mass'):dsl.SimBinding('driver_mass'),
              ('bowl_b','mass'):dsl.SimBinding('receiver_mass'),
              ('bowl_a','initial_velocity'):dsl.SimBinding('initial_velocity'),
              ('bowl_b','initial_velocity'):dsl.SimBinding('receiver_initial_velocity'),
              ('pair','restitution'):dsl.SimBinding('restitution'),
              ('bowls','friction'):dsl.SimBinding('tableware_friction')}
DELETE_BINDINGS={'bowl_b':dsl.DeleteBinding('receiver_active',index=0,value_when_removed=0)}
VOCAB=dsl.Vocabulary(objects=OBJECTS,properties=PROPERTIES,sim_bindings=SIM_BINDINGS,delete_bindings=DELETE_BINDINGS,
                     baseline_physics=BASELINE_PHYSICS,total_frames=TOTAL_FRAMES)
# Five cases: a five-times heavier driver, a five-times faster launch (the
# receiver is allowed to slide clean off the far end of the counter and fall
# -- the stability guards only cover bowls still on the counter surface), a
# perfectly plastic pair coefficient, the receiver removed outright, and a
# mid-run removal of ALL counter friction -- the collision lands about frame
# 19, so frame 21 sits just after it and the edited bowls coast on without
# ever stopping.
EDIT_CASES=[('edit_heavy_driver','SET bowl_a.mass TIMES 5'),
            ('edit_fast_driver','SET bowl_a.initial_velocity TIMES 5'),
            ('edit_no_restitution','SET pair.restitution TO 0'),
            ('edit_remove_receiver','DELETE bowl_b'),
            ('edit_frictionless_counter_timed','SET bowls.friction TIMES 0 AT FRAME 21')]

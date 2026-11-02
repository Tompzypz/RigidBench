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



from pathlib import Path
import sys
import pcve_edit_dsl as dsl
from scene_config import BASELINE_PHYSICS,TOTAL_FRAMES

# Scene-only edit controls, registered on the embedded schema's own dict so its
# validator (which allows extra physics keys only when they equal baseline)
# accepts them, and the simulator can read them:
#   * ``ball_presence`` -- which of the five pendulum slots exist; DELETE
#     writes one slot to 0;
#   * ``timed_edits`` -- the mid-run restitution schedule.

OBJECTS={'first_ball':{'zh':'左端第一个摆球','en':'the leftmost pendulum ball'},
         'balls':{'zh':'摆球之间','en':'the pendulum balls'},
         'ball_02':{'zh':'正中间的摆球','en':'the middle pendulum ball'},
         'ball_03':{'zh':'右数第二个摆球','en':'the second ball from the right'}}
PROPERTIES={'initial_height':dsl.PropertySpec('scalar','m','初始释放高度','initial release height'),
    'restitution':dsl.PropertySpec('scalar','','碰撞恢复系数','collision restitution coefficient')}
SIM_BINDINGS={('first_ball','initial_height'):dsl.SimBinding('initial_height'),('balls','restitution'):dsl.SimBinding('restitution')}
DELETE_BINDINGS={'ball_02':dsl.DeleteBinding('ball_presence',2,0),
                 'ball_03':dsl.DeleteBinding('ball_presence',3,0)}
VOCAB=dsl.Vocabulary(objects=OBJECTS,properties=PROPERTIES,sim_bindings=SIM_BINDINGS,
    delete_bindings=DELETE_BINDINGS,baseline_physics=BASELINE_PHYSICS,total_frames=TOTAL_FRAMES)
# Five cases: two release heights, a missing middle ball and a missing
# second-from-right ball (whole-clip deletes -- the released ball either dead
# stops at the gap or swings across it and launches the far ball), and a timed
# restitution drop that lands after the first impact (about frame 6) but
# before the last ball's return trip (about frame 27), so the returning
# collision visibly lands dead.
EDIT_CASES=[('edit_low_release','SET first_ball.initial_height TIMES 0.5'),
    ('edit_high_release','SET first_ball.initial_height TIMES 2'),
    ('delete_middle_ball','DELETE ball_02'),
    ('delete_inner_right_ball','DELETE ball_03'),
    ('edit_dead_bounce_timed','SET balls.restitution TIMES 0.3 AT FRAME 15')]

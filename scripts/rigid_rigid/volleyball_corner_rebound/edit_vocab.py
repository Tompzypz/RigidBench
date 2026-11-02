"""Use the project's shared PCVE DSL; four edits hold throughout, one lands mid-flight."""
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



import pcve_edit_dsl as dsl
from scene_config import load_scenario

BASELINE_PHYSICS = load_scenario()['physics']
# Three bodies carry the five edits: the ball itself, the two corner walls it
# rebounds off, and the world (gravity). Every property here is one whose
# change moves the ball somewhere visibly different in the simulated frames;
# the ball's mass is deliberately absent, because a free sphere under gravity
# with mass-independent contact laws follows the identical trajectory at any
# mass and a mass edit would render as the source video.
OBJECTS = {
    'ball': {'zh': '排球', 'en': 'the volleyball'},
    'wall': {'zh': '墙面', 'en': 'the walls'},
    'world': {'zh': '场景', 'en': 'the scene'},
}
PROPERTIES = {
    'initial_velocity': dsl.PropertySpec('scalar', 'm/s', '初始速度大小', 'initial speed',
        initial_condition=True),
    'restitution': dsl.PropertySpec('scalar', '', '恢复系数', 'restitution'),
    'friction': dsl.PropertySpec('scalar', '', '摩擦系数', 'friction coefficient'),
    # Signed, exactly as the simulator stores it: -9.81 m/s^2 measures 9.81
    # downwards, and doubling the magnitude at a frame is what a timed gravity
    # edit writes into the running solver.
    'gravity': dsl.PropertySpec('scalar', 'm/s²', '重力加速度', 'gravity'),
}
SIM_BINDINGS = {
    ('ball', 'initial_velocity'): dsl.SimBinding('ball_initial_speed'),
    ('ball', 'restitution'): dsl.SimBinding('ball_restitution'),
    ('ball', 'friction'): dsl.SimBinding('ball_friction'),
    ('wall', 'restitution'): dsl.SimBinding('wall_restitution'),
    ('world', 'gravity'): dsl.SimBinding('gravity_z'),
}
# The ball is the only body in the clip; the room, cabinet, plant pot and two
# spare volleyballs are static scenery the ball never touches in this corner
# rebound, so removing any of them would change the picture without changing
# the physics. No DELETE, no ADD, and therefore no delete/add bindings.
DELETE_BINDINGS = {}
VOCAB = dsl.Vocabulary(objects=OBJECTS, properties=PROPERTIES, sim_bindings=SIM_BINDINGS,
    delete_bindings=DELETE_BINDINGS, baseline_physics=BASELINE_PHYSICS, total_frames=96)

# Exactly five edits: three that reshape the ball's own motion, one that makes
# the corner walls absorb the rebound, and one gravity change applied while the
# ball is still in flight so the first half of the clip is the source video.
EDIT_CASES = (
    ('edit_speed_x15', 'SET ball.initial_velocity TIMES 1.5'),
    ('edit_restitution_x03', 'SET ball.restitution TIMES 0.3'),
    ('edit_friction_x05', 'SET ball.friction TIMES 0.5'),
    ('edit_wall_restitution_x04', 'SET wall.restitution TIMES 0.4'),
    ('edit_gravity_x25_at24', 'SET world.gravity TIMES 2.5 AT FRAME 24'),
)

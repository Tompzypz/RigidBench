"""PCVE object/property bindings and the preset edit cases."""
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
from scene_config import BASELINE_PHYSICS, TOTAL_FRAMES

OBJECTS = {'driver': {'zh': '左侧启动摆锤', 'en': 'the left driving bob'},
           'receiver': {'zh': '右侧被传动单摆', 'en': 'the right receiving pendulum'},
           'pendulums': {'zh': '两个单摆', 'en': 'both pendulums'}}
PROPERTIES = {
    'mass': dsl.PropertySpec('scalar', 'kg', '质量', 'mass'),
    'initial_angle_deg': dsl.PropertySpec('scalar', 'deg', '相对竖直方向的初始摆幅', 'initial release angle from vertical', initial_condition=True),
    'drag_coefficient': dsl.PropertySpec('scalar', 'kg/s', '线性阻力系数', 'linear drag coefficient')}
SIM_BINDINGS = {('driver', 'mass'): dsl.SimBinding('driver_mass'),
                ('driver', 'initial_angle_deg'): dsl.SimBinding('initial_angle_deg'),
                ('pendulums', 'drag_coefficient'): dsl.SimBinding('drag_coefficient')}
DELETE_BINDINGS = {'receiver': dsl.DeleteBinding('receiver_active', index=0)}
VOCAB = dsl.Vocabulary(objects=OBJECTS, properties=PROPERTIES, sim_bindings=SIM_BINDINGS,
                      delete_bindings=DELETE_BINDINGS, baseline_physics=BASELINE_PHYSICS,
                      total_frames=TOTAL_FRAMES)

# One whole-clip SET each for mass, release angle and drag, a whole-clip
# delete, and a delete that lands partway through, after the first impact.
# Frame 18 is physical time 17/24 s; the builder rescales it when the sample
# clock differs from 24 fps.
EDIT_CASES = (
    ('edit_heavy_driver', 'SET driver.mass TIMES 2',
     'Double the driving bob mass; the receiving bob stays at 0.26 kg and swings farther after impact.'),
    ('edit_large_amplitude', 'SET driver.initial_angle_deg TIMES 1.5',
     'Release the driver from 48 instead of 32 degrees; greater initial energy increases the receiving swing.'),
    ('edit_high_drag', 'SET pendulums.drag_coefficient TIMES 8',
     'Raise linear drag from 0.006 to 0.048 kg/s on both pendulums; motion decays more quickly.'),
    ('edit_remove_receiver', 'DELETE receiver',
     'Remove the receiving pendulum from frame 1; the driver swings freely without transmitting motion.'),
    ('edit_remove_receiver_after_impact', 'DELETE receiver AT FRAME 18',
     'Remove the receiving pendulum at physical time 17/24 s after the first impact (frame 18 at 24 fps); earlier frames match the source and later return impacts cannot occur.'),
)

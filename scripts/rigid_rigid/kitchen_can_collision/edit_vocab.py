"""Exactly five independent edits, applied from frame one."""
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

OBJECTS={'rolling_can':{'zh':'横放滚动的易拉罐','en':'the rolling can'},
         'upright_can':{'zh':'静止直立的易拉罐','en':'the upright can'},
         'pair':{'zh':'两只易拉罐之间的碰撞','en':'the collision between the two cans'},
         # Bullet keeps one friction value per body, so the two contacts are
         # declared as the two surfaces that meet in them.
         'can':{'zh':'两只易拉罐的罐体表面','en':'the can surfaces'},
         'table':{'zh':'厨房台面','en':'the kitchen worktop'}}
PROPERTIES={'mass':dsl.PropertySpec('scalar','kg','质量','mass'),
            'initial_velocity':dsl.PropertySpec('scalar','m/s','沿桌面 X 轴的初速度','initial velocity along the tabletop X axis',initial_condition=True),
            # The rolling can's speed as a live quantity rather than a launch
            # condition: same physics key, but the simulator is allowed to write
            # it into a body that is already rolling, which is what an AT FRAME
            # speed edit needs.
            'speed':dsl.PropertySpec('scalar','m/s','滚动速度','rolling speed'),
            'restitution':dsl.PropertySpec('scalar','','碰撞恢复系数','coefficient of restitution'),
            'friction':dsl.PropertySpec('scalar','','滑动摩擦因数','sliding friction coefficient')}
SIM_BINDINGS={('rolling_can','mass'):dsl.SimBinding('driver_mass'),
              ('upright_can','mass'):dsl.SimBinding('receiver_mass'),
              ('rolling_can','initial_velocity'):dsl.SimBinding('initial_velocity'),
              ('rolling_can','speed'):dsl.SimBinding('initial_velocity'),
              ('upright_can','initial_velocity'):dsl.SimBinding('receiver_initial_velocity'),
              ('pair','restitution'):dsl.SimBinding('restitution'),
              ('can','friction'):dsl.SimBinding('can_friction'),
              ('table','friction'):dsl.SimBinding('table_friction')}
DELETE_BINDINGS={'upright_can':dsl.DeleteBinding('receiver_active',index=0,value_when_removed=0)}
VOCAB=dsl.Vocabulary(objects=OBJECTS,properties=PROPERTIES,sim_bindings=SIM_BINDINGS,
                     delete_bindings=DELETE_BINDINGS,baseline_physics=BASELINE_PHYSICS,total_frames=TOTAL_FRAMES)

# Exactly five cases, one per row, each moving one declared control. The listed
# outcome is the upright can's travel along the table, measured on the current
# simulator (24 fps, 4 s): the source moves it 0.147 m and the rolling can
# leaves 0.611 m of its own, with a pre-impact slip ratio of 0.4 % (it rolls).
#   * 3 x driver mass      : 0.72 kg roller, target 0.394 m, tips 6.1 deg.
#   * 3 x target mass      : 0.72 kg target, 0.023 m -- the roller keeps its
#                            line and the target barely stirs.
#   * delete the target    : nothing to hit; the roller runs 1.306 m instead of
#                            stopping against the other can.
#   * 3 x can surface      : rougher cans (0.065 -> 0.195). Both contacts stiffen
#                            and everything stops sooner: roller 0.520 m, target
#                            0.056 m, tilt 2.6 deg. Bullet has no per-pair
#                            friction, so this knob is the can surface and it
#                            necessarily moves the can-table contact too; the
#                            table-only counterpart (table 2.0, cans untouched)
#                            lands at 0.044 m, which is how the split was read.
#   * 0.25 x table at frame 30: the worktop turns slippery *after* the impact;
#                            both cans then glide -- target 0.335 m, roller
#                            0.799 m. Frames 1-29 are the source clip.
EDIT_CASES=[('edit_heavy_driver','SET rolling_can.mass TIMES 3'),
            ('edit_heavy_receiver','SET upright_can.mass TIMES 3'),
            ('edit_remove_receiver','DELETE upright_can'),
            ('edit_rough_cans','SET can.friction TIMES 3'),
            ('edit_slippery_table','SET table.friction TIMES 0.25 AT FRAME 30')]

DESCRIPTION={
    'vague':{'zh':'厨房桌面上，横放的易拉罐滚向静止直立的易拉罐，碰撞后推动它向前滑行一段距离。',
             'en':'On a kitchen table, a rolling can hits a stationary upright can and pushes it forward.'},
    'quantitative':{'zh':(f'两只易拉罐各重 {BASELINE_PHYSICS["driver_mass"]:g} kg，直径 6.6 cm、高 12.8 cm；'
                          f'滚动罐以 {BASELINE_PHYSICS["initial_velocity"]:g} m/s 滚向静止的直立罐，'
                          f'碰撞恢复系数 {BASELINE_PHYSICS["restitution"]:g}；'
                          f'罐体摩擦因数 {BASELINE_PHYSICS["can_friction"]:g}、台面摩擦因数 '
                          f'{BASELINE_PHYSICS["table_friction"]:g}。'),
                    'en':(f'Both cans weigh {BASELINE_PHYSICS["driver_mass"]:g} kg, 6.6 cm across and 12.8 cm tall; '
                          f'the rolling one approaches the stationary upright one at {BASELINE_PHYSICS["initial_velocity"]:g} m/s '
                          f'with a pair restitution of {BASELINE_PHYSICS["restitution"]:g}; the can surface and '
                          f'the worktop carry friction coefficients of {BASELINE_PHYSICS["can_friction"]:g} and '
                          f'{BASELINE_PHYSICS["table_friction"]:g}.')}}


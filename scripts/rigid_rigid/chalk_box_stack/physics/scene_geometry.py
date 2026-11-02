"""Metric dimensions shared by collision and appearance builders."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
from math import radians

# Two deeper cartons instead of seven thin ones: the same silhouette with a
# third of the parts, and each carton still reads as a real chalk box. COUNT=2
# means the eraser has to extract the bottom carton out from under exactly one
# survivor, which is the shortest stack that still shows a drop of one level.
BOX_SIZE=(.12,.085,.08)
ERASER_SIZE=(.13,.075,.032)
COUNT=2
TABLE_Z=.76
# 65 g keeps the calibrated pair of outcomes: 4 m/s extracts the bottom carton
# and leaves the stack standing, 1 m/s tips it over. Above ~0.10 kg the stack
# also becomes too heavy for the 1 m/s swipe to move at all.
BOX_MASS=.065

# How far the survivor(s) may rock before the take stops counting as "the stack
# stayed up". With two or more survivors this is really an inter-box alignment
# gate -- 15 deg is where they start to slide off each other. With COUNT=2 there
# is only one survivor and nothing to stay aligned to, so a one-level drop that
# rocks and lands flat (a genuine extraction) would be failed for a reason that
# no longer exists; 45 deg keeps the gate meaningful while staying well under
# the 60 deg ``collapse_observed`` threshold.
UPPER_TILT_LIMIT_DEG=15. if COUNT>=3 else 45.

# Hand-stacked, not solver-stacked: a few millimetres of drift and one or two
# degrees of yaw per carton, kept small so the contact and the drop height stay
# predictable. Offsets are fixed rather than random so every run is identical.
# Only the first COUNT entries are used, so lowering COUNT needs no edit here.
BOX_LAYOUT=((.003,-.004,-1.8),(-.005,.003,2.4),(.002,.005,-1.2))


def box_poses():
    """Initial pose of each carton, bottom first, in table coordinates."""
    return [dict(index=index,location=[dx,dy,TABLE_Z+BOX_SIZE[2]*(index+.5)],yaw=radians(yaw))
            for index,(dx,dy,yaw) in enumerate(BOX_LAYOUT[:COUNT])]


def moving_objects(physics):
    start_x=physics.get('eraser_start_x',-.30)
    result={'eraser':dict(size=list(ERASER_SIZE),mass=physics['eraser_mass'],initial_location=[start_x,0,TABLE_Z+ERASER_SIZE[2]/2])}
    for pose in box_poses():
        result[f"box_{pose['index']}"]=dict(size=list(BOX_SIZE),mass=BOX_MASS,
            initial_location=pose['location'],initial_yaw=pose['yaw'])
    return result

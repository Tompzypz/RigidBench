"""Shared visual/physics dimensions of room furniture and static spare balls."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
CABINET_CENTER=(3.8,.11,.21)
CABINET_SIZE=(1.5,.20,.42)
# There is no plant in this room. The corner the ball rebounds into is the only
# corner the camera can see, so a planter there would be a collider the two
# low-restitution edits roll into; a planter anywhere else is either out of shot
# or standing in front of the window. The corner is left empty instead, which is
# also what the ball's own story needs: it comes to rest against the walls.
SPARE_BALL_RADIUS=.105
# Parked at the far end of the sideboard, clear of every run: at their old
# spot the 1.5x speed edit passed a spare ball by 0.2 mm.
SPARE_BALL_CENTERS=((4.75,.30,SPARE_BALL_RADIUS),(4.95,.80,SPARE_BALL_RADIUS))
WINDOW_CENTER_Y=2.5
# The split indoor unit hangs on the window wall, x=0, the wall the camera faces
# most squarely: seen from the y=0 wall its face was foreshortened to 0.56 of its
# length, here it keeps 0.95.  indoor_air_conditioner_unit imports as
# 0.531 x 0.131 x 0.181 m; the room is 10 x 8 x 3 m = 240 m3, which a 3 HP wall
# split of about 1.10 x 0.25 x 0.33 m serves, so the asset is scaled uniformly by
# 2.26 to 1.20 m wide (0.409 high, 0.296 deep) and its own proportions are kept
# rather than stretched to the figures.
AC_SCALE=2.26
AC_WIDTH=.531*AC_SCALE
AC_DEPTH=.131*AC_SCALE
AC_HEIGHT=.181*AC_SCALE
AC_BACK_GAP=.006
# Hung with its underside 2.40 m up and 0.90 m clear of the window's right reveal
# at y=3.20, which puts the top of the case at 2.81 m: 0.19 m of clearance to the
# 3.0 m ceiling, the gap the install manuals ask for and the reason the unit
# cannot go higher.  Its own width runs along the wall (y) and its depth along x:
# AC_SIZE is the axis-aligned box the simulator collides with, so width and depth
# swap relative to the brief's W x D x H.
AC_WALL_Y=4.70
AC_BOTTOM_Z=2.40
AC_CENTER=(AC_BACK_GAP+AC_DEPTH/2,AC_WALL_Y,AC_BOTTOM_Z+AC_HEIGHT/2)
AC_SIZE=(AC_DEPTH,AC_WIDTH,AC_HEIGHT)

def geometry_snapshot():
    return {'cabinet_center':list(CABINET_CENTER),'cabinet_size':list(CABINET_SIZE),
        'spare_ball_radius':SPARE_BALL_RADIUS,'spare_ball_centers':[list(p) for p in SPARE_BALL_CENTERS],
        'window_center_y':WINDOW_CENTER_Y,
        'ac_center':list(AC_CENTER),'ac_size':list(AC_SIZE)}

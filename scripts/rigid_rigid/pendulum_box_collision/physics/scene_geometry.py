"""Metric dimensions shared by the collision shapes and the visible meshes.

Every number here is read by both ``simulate_pendulum_box_collision.py`` and
``look_pendulum_box_collision.py``, so the block the solver moves and the block on screen
cannot drift apart, and the thread in the picture is guaranteed to be the same
length as the rod constraint.

The block is a lab slider, not a crate: 12 x 7 x 8.5 cm of pine, the size of the
block that sits next to a dynamics track in a school lab. It is deliberately
long and shallow rather than cubic -- a tall block would have to be hit high on
its face and would read as a box again.

Height is nonetheless load bearing. The bob rises as it swings and the block may
arrive at any point of the bob's first half period, so the top of the block has
to stay above the bob's centre for the whole swing: with a 0.36 m thread and a
26.5 degree maximum amplitude the bob's centre rises 37.8 mm above its lowest
point, which is why the block is 85 mm tall and not 60.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)

# Bench top, matching the other bench-top scenes in this repo.
TABLE_Z = .76
BENCH_SIZE = (2.6, 1.0, .08)

# 12 x 7 x 8.5 cm, 0.45 kg at about 630 kg/m^3 -- dry pine.
BOX_SIZE = (.12, .07, .085)

# The slider starts well outside the camera frame. Its whole approach is the
# point: the block has to be far enough away that the pendulum finishes half a
# period before anything touches it (about 0.605 s), and at 1.3 m/s with bench
# friction that is 0.70 m of travel. The arithmetic is spelled out here so the
# start position is not a magic constant.
CONTACT_X = -(.020 + BOX_SIZE[0] / 2)      # block centre when its face meets the bob
APPROACH_DISTANCE = .701                   # 1.3 m/s for 0.605 s at 0.47 m/s^2 of friction
BOX_START_X = CONTACT_X - APPROACH_DISTANCE

# Bob: a 48 mm steel ball on a 360 mm thread -- a lab pendulum bob, not a
# wrecking ball. Mass and size are deliberately independent: the mass is an
# editable parameter, and a hollow demonstration ball is exactly the case where
# the two come apart. 48 mm is about the largest ball that still reads as a
# pendulum bob rather than a weight.
BOB_RADIUS = .024
# Gap between the bottom of the hung bob and the bench top.
BOB_CLEARANCE = .010
BOB_CENTER_Z = TABLE_Z + BOB_CLEARANCE + BOB_RADIUS
PENDULUM_LENGTH = .36
PIVOT = (0., 0., BOB_CENTER_Z + PENDULUM_LENGTH)


def box_center():
    """Resting centre of the block, the pose frame 1 must show."""
    return [BOX_START_X, 0., TABLE_Z + BOX_SIZE[2] / 2]


def moving_objects(physics):
    """Per-body metadata shared by the cache, the GT export and the renderer."""
    return {
        'box': dict(size=list(BOX_SIZE), mass=physics['box_mass'],
                    initial_location=box_center(), initial_yaw=0.),
        'bob': dict(radius=BOB_RADIUS, mass=physics['bob_mass'],
                    pivot=list(PIVOT), pendulum_length=PENDULUM_LENGTH,
                    lowest_center=[0., 0., BOB_CENTER_Z]),
    }

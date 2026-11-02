"""Shared geometry and baseline parameters for the pool-break scene.

Both the PyBullet simulation and the Blender renderer import these constants, so
the collision bodies and the visible meshes cannot drift apart and the scene's
three exposed controls have exactly one definition.

World conventions
-----------------
* The table's long axis is **X**. The cue ball breaks from ``+X`` towards
  ``-X``, so the camera sits behind the cue at ``+X`` and looks down the table.
* **+Y** is the far side of the table as seen from that camera's default rig
  (forward ``-X``, up ``+Z`` => screen-right is ``+Y``), which is why a
  positive ``cue_contact_offset`` reads as "hit the right side of the apex
  ball" rather than as an abstract axis sign.
* The felt surface is world ``z = 0``; every ball centre sits at ``z = radius``.
  The imported table model is shifted down by its own felt height so the two
  frames coincide -- see :func:`model_z_shift`.

Why the scene is scaled by the ball, not by the table
-----------------------------------------------------
``pool_table_animation.glb`` is authored in FBX centimetres: the felt mesh
measures 1200.7 x 621.8 units and every ball mesh has a 18.93-unit radius. A
real 57.15 mm ball against that felt would make a 3.6 m table, so the model's
balls are oversized relative to its cloth. Scaling so the *balls* are
regulation (``SCENE_SCALE``) instead gives a 1.81 x 0.94 m playing surface --
a compact bar table, which is a real thing -- and keeps every number that the
physics cares about (ball/ball contact, cue speed, gravity) in familiar units.
Scaling by the table instead would leave 76 mm balls that visibly do not behave
like billiard balls at this camera distance.
"""

from __future__ import annotations
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)

from pathlib import Path

# ---------------------------------------------------------------- the model

MODEL_PATH = _PCVE_ROOT / "assets" / "models" / "pool_table_animation.glb"

# Measured off the model: every ball mesh is a sphere of this radius, the felt
# mesh is a flat sheet at this height, and the cushion nose sits at the felt
# edge (the vertex scan put it within 1.5 units of the felt bound).
MODEL_BALL_RADIUS_UNITS = 18.9315
MODEL_FELT_TOP_Z_UNITS = 100.012
MODEL_PLAY_HALF_X_UNITS = 598.9
MODEL_PLAY_HALF_Y_UNITS = 309.4
MODEL_FLOOR_Z_UNITS = -363.94        # bottom of the legs, for the visual floor

# Regulation pool ball: 57.15 mm diameter.
BALL_RADIUS = 0.028575
SCENE_SCALE = BALL_RADIUS / MODEL_BALL_RADIUS_UNITS

PLAY_HALF_X = MODEL_PLAY_HALF_X_UNITS * SCENE_SCALE      # 0.904 m
PLAY_HALF_Y = MODEL_PLAY_HALF_Y_UNITS * SCENE_SCALE      # 0.467 m
MODEL_FLOOR_Z = MODEL_FLOOR_Z_UNITS * SCENE_SCALE


def model_z_shift() -> float:
    """How far to drop the imported table so its felt lands on world ``z = 0``."""
    return MODEL_FELT_TOP_Z_UNITS * SCENE_SCALE


# Which mesh in the GLB plays which part. The file ships a full rack of
# fifteen numbered balls plus a white cue ball and two cue sticks; the scene
# only uses four of them and hides the rest, exactly the way
# ``pool_collision`` hides the balls its shot does not use.
CUE_BALL_MESH = "Ball Clube_10 - Default_0"
APEX_BALL_MESH = "Ball1_01 - Default_0"
LEFT_BALL_MESH = "Ball2_Material #158_0"
RIGHT_BALL_MESH = "Ball3_Material #157_0"
# Hidden on import: the rest of the rack, and both sticks (this scene drives
# the cue ball kinematically at frame 1 rather than animating a stick).
UNUSED_BALL_PREFIX = "Ball"
CUE_STICK_PREFIXES = ("Cue stick", "Cue stick2")

# ----------------------------------------------------------------- the rack
# The foot spot is the middle of the far half of the table, which is where a
# rack is set in every published rule set.
FOOT_SPOT_X = -PLAY_HALF_X / 2.0
# Cue ball starts behind the head string and drives 1.05 m up the table.
CUE_START_X = 0.60
# A 0.5 mm air gap between the racked balls. Placing them exactly touching
# makes Bullet resolve an initial overlap with a separation impulse on frame 1,
# which pushes the rack apart before the cue ball has moved.
RACK_GAP = 0.0005


def rack_centres() -> dict[str, tuple[float, float]]:
    """Where the three racked balls sit, in the table plane.

    An equilateral triangle pointing at the cue ball: the apex on the foot
    spot, the other two one centre-to-centre distance behind it. The apex is
    therefore wedged between the two rear balls, which is what turns a cue-ball
    impact into a break instead of into a single ball rolling away from an
    untouched pair.

    The rear pair sits at ``(-d * sqrt(3)/2, +/- d/2)`` relative to the apex --
    half a spacing to either side, three quarters of a spacing back. That is the
    first three balls of a real rack: the apex angle seen from the cue ball is
    60 degrees, so each rear ball sits 30 degrees off the cue's line, and all
    three pairs are one full spacing apart. Getting this the wrong way round
    (rear pair at ``(-d/2, +/- d * sqrt(3)/2)``) still touches the apex but
    leaves the two rear balls 1.73 spacings apart with a hole between them: a
    flat 120-degree wedge that no rack has ever looked like, and the "triangle"
    reads as two balls flanking a third from a distance.
    """
    d = 2.0 * BALL_RADIUS + RACK_GAP
    back = d * 0.8660254037844386
    across = d * 0.5
    return {
        "apex_ball": (FOOT_SPOT_X, 0.0),
        "right_ball": (FOOT_SPOT_X - back, +across),
        "left_ball": (FOOT_SPOT_X - back, -across),
    }


# ---------------------------------------------------------------- physics

# The three controls the benchmark exposes.
BASELINE_PHYSICS = {
    # A medium break: about 3.6 m/s of cue-ball speed. On a 1.8 m table this
    # carries the cue ball 1.05 m to the rack in a quarter of a second and
    # spreads the triangle to the cushions inside the clip.
    "cue_speed": 3.6,            # m/s
    # Signed lateral offset of the cue ball's line of travel from the apex
    # ball's centre. + is the apex ball's right side (screen-right); +/-
    # one ball radius is a half-ball hit, 2 radii is a clean miss.
    #
    # Deliberately not 0. A dead-centre hit is a stun shot: the cue ball comes
    # straight back down its own line (+/-180 degrees) and the rack opens with
    # perfect mirror symmetry, which no real break does and which makes the
    # shot look like a diagram. 3 mm is 0.05 radii -- invisible at this camera
    # distance -- but it is already enough to break the symmetry: the cue ball
    # leaves at 157 degrees instead of coming straight back, and the apex ball
    # is nudged to one side.
    "cue_contact_offset": 0.003,  # m
    "cue_mass": 0.17,            # kg -- regulation ball
}

# Everything an edit must NOT move, so a single-variable edit stays single.
FIXED_PHYSICS = {
    "object_mass": 0.17,
    # Bullet multiplies the two bodies' coefficients, so the pair that matters
    # is 0.25 * 0.12 = 0.03. This pair governs the *sliding* phase only -- it is
    # what stops the cue ball skidding and gets it rolling, and it is kept low
    # because at 0.6/0.9 the cue ball loses 5.3 m/s^2 and stops a third of the
    # way to the rack. The loss that lasts, cloth drag, is ``BALL_ROLL_DECEL``.
    "ball_friction": 0.25,
    "felt_friction": 0.12,
    # Left at zero on purpose. Bullet's rolling-friction constraint on a sphere
    # does not give a rolling ball a constant drag -- it instead cancels the
    # spin the contact friction is trying to build, so the ball slides the whole
    # way at the full lateral coefficient. Cloth drag therefore lives in the
    # lateral pair above, and the visible roll is reconstructed from each ball's
    # path by ``simulate_pool_break.rolling_quaternions``.
    "ball_rolling_friction": 0.0,
    "ball_spinning_friction": 0.0,
    "ball_restitution": 0.93,        # ball <-> ball reads 0.93 * 0.93 = 0.86
    "felt_restitution": 0.10,
    "cushion_friction": 0.30,
    "cushion_restitution": 0.72,
    "gravity_z": -9.81,
}

# Cloth drag, applied explicitly as a constant deceleration (m/s^2).
#
# Coulomb friction alone cannot stop a ball: once it rolls without slipping the
# contact patch is stationary, the friction force drops to zero and a rigid
# sphere on a rigid plane coasts forever. Real cloth dissipates through fibre
# deformation and the ball's own hysteresis, which Bullet does not model, and
# its ``rollingFriction`` term is not usable here (see above -- it fights the
# spin instead of damping it). So the drag is integrated by hand, and without it
# the clip ended with four balls still travelling at 0.5-1.2 m/s after five
# cushion bounces, the triangle width oscillating between 70 mm and 570 mm from
# frame to frame -- a pinball table, not a break.
#
# The value is the physical one. A ball rolling on worsted cloth decelerates at
# 0.2-0.35 m/s^2 (rolling resistance coefficient 0.02-0.035); 0.30 is the fast
# end of that band, which is what a brushed worsted cloth under a hard break
# behaves like. Note that the total loss is not this number alone: while a ball
# is still sliding it also pays the felt's Coulomb term (``ball_friction`` *
# ``felt_friction`` * g = 0.29 m/s^2), so the hand-integrated drag is the
# rolling-phase loss only.
#
# This used to be 0.8 to make a 2.5 s clip settle, and 0.8 is what a viewer
# reads as wrong: it is 3x the real figure, and it stopped every ball by 1.9 s.
# The constraint that forced it was clip length, and clip length is now 4 s
# (``BASELINE_RENDER``), so the compromise is gone. At 0.30 the same break runs
# 2.4 m of path per wing ball instead of 1.2 m -- a wing ball reaches the corner,
# comes off the end cushion and carries back across the table -- and the last
# ball dies at 3.96 s, one frame before the end.
#
# The two numbers are coupled: shortening the clip below ~3.8 s puts the
# settling back in the cut-off, and at 2.5 s the two wing balls are still
# running at 0.39 and 0.48 m/s when the clip ends.
BALL_ROLL_DECEL = 0.30

# Cushion nose height is 63.5 % of a ball diameter in every table spec.
CUSHION_HEIGHT = 0.0363
CUSHION_THICKNESS = 0.05
# 96 substeps at 24 fps is a 0.43 ms step. The cue ball covers 1.5 mm per
# substep at the default speed, which is the point: at 48 substeps a fast
# contact resolves with about 3 mm of penetration on a 28.6 mm radius and the
# rack visibly pops apart instead of being struck.
SUBSTEPS_PER_FRAME = 96

# ---------------------------------------------------------------- baseline

BASELINE_RENDER = {
    "fps": 24,
    # Long enough for the break to finish on its own at the physical cloth
    # drag: the last ball dies at 3.96 s. A 2.5 s clip (the old default) only
    # fitted because ``BALL_ROLL_DECEL`` was inflated to stop everything early.
    "duration_sec": 4.0,
    # Same size every other rigid-body suite in this repo renders at.
    "resolution": (960, 540),
    "samples": 48,
    "camera_mode": "break",
}

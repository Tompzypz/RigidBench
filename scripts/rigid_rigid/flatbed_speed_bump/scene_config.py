"""Shared geometry and baseline parameters for the flatbed-speed-bump scene.

Both the PyBullet simulation and the Blender renderer import these constants so
the collision shapes and the visible meshes cannot drift apart, and so the
scene's three exposed controls have exactly one definition.

World conventions
-----------------
* The truck is driven along world **+X**; the cab faces +X.
* **+Y** is the far kerb (the freight-yard side); **-Y** is the near kerb
  (safety fence, cones) that faces the camera.
* Everything about the truck is expressed in the **vehicle reference frame
  V**: the origin sits on the wheel-axle line at mid-wheelbase, i.e.
  ``WHEEL_RADIUS`` above the road, so ``V z = 0`` is the axle height and the
  road surface is at ``V z = -WHEEL_RADIUS``. Chassis-local coordinates are
  V-relative values shifted by ``-CHASSIS_COM_Z``, because a multibody's base
  position *is* its centre of mass.

Why the bed is its own body
---------------------------
A rigid truck that clears a speed bump flies as one piece, and so does
anything resting on it: while the vehicle is ballistic the bed and its cargo
share exactly the same acceleration, so the cargo can never leave the bed no
matter how violent the jump looks. Making the deck a *sprung* body on a
prismatic suspension is what actually throws the cargo: the deck overshoots the
chassis and can be pulled down at well over 1 g on the rebound, which is the
one condition under which a loose carton separates from it.
"""

from __future__ import annotations
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)

# --------------------------------------------------------------------- truck
#
# The rig is *derived from* the asset, not fitted to it. ``flatbed_unity3d.glb``
# is a real-proportioned three-axle flatbed authored at 26.03 x 8.87 x 8.86
# model units, and it is placed by ONE factor, ``TRUCK_SCALE``, applied to every
# vertex on all three axes -- ``model_x`` / ``model_z`` below plus
# ``p.x * TRUCK_SCALE`` are the whole mapping, and ``import_truck`` calls the
# same two functions. There is no per-axis correction left anywhere, so every
# proportion the artist built survives.
#
# That is why the deck sits at 0.737 m and the wheelbase is 3.068 m instead of
# at round numbers: those are where this truck's bed and axles actually are. Any
# rig that wants the deck higher has to stretch the 0.70 m between the sill and
# the bed, and that stretch is exactly what reads as "the cab is on stilts".
#
# The factor itself is the front tyre radius over the rig's, which keeps the
# 0.34 m wheel: the 0.17 m bump therefore stays at half a wheel radius and the
# suspension keeps being excited in the band it was tuned for.

# Measured on the asset, in model units (_dump_truck_dimensions.py prints them).
MODEL_GROUND_Z = -4.43          # tyre contact plane
MODEL_WHEEL_R = 1.635           # front tyre radius
MODEL_FRONT_AXLE_Y = -11.2425
MODEL_REAR_AXLE_Y = 3.5119      # mean of the rear tandem
MODEL_BED_TOP_Z = -0.887        # up-facing deck plank, level with the tyre tops
MODEL_BED_FRONT_Y = -6.46       # nose end of the deck, where the cab ends
MODEL_BED_SILL_Z = -1.23        # lowest bed face; below this it is still frame
MODEL_BED_Y = (-6.45, 9.64)
MODEL_BED_X = (-4.11, 4.09)
MODEL_CAB_Y = (-16.39, -6.51)
MODEL_CAB_X = (-4.46, 4.41)
MODEL_CAB_Z = (-1.23, 4.43)
MODEL_FRAME_Y = (-15.75, 9.57)
MODEL_FRAME_X = (-4.15, 4.13)

TRUCK_SCALE = 0.34 / MODEL_WHEEL_R                    # 0.2079511

WHEEL_RADIUS = MODEL_WHEEL_R * TRUCK_SCALE            # 0.3400
WHEEL_WIDTH = 1.437 * TRUCK_SCALE                     # 0.2988, front tyre
WHEEL_BASE = (MODEL_REAR_AXLE_Y - MODEL_FRONT_AXLE_Y) * TRUCK_SCALE
WHEEL_XS = (-0.5 * WHEEL_BASE, 0.5 * WHEEL_BASE)      # 3.0682 m axle spacing
# The front axle strikes the bump first, so its track is what the four collision
# cylinders use; the rear tandem is narrower (0.591 m half-track) and only its
# visible wheels sit there.
WHEEL_YS = (-3.398 * TRUCK_SCALE, 3.398 * TRUCK_SCALE)  # 1.4132 m track


def model_x(y: float) -> float:
    """Model +Y (rearwards) -> vehicle X, front axle on ``+WHEEL_BASE / 2``."""
    return 0.5 * WHEEL_BASE - (y - MODEL_FRONT_AXLE_Y) * TRUCK_SCALE


def model_z(z: float) -> float:
    """Model +Z -> vehicle Z, with the tyre contact patch landing on ``-R``."""
    return -WHEEL_RADIUS + (z - MODEL_GROUND_Z) * TRUCK_SCALE


# The chassis body's origin is its centre of mass, placed this high above the
# ground contact line; the collision shapes below are offset from it. 0.55 m is
# the height the pitch and roll response was tuned at, and the tyre radius is
# unchanged, so it stays.
CHASSIS_MASS = 900.0
CHASSIS_COM_Z = 0.55
# Underbody rail, cut off at the axle line. The model's sill reaches down to
# 0.108 m above the road, which is below the 0.17 m bump crest -- a collider
# that deep would ride up on the bump, so the box stops at V z = 0. The sim
# centres this box on X = 0 while the model's own rail is 0.16 m off-centre, so
# it takes the shorter side: that keeps it inside the body at both ends.
FRAME_HALF = (
    min(abs(model_x(MODEL_FRAME_Y[0])), abs(model_x(MODEL_FRAME_Y[1]))),
    0.5 * (MODEL_FRAME_X[1] - MODEL_FRAME_X[0]) * TRUCK_SCALE,
    0.125,
)
FRAME_Z = 0.125
# The cab's collision box starts behind the deck's front edge only if it is
# pushed far enough forward: an overlapping box would press on the deck and
# lock the suspension solid at zero travel. Here the model's own gap (12 mm) is
# what separates them; the joint is prismatic in Z, so the deck cannot rotate
# into the cab.
CAB_HALF = (
    abs(0.5 * (model_x(MODEL_CAB_Y[1]) - model_x(MODEL_CAB_Y[0]))),
    0.5 * (MODEL_CAB_X[1] - MODEL_CAB_X[0]) * TRUCK_SCALE,
    0.5 * (model_z(MODEL_CAB_Z[1]) - model_z(MODEL_CAB_Z[0])),
)
CAB_X = 0.5 * (model_x(MODEL_CAB_Y[1]) + model_x(MODEL_CAB_Y[0]))
CAB_Z = 0.5 * (model_z(MODEL_CAB_Z[1]) + model_z(MODEL_CAB_Z[0]))

# ------------------------------------------------------- sprung flatbed deck

BED_MASS = 350.0
DECK_HALF = (
    abs(0.5 * (model_x(MODEL_BED_Y[1]) - model_x(MODEL_BED_Y[0]))),
    0.5 * (MODEL_BED_X[1] - MODEL_BED_X[0]) * TRUCK_SCALE,
    # A 50 mm plate: thin enough to hide inside the model's bed slab, which is
    # 0.071 m thick at this scale, so the 0.05 m of collision below the plank
    # surface never pokes out under the visible sill.
    0.025,
)
DECK_CENTER_X = 0.5 * (model_x(MODEL_BED_Y[1]) + model_x(MODEL_BED_Y[0]))
DECK_TOP_Z = model_z(MODEL_BED_TOP_Z)     # V-frame deck surface, 0.3968
DECK_Z = DECK_TOP_Z - DECK_HALF[2]        # V-frame centre of the deck at rest
DECK_FRONT_X = DECK_CENTER_X + DECK_HALF[0]
DECK_REAR_X = DECK_CENTER_X - DECK_HALF[0]

# Prismatic travel of the deck on the chassis: down is compression, up is droop.
# Down is capped by the 0.097 m between the deck plate and the frame top.
SUSPENSION_TRAVEL_DOWN = 0.09
SUSPENSION_TRAVEL_UP = 0.07
# 40 kN/m on the 350 kg deck is 1.70 Hz. That is far softer than the 280 kN/m
# the 2.28 m rig used, and it has to be: what a chassis feeds the deck is the
# gap between the two axles clearing the bump, and this wheelbase is 3.068 m
# rather than 2.28 m, i.e. 2.9 Hz instead of 3.9 Hz. A deck stiff enough to
# follow the chassis over the bump just rides with it, and then the cargo shares
# its acceleration and never leaves the planks. `_sweep_suspension.py` over
# 40-280 kN/m x damping ratio 0.12/0.25/0.35 put the launch peak here: 65 mm of
# deck clearance and 7 airborne frames, against 40 mm and 3 at 280 kN/m.
SUSPENSION_STIFFNESS = 40_000.0
SUSPENSION_DAMPING = 1_870.0
# Bump and droop stops: a stiffer one-sided spring takes over past the travel
# limits, which is what keeps the deck from driving into the frame.
STOP_STIFFNESS = 700_000.0
STOP_DAMPING = 6_000.0
# Hard cap on what the suspension may transmit, as a multiple of the deck's
# weight. This is what keeps the explicit integration stable when the chassis
# lands hard: uncapped, a 0.16 m bump sent the deck's travel into the tens of
# metres.
SUSPENSION_FORCE_LIMIT_UP = 14.0
SUSPENSION_FORCE_LIMIT_DOWN = 4.0

CHASSIS_ANGULAR_DAMPING = 0.12
# The wheels are cylinders fixed to the chassis; they have no axle of their own
# and cannot spin, so any real Coulomb coefficient turns them into skids that
# stop the truck (about 0.96 g) long before it reaches the bump. Giving them a
# near-frictionless contact is what a free-rolling tyre actually looks like
# here: it still carries the full normal load, so the bump still kicks the
# truck, it just does not drag.
WHEEL_ROAD_FRICTION = 0.02
# Cruise control, as a real force applied at the chassis centre of mass rather
# than a velocity override. The override was the one thing that made this scene
# unphysical: resetting the linear velocity every substep threw away the contact
# impulse's linear part while keeping its angular part, which pumped angular
# momentum into the chassis and stood the truck on its tail -- an 87 degree
# wheelie on bumps as small as 0.10 m. A force at the centre of mass cannot
# torque the chassis, so the pitch it produces is only what the bump really
# produces.
DRIVE_FORCE_GAIN = 200_000.0       # N per m/s of speed error
DRIVE_FORCE_MAX = 25_000.0         # N, about 18 m/s^2 on the laden truck

# ------------------------------------------------------------------- cargo
# Two identical parcels ride loose on the bed, abreast and almost touching:
# side by side across the deck, parallel to its long axis, 8 mm apart. The gap
# is not decorative -- spawning them truly coincident makes Bullet fire a
# separation impulse on frame 1 -- but it is small enough that the pair reads as
# one tidy load instead of two boxes parked at random.
#
# The parcel is the ``carton_box_05_closed`` glb, measured at 31.5488 x 39.9721
# x 25.8244 model units with its base on z = 0 (see ``_dump_asset_bounds.py``).
# One factor takes that to a real parcel: CARGO_SCALE puts the 25.82 height at
# 0.52 m -- the height the old procedural crate had, so the suspension tuning
# and the 0.20 friction band still describe the same load. x and y are *not*
# chosen, they follow the model's own 1.222 : 1.548 : 1 aspect, which is why
# the footprint comes out 0.635 x 0.805 instead of the old 0.64 x 0.56.

CARGO_ASSET = "carton_box_05_closed.glb"
CARGO_MODEL_SIZE = (31.5488, 39.9721, 25.8244)
CARGO_TARGET_HEIGHT = 0.52
CARGO_SCALE = CARGO_TARGET_HEIGHT / CARGO_MODEL_SIZE[2]          # 0.0201362
CARGO_SIZE = tuple(size * CARGO_SCALE for size in CARGO_MODEL_SIZE)

CARGO_HALF_EXTENTS = (
    tuple(0.5 * size for size in CARGO_SIZE),                    # 0.3176 x 0.4024 x 0.26
    tuple(0.5 * size for size in CARGO_SIZE),
)
# The pair is abreast in Y but staggered in X by 0.90 m, and the near-side
# parcel (index 0, -Y, the camera side) is the one set back: its rear face is
# 0.65 m from the tail edge of the planks, and its centre of mass is 0.97 m
# from it. That is the whole point of the scene now. The deck lags the chassis
# on the rebound and the loose parcel lags the deck, so in deck coordinates it
# travels aft during the strike; mid-deck that aft travel is all spent sliding
# on the planks, and moving the pair to the tail converts the same aft travel
# into a parcel going over the back edge while the far parcel rides it out as
# the control.
#
# Both numbers are measured, not chosen, and `_probe_cargo_xs.py` is the
# measurement: it walks one parcel at a time and reports whether it is still
# aboard at t = 4 s. The aft slip is 1.0-1.5 m in deck coordinates, so a parcel
# has to start within ~1.0 m of the tail edge to go over, and the other has to
# start at least ~1.85 m from it to survive -- which is why the two cannot sit
# at the same x and why the stagger is 0.9 m rather than the "just slightly
# back" a still frame would suggest. At this split the near parcel leaves at
# the 9 m/s baseline and still leaves at 7 m/s; the far one does not leave at
# either, which is what makes the shot readable: one parcel on the road, one
# still on the planks.
CARGO_DECK_LOCAL_XS = (-0.70, 0.20)    # deck-local x; -X is aft, 0 = deck centre
CARGO_GAP_Y = 0.008                     # mm-scale only: see the note above
CARGO_LOCAL_XS = tuple(DECK_CENTER_X + x for x in CARGO_DECK_LOCAL_XS)
CARGO_LOCAL_YS = (
    -(CARGO_HALF_EXTENTS[0][1] + 0.5 * CARGO_GAP_Y),   # near kerb, set back
    +(CARGO_HALF_EXTENTS[0][1] + 0.5 * CARGO_GAP_Y),   # far kerb, forward
)

# --------------------------------------------------------------- speed bump
# A rounded (sine-profile) bump spanning the full road width. Its width stays
# below the truck's wheelbase, so the two axles strike it separately and the
# bed is pitched as well as heaved.

SPEED_BUMP_CENTER_X = 0.0
SPEED_BUMP_WIDTH = 1.34
SPEED_BUMP_SEGMENTS = 24

# ------------------------------------------------------------------- roadway

ROAD_HALF_LENGTH = 70.0
ROAD_HALF_WIDTH = 4.0
ROAD_SURFACE_Z = 0.0

# Truck spawn: far enough back that the approach, the strike, the flight and
# the landing all fit inside one short clip.
TRUCK_START_X = -7.0

# ---------------------------------------------------------------- baseline

# The three controls the benchmark exposes, plus the surfaces that are
# deliberately fixed so a single-variable edit really is single-variable.
BASELINE_PHYSICS = {
    "truck_speed": 9.0,          # m/s -- about 32 km/h, deliberately too fast
    "speed_bump_height": 0.17,   # m   -- peak height of the rounded bump
    # 0.20 sits in the middle of the band that matters: below it the cartons
    # skid off the deck, above it they grip and stay, so both directions of the
    # edit read as different outcomes. At 0.34 the high side had already
    # saturated.
    "cargo_friction": 0.20,      # --  cargo box <-> deck pair friction
}
FIXED_PHYSICS = {
    "deck_friction": 0.70,       # the deck's own coefficient; the pair with the
                                 # cargo is what the exposed knob scales
    "road_friction": 0.96,
    "cargo_mass": 42.0,
    "gravity_z": -9.8,
}

# The camera is a fixed vantage on the near-kerb side of the road, so the truck
# drives through the frame instead of the frame driving with it. A chase rig
# would hold the truck still on screen and read the throw only as background
# motion, which hides the one thing the scene exists to show. It sits on the -Y
# (camera-facing) side and is framed *left*: the start of the run (the truck
# intact at x = -7) must be fully in frame, and only the stretch the truck needs
# to clear the bump matters -- the empty haul road past the landing is left out
# of shot, so no dead runway dominates the right half of the frame.
STATIC_CAMERA_LOCATION = (0.0, -12.0, 3.3)
STATIC_CAMERA_TARGET = (1.0, 0.0, 1.15)
STATIC_CAMERA_LENS_MM = 26.0

BASELINE_RENDER = {
    "fps": 24,
    "duration_sec": 4.0,
    # Matches the other rigid-body suites in this repo. EEVEE Next holds about
    # 14 s per frame here at 960x540/32, so a full clip is roughly 18 minutes;
    # 1280x720/48 is about three times that for no visible gain.
    "resolution": (960, 540),
    "samples": 32,
    # The clip is a bolted-down camera by requirement, so it has to hold a run
    # of 41 m: see ``render_flatbed_speed_bump.CAMERA_PRESETS``. ``static`` only
    # works for one still.
    "camera_mode": "clip4s",
}

# ------------------------------------------------------------------ helpers


def bed_rest_top_z() -> float:
    """World z of the deck surface with the truck sitting at rest."""
    return WHEEL_RADIUS + DECK_TOP_Z


def road_length_for(speed: float, duration_sec: float, *, margin: float = 12.0) -> float:
    """Half-length that keeps a truck at ``speed`` on the slab for the clip."""
    reach = abs(float(TRUCK_START_X)) + abs(float(speed)) * float(duration_sec) + margin
    return max(ROAD_HALF_LENGTH, reach)

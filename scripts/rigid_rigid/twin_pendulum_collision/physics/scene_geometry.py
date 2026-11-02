"""Single source of geometry for collision, suspension, renderer and GT."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math

BOB_RADIUS = .032
LENGTH = .32
PIVOT_HEIGHT = 1.25
PIVOT_SPACING = .086
REST_GAP = PIVOT_SPACING - 2 * BOB_RADIUS
RECEIVER_MASS = .26
RESTITUTION = .92
GRAVITY = 9.81
PHYSICS_HZ = 4800
TABLE_HEIGHT = .76
KEYS = ('driver', 'receiver')
PIVOTS = ((-PIVOT_SPACING / 2, 0., PIVOT_HEIGHT), (PIVOT_SPACING / 2, 0., PIVOT_HEIGHT))


def center(index, angle):
    x, y, z = PIVOTS[index]
    return (x + LENGTH * math.sin(angle), y, z - LENGTH * math.cos(angle))


def tangent(angle):
    return (LENGTH * math.cos(angle), 0., LENGTH * math.sin(angle))


def fixed_constants():
    return dict(bob_radius_m=BOB_RADIUS, pendulum_length_m=LENGTH, pivots=PIVOTS,
                pivot_spacing_m=PIVOT_SPACING, rest_surface_gap_m=REST_GAP,
                receiver_mass_kg=RECEIVER_MASS, pair_restitution=RESTITUTION,
                gravity_m_s2=GRAVITY, physics_hz=PHYSICS_HZ)

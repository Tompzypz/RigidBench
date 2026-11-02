"""Meter-scale can geometry shared by the visual model and Bullet hull."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math

KEYS = ('rolling_can', 'upright_can')
COUNTER_Z = 1.8916853666305542 * .5
RADIUS = .033
HEIGHT = .128
COM_HEIGHT = HEIGHT / 2
START_X = (-.48, .05)
SIM_HZ = 1440
PROFILE = ((.027, -.064), (.030, -.063), (.030, -.060),
           (.033, -.052), (.033, .049), (.030, .058),
           (.029, .061), (.030, .062), (.030, .064))


def hull_vertices(segments=128):
    return [[r*math.cos(i*2*math.pi/segments), r*math.sin(i*2*math.pi/segments), z]
            for r,z in PROFILE for i in range(segments)]


def fixed_constants():
    return dict(counter_z=COUNTER_Z, radius=RADIUS, height=HEIGHT, profile=PROFILE,
                initial_x=START_X, gravity_z=-9.81, sim_hz=SIM_HZ,
                table_friction=1., can_lateral_friction=.065, rolling_friction=.00065,
                solver_iterations=120, collision_margin_m=.0001)

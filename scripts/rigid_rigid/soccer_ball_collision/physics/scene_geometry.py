"""Shared metric collision geometry. Size-five balls on level short turf."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
KEYS = ('ball_a', 'ball_b', 'ball_c')
RADIUS = .11
START_X = (-.85, .85)
START_Y = (-.04, .04)
SIM_HZ = 1440


def fixed_constants():
    return dict(radius_m=RADIUS, start_x_m=START_X, start_y_m=START_Y,
                gravity_m_s2=9.81, simulation_hz=SIM_HZ, ground_lateral_friction=.8,
                spinning_friction=.0002, ground_height_m=0.,
                sphere_inertia_factor=.6666666666666666)

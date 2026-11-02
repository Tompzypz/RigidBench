"""Metric dimensions, collision proxy and deterministic simulation clock."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
KEYS=('car_a','car_b')
# Visual bounds at the chosen model scale: length, width, height in metres.
DIMENSIONS=((.145,.145*189.85845947265625/363.76861572265625,.145*138.92532423161902/363.76861572265625),
            (.180,.180*4.010020732879639/7.570144176483154,.180*3.5043145418167114/7.570144176483154))
HALF_EXTENTS=tuple(tuple(v/2 for v in size) for size in DIMENSIONS)
START_X=(-.42,0.)
SIM_HZ=1440
FLOOR_FRICTION=.5

def fixed_constants():
    return dict(dimensions=DIMENSIONS,half_extents=HALF_EXTENTS,start_x=START_X,sim_hz=SIM_HZ,
                floor_friction=FLOOR_FRICTION,gravity=9.81,pair_restitution=.32,
                proxy='free 6-DOF rigid box; effective rolling drag at floor; visual wheels roll by travelled arc length')

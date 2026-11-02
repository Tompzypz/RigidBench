"""One source of truth for visible surfaces and Bullet collision geometry."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
KEYS = ('soccer','basketball')
RADII = (.11,.12)
START_X = (-1.55,.82)
LANE_Y = -.18
SIM_HZ = 1440
ROOM_X = (-3.8,5.2)
ROOM_Y = (-3.8,2.8)
STEP_X = 0.
FLOOR_THICKNESS = .16

def boxes(height):
    """(name, centre, full size). Top surfaces are exactly z=0 and z=height."""
    x0,x1=ROOM_X; y0,y1=ROOM_Y
    return [
        ('floor',((x0+x1)/2,(y0+y1)/2,-FLOOR_THICKNESS/2),
            (x1-x0,y1-y0,FLOOR_THICKNESS)),
        ('platform',((STEP_X+x1)/2,(y0+y1)/2,height/2),
            (x1-STEP_X,y1-y0,height)),
        ('back_wall',((x0+x1)/2,y1+.10,1.6),(x1-x0,.20,3.2)),
        ('right_wall',(x1+.1,(y0+y1)/2,1.6),(.20,y1-y0,3.2)),
        ('left_wall',(x0-.1,(y0+y1)/2,1.6),(.20,y1-y0,3.2))]

def constants():
    return dict(radii_m=RADII,start_x_m=START_X,lane_y_m=LANE_Y,
                step_x_m=STEP_X,room_x_m=ROOM_X,room_y_m=ROOM_Y,simulation_hz=SIM_HZ,
                floor_friction=.65,platform_friction=.65,surface_restitution=.22,
                floor_rolling_friction=.0015,ball_lateral_friction=.8)

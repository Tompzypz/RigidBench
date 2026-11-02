"""A shared lathe profile for the visible bowl and its convex collision hull.

The hull fills the bowl's empty interior; no object enters that interior here.
The foot, underside, wall slope, rim radius and body origin match the renderer.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math

KEYS=('bowl_a','bowl_b')
COUNTER_Z=1.8916853666305542*.5
COM_HEIGHT=.018
RADIUS=.085
FRICTION=.018
START_X=(-.67,0.)
SIM_HZ=1440
# Radius, height above foot plane. Closed solid cross section, underside -> lip -> inner floor.
PROFILE=((0.,.004),(.030,.004),(.037,.000),(.044,.000),(.046,.003),(.047,.008),
         (.055,.012),(.067,.020),(.078,.030),(.0835,.036),(.085,.039),
         (.0845,.041),(.0825,.042),(.0805,.040),(.077,.034),(.066,.025),
         (.054,.019),(.043,.014),(.030,.011),(0.,.011))


def hull_vertices(segments=96):
    return [[r*math.cos(i*2*math.pi/segments),r*math.sin(i*2*math.pi/segments),z-COM_HEIGHT]
            for r,z in PROFILE for i in range(segments)]


def fixed_constants():
    return dict(counter_z=COUNTER_Z,com_height=COM_HEIGHT,radius=RADIUS,profile=PROFILE,
                initial_x=START_X,table_friction=FRICTION,gravity_z=-9.81,sim_hz=SIM_HZ,
                solver_iterations=120,collision_margin_m=.0001)

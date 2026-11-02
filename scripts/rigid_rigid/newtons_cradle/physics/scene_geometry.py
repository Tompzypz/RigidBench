"""Shared tabletop and cradle suspension geometry, SI units."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
def table_parts(c):
    # A solid display cabinet replaces the four-legged desk. The top surface stays
    # at table_height so the cradle base sits flush; the taper below reads as a
    # museum plinth rather than office furniture.
    h=c['table_height']
    parts=[dict(name='Cabinet top',location=[0,0,h-.035],size=[1.24,.60,.07])]
    parts.append(dict(name='Cabinet body',location=[0,0,(h-.07+.06)/2],size=[1.12,.50,h-.07-.06]))
    parts.append(dict(name='Cabinet plinth',location=[0,0,.03],size=[1.18,.54,.06]))
    return parts

def pivots(c):
    spacing=2*c['ball_radius']+c['ball_gap']
    return [[(i-2)*spacing,0,c['pivot_height']] for i in range(5)]

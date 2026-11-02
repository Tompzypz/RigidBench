"""All blocks are separate bodies; no hidden supports, bonds or scripted collapse."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math

def building_blocks(c):
    """A two-piece pile: one upright block with a second block resting on top.

    The upper block is centred on the base block, so the pile stands still but
    loses its support as soon as the base is nudged clear of that centre. That
    shallow single contact is what makes the outcome sensitive to how hard the
    ball arrives.
    """
    blocks=[];top=c['table_height'];index=0
    def add(location,size,angle,group,color):
        nonlocal index
        blocks.append(dict(object_id=f'block_{index:02d}',location=location,size=size,
            angle=angle,mass=math.prod(size)*c['block_density'],group=group,color=color))
        index+=1
    base=[.07,.07,.16]
    upper=[.09,.09,.09]
    add([.35,0,top+base[2]/2],base,0,'base',1)
    add([.35,0,top+base[2]+upper[2]/2],upper,0,'top',2)
    return blocks

def table_parts(c):
    h=c['table_height'];parts=[dict(name='Oak play table',location=[.1,0,h-.045],size=[2.65,1.25,.09])]
    for x in (-1.05,1.25):
        for y in (-.52,.52):parts.append(dict(name='Table leg',location=[x,y,(h-.09)/2],size=[.30,.05,h-.09]))
    return parts

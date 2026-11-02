"""A furnished playroom; appearance only, physics lives in the simulator."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)

import sys
from pathlib import Path
sys.path.insert(0, str(_PCVE_ROOT / 'scripts'))
from pcve_blender_compat import (shader_socket, set_shader_input, eevee_engine, set_eevee_property, set_color_property)
from pathlib import Path
import math,random
ASSETS=_PCVE_ROOT/'assets'/'polyhaven'/'ball_block_building'
MODELS=_PCVE_ROOT/'assets'/'models'


def fitted_model(bpy,filename,name,size,center,flip=False):
    """Fit imported world-space geometry while preserving glTF UVs/materials.

    These are visual assets only; the simulation retains its existing boxes.
    Bake the complete import hierarchy before fitting, including axis conversion.
    """
    from mathutils import Vector,Matrix
    path=MODELS/filename
    if not path.is_file():raise FileNotFoundError(f'Missing room model: {path}')
    before=set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    bpy.context.view_layer.update()
    imported=set(bpy.data.objects)-before
    meshes=[obj for obj in imported if obj.type=='MESH']
    if not meshes:raise ValueError(f'No meshes in {path}')
    rotation=Matrix.Rotation(math.pi,4,'Z') if flip else Matrix.Identity(4)
    transforms={obj:rotation@obj.matrix_world.copy() for obj in meshes}
    points=[transforms[obj]@Vector(v) for obj in meshes for v in obj.bound_box]
    low=Vector([min(v[i] for v in points) for i in range(3)])
    high=Vector([max(v[i] for v in points) for i in range(3)])
    if min(high-low)<=0:raise ValueError(f'Degenerate model bounds: {path}')
    scale=Matrix.Diagonal(Vector([size[i]/(high[i]-low[i]) for i in range(3)]+[1]))
    fit=Matrix.Translation(Vector(center))@scale@Matrix.Translation(-(low+high)/2)
    for index,obj in enumerate(meshes):
        transform=fit@transforms[obj]
        obj.parent=None
        obj.matrix_world=Matrix.Identity(4)
        obj.data=obj.data.copy()
        obj.data.transform(transform)
        obj.name=f'{name} {index+1}'
    for obj in imported:
        if obj.type!='MESH':bpy.data.objects.remove(obj,do_unlink=True)
    bpy.context.view_layer.update()
    return meshes

def material(bpy,name,color,metal=0,roughness=.5):
    mat=bpy.data.materials.new(name);mat.diffuse_color=(*color,1);mat.use_nodes=True
    shader=mat.node_tree.nodes.get('Principled BSDF');shader.inputs['Base Color'].default_value=(*color,1);shader.inputs['Metallic'].default_value=metal;shader.inputs['Roughness'].default_value=roughness
    return mat

def wood(bpy,name,light=(.40,.24,.115),dark=(.20,.095,.038)):
    mat=material(bpy,name,light,roughness=.42);nodes=mat.node_tree.nodes;links=mat.node_tree.links
    coords=nodes.new('ShaderNodeTexCoord');scale=nodes.new('ShaderNodeVectorMath');scale.operation='MULTIPLY';scale.inputs[1].default_value=(2,65,4)
    links.new(coords.outputs['Generated'],scale.inputs[0]);noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=2.5;noise.inputs['Detail'].default_value=3
    links.new(scale.outputs[0],noise.inputs['Vector']);ramp=nodes.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].color=(*dark,1);ramp.color_ramp.elements[1].color=(*light,1)
    links.new(noise.outputs['Fac'],ramp.inputs[0]);shader=nodes.get('Principled BSDF');links.new(ramp.outputs['Color'],shader.inputs['Base Color'])
    bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.08;bump.inputs['Distance'].default_value=.00025
    links.new(noise.outputs['Fac'],bump.inputs['Height']);links.new(bump.outputs[0],shader.inputs['Normal']);return mat

def pbr_wood(bpy,name,floor=False):
    mat=material(bpy,name,(.28,.14,.06),roughness=.42);nodes=mat.node_tree.nodes;links=mat.node_tree.links;shader=nodes.get('Principled BSDF')
    tex=nodes.new('ShaderNodeTexCoord');mapping=nodes.new('ShaderNodeMapping');mapping.inputs['Scale'].default_value=(1.0,1.0,1.0)
    links.new(tex.outputs['Object'],mapping.inputs['Vector'])
    stem='wood_floor_worn' if floor else 'wood_table'
    for suffix,color_space,socket in [('diff','sRGB','Base Color'),('rough','Non-Color','Roughness'),('nor_gl','Non-Color',None)]:
        path=ASSETS/f'{stem}_{suffix}_2k.jpg'
        if not path.exists():
            if suffix=='diff':raise FileNotFoundError(f'{path}: run fetch_visual_assets.py once')
            continue
        img=bpy.data.images.load(str(path),check_existing=True);img.colorspace_settings.name=color_space
        node=nodes.new('ShaderNodeTexImage');node.image=img;node.projection='BOX';node.projection_blend=.18
        links.new(mapping.outputs['Vector'],node.inputs['Vector'])
        if socket:links.new(node.outputs['Color'],shader.inputs[socket])
        else:
            normal=nodes.new('ShaderNodeNormalMap');normal.inputs['Strength'].default_value=.24
            links.new(node.outputs['Color'],normal.inputs['Color']);links.new(normal.outputs['Normal'],shader.inputs['Normal'])
    set_shader_input(shader, 'Coat Weight', 0.16);set_shader_input(shader, 'Coat Roughness', 0.28)
    return mat

def textured_material(bpy,name,color,roughness=.5,metal=0,scale=160,bump_distance=.00012):
    mat=material(bpy,name,color,metal,roughness);nodes=mat.node_tree.nodes;links=mat.node_tree.links;shader=nodes.get('Principled BSDF')
    noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=scale;noise.inputs['Detail'].default_value=2
    rough=nodes.new('ShaderNodeMapRange');rough.inputs['From Min'].default_value=0;rough.inputs['From Max'].default_value=1
    rough.inputs['To Min'].default_value=roughness*.85;rough.inputs['To Max'].default_value=min(.95,roughness*1.15)
    links.new(noise.outputs['Fac'],rough.inputs[0]);links.new(rough.outputs[0],shader.inputs['Roughness'])
    bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.12;bump.inputs['Distance'].default_value=bump_distance
    links.new(noise.outputs['Fac'],bump.inputs['Height']);links.new(bump.outputs[0],shader.inputs['Normal']);return mat

def box(bpy,name,location,size,mat,pitch=0,bevel=0):
    bpy.ops.mesh.primitive_cube_add(size=1,location=location);obj=bpy.context.object;obj.name=name;obj.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);obj.rotation_euler[1]=pitch;obj.data.materials.append(mat)
    if bevel:
        mod=obj.modifiers.new('Manufactured edge','BEVEL');mod.width=bevel;mod.segments=3;obj.modifiers.new('Weighted normals','WEIGHTED_NORMAL')
    return obj

def cylinder(bpy,name,location,radius,depth,mat,vertices=40):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices,radius=radius,depth=depth,location=location);obj=bpy.context.object;obj.name=name;obj.data.materials.append(mat)
    for poly in obj.data.polygons:poly.use_smooth=True
    bevel=obj.modifiers.new('Soft rim','BEVEL');bevel.width=min(.003,radius*.08);bevel.segments=3;obj.modifiers.new('Weighted normals','WEIGHTED_NORMAL');return obj

def rod(bpy,name,start,end,radius,mat):
    from mathutils import Vector
    a,b=Vector(start),Vector(end);v=b-a;obj=cylinder(bpy,name,(a+b)/2,radius,v.length,mat,20);obj.rotation_euler=v.to_track_quat('Z','Y').to_euler();return obj

def plant(bpy,name,location,size=1):
    from mathutils import Vector
    x,y,z=location;terracotta=textured_material(bpy,name+' ceramic',(.25,.09,.047),.78)
    bpy.ops.mesh.primitive_cone_add(vertices=48,radius1=.073*size,radius2=.092*size,depth=.16*size,location=[x,y,z+.08*size]);pot=bpy.context.object;pot.name=name+' planter';pot.data.materials.append(terracotta)
    for poly in pot.data.polygons:poly.use_smooth=True
    cylinder(bpy,name+' pot lip',[x,y,z+.156*size],.094*size,.016*size,terracotta)
    soil=material(bpy,name+' soil',(.033,.02,.012),roughness=.95);cylinder(bpy,name+' soil',[x,y,z+.16*size],.079*size,.004*size,soil)
    leaf_mats=[material(bpy,name+f' leaf {i}',color,roughness=.44) for i,color in enumerate(((.045,.11,.025),(.085,.17,.04),(.14,.22,.06)))]
    rng=random.Random(28)
    for i in range(13):
        angle=i*2.4;length=rng.uniform(.22,.42)*size;stem_start=Vector([x,y,z+.16*size]);end=stem_start+Vector([math.cos(angle)*.10*size,math.sin(angle)*.10*size,length])
        rod(bpy,name+' stem',stem_start,end,.002*size,leaf_mats[0])
        direction=Vector([math.cos(angle)*.7,math.sin(angle)*.7,.45]);bpy.ops.mesh.primitive_uv_sphere_add(segments=16,ring_count=8,location=end)
        leaf=bpy.context.object;leaf.name=name+' tapered leaf';leaf.scale=(.035*size,.008*size,.13*size);leaf.rotation_euler=direction.to_track_quat('Z','Y').to_euler();leaf.data.materials.append(leaf_mats[i%3])
        for poly in leaf.data.polygons:poly.use_smooth=True

def book(bpy,name,location,size,color):
    cover=material(bpy,name+' cover',color,roughness=.6);pages=textured_material(bpy,name+' paper',(.62,.57,.45),.86,scale=220)
    x,y,z=location;w,d,h=size
    box(bpy,name+' page block',[x,y,z],[w*.87,d*.93,h*.98],pages,bevel=.001)
    for side in (-1,1):box(bpy,name+' bound cover',[x+side*w*.46,y,z],[.008,d,h],cover,bevel=.002)
    box(bpy,name+' spine',[x,y-d/2,z],[w,.009,h],cover,bevel=.002)
    foil=material(bpy,name+' spine lettering',(.54,.40,.19),metal=.55)
    for shift in (-.33,.28):box(bpy,name+' spine bands',[x,y-d/2-.005,z+h*shift],[w*.78,.001,.004],foil)

ENVIRONMENT_THEME='playroom_imported_desk_blackboard'

def build_room(bpy,c):
    from building_geometry import table_parts
    # --- Materials -----------------------------------------------------------
    oak=wood(bpy,'Warm oak furniture',(.48,.33,.17),(.27,.17,.075));oak.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value=.48
    floor=pbr_wood(bpy,'Warm oak playroom floor',floor=True)
    wall=textured_material(bpy,'Warm white playroom wall',(.68,.64,.56),.94,scale=90,bump_distance=.00012)
    # --- Floor + walls -------------------------------------------------------
    box(bpy,'Warm oak floor',[0,0,-.04],[14,14,.08],floor)
    back=1.35
    box(bpy,'Playroom side wall',[-3,0,1.55],[.10,4,3.1],wall)
    # Skirting must touch the back-wall face (y=back) or it floats and casts a
    # false seam down the wall below the board.
    box(bpy,'Oak skirting',[.3,back-.0175,.06],[6.4,.035,.12],oak,bevel=.004)
    # --- Room shell: full back wall so the board sits on plaster, not void ----
    box(bpy,'Playroom back wall',[.5,back+.05,1.55],[7,.10,3.1],wall)
    # --- Framed chalkboard replaces the recurring window ----------------------
    fitted_model(bpy,'realistic_blackboard.glb','Imported realistic blackboard',
        (4.4,.071,1.98),(0,back-.04,1.65))
    # Slatted toy basket on the visible floor beside the left table leg.
    bx,by=-.65,-.25
    basket=wood(bpy,'Basket pale timber',(.52,.37,.22),(.32,.21,.11))
    box(bpy,'Basket base',[bx,by,.025],[.44,.32,.05],basket,bevel=.008)
    for z in (.085,.155,.225):
        for side in (-1,1):
            box(bpy,'Basket long slat',[bx,by+side*.15,z],[.44,.022,.05],basket,bevel=.003)
            box(bpy,'Basket end slat',[bx+side*.21,by,z],[.022,.30,.05],basket,bevel=.003)
    for dx in (-.20,.20):
        for dy in (-.14,.14):box(bpy,'Basket corner',[bx+dx,by+dy,.145],[.026,.026,.26],basket,bevel=.003)
    for i,(dx,dy,z,color) in enumerate([(-.10,0,.18,(.24,.42,.44)),(.045,.035,.21,(.61,.28,.18)),(.10,-.06,.14,(.65,.48,.22))]):
        toy=box(bpy,f'Basket toy {i}',[bx+dx,by+dy,z],[.11,.10,.13],material(bpy,f'Basket toy paint {i}',color,roughness=.65),bevel=.005)
        toy.rotation_euler=(.15*i,.12*i,.3*i)
    # --- Colourful bunting across the top, inside the camera frame ------------
    rod(bpy,'Bunting string',[-1.6,back-.14,2.36],[1.6,back-.14,2.36],.003,material(bpy,'Bunting cord',(.82,.78,.70),roughness=.8))
    flag_colors=[(.78,.32,.30),(.30,.55,.70),(.88,.62,.20),(.45,.65,.38),(.55,.38,.70),(.88,.52,.22)]
    for i in range(7):
        fx=-1.5+i*.5
        bpy.ops.mesh.primitive_cone_add(vertices=3,radius1=.10,depth=.20,location=[fx,back-.14,2.26])
        flag=bpy.context.object;flag.name='Bunting flag '+str(i);flag.rotation_euler[0]=math.pi;flag.data.materials.append(material(bpy,'Bunting flag '+str(i),flag_colors[i%6],roughness=.6))
    # --- Coloured blocks scattered on the floor ------------------------------
    block_colors=[(.78,.32,.30),(.30,.55,.70),(.88,.62,.20),(.45,.65,.38),(.55,.38,.70)]
    for i,(bx,by,bs) in enumerate([(-1.55,1.05,.09),(-1.35,1.12,.075),(-1.45,.95,.11),(-1.18,.98,.08)]):
        box(bpy,'Floor block '+str(i),[bx,by,bs/2],[bs,bs,bs],material(bpy,'Floor block colour '+str(i),block_colors[i],roughness=.55),bevel=.006)
    # Share the collision footprint so the smaller visible desk remains physical.
    tabletop=table_parts(c)[0]
    fitted_model(bpy,'office_desk___6mb.glb','Imported office desk',
        (*tabletop['size'][:2],c['table_height']),(.1,0,c['table_height']/2))
    # Keep the plant's native proportions; its base rests on the desktop.
    # Rear-left placement mirrors the old rear-right spot across the diagonal,
    # so the visible lane (y=0) from the ball's start to the stack stays clear.
    height=.40
    plant_size=(height*1.08056697/1.06488935,height*1.03534520/1.06488935,height)
    # Place the complete foliage bounds 6 cm inside both rear/left edges,
    # rather than positioning only the pot centre near an edge.
    edge_margin=.06
    plant_center=(tabletop['location'][0]-(tabletop['size'][0]-plant_size[0])/2+edge_margin,
        tabletop['location'][1]+(tabletop['size'][1]-plant_size[1])/2-edge_margin,
        c['table_height']+height/2)
    fitted_model(bpy,'indoor_plant.glb','Imported tabletop plant',
        plant_size,plant_center)
    return oak


def configure_lighting(bpy,scene):
    """Broad key plus low frontal fill retain detail under the desk."""
    from mathutils import Vector
    world=bpy.data.worlds.new('Neutral room ambient');scene.world=world;world.use_nodes=True
    background=world.node_tree.nodes.get('Background')
    background.inputs['Color'].default_value=(.78,.84,1.0,1)
    background.inputs['Strength'].default_value=.28
    # A large emitter softens shadows without a spotlight cone on the tabletop.
    # Keep the fill weak so the ball has one dominant highlight and shadow.
    for name,location,target,power,size,color in [
        ('Large soft key',[-1.5,-1.0,3.5],[.1,0,.72],320,2.4,(1.0,.95,.87)),
        ('Soft room fill',[2.2,-.8,2.8],[.1,.4,1.0],45,2.0,(.86,.92,1.0)),
        ('Low front-left bounce',[-1.8,-2.6,1.05],[0,0,.35],110,2.2,(1.0,.96,.90))]:
        bpy.ops.object.light_add(type='AREA',location=location)
        obj=bpy.context.object;obj.name=name;obj.data.energy=power
        obj.data.shape='DISK';obj.data.size=size;obj.data.color=color
        obj.rotation_euler=(Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler()

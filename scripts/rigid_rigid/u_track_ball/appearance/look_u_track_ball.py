"""A furnished home work corner; appearance only, physics lives in track_geometry."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)

import sys
from pathlib import Path
sys.path.insert(0, str(_PCVE_ROOT / 'scripts'))
from pcve_blender_compat import (shader_socket, set_shader_input, eevee_engine, set_eevee_property, set_color_property)
from pathlib import Path
import math,random
ASSETS=_PCVE_ROOT/'assets'/'polyhaven'/'u_track_ball'
MODELS=_PCVE_ROOT/'assets'/'models'

def fitted_model(bpy,filename,name,height,center,yaw=0):
    """Place a downloaded furniture mesh at real-world size, feet on the floor.

    Uniform scale only: a table squashed along one axis reads as wrong immediately.
    These are visual assets; the simulation keeps its own primitives.
    """
    from mathutils import Vector,Matrix
    path=MODELS/filename
    if not path.is_file():raise FileNotFoundError(f'Missing furniture model: {path}')
    before=set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    bpy.context.view_layer.update()
    imported=set(bpy.data.objects)-before
    meshes=[obj for obj in imported if obj.type=='MESH']
    if not meshes:raise ValueError(f'No meshes in {path}')
    # Bake the whole import hierarchy (axis conversion, node offsets) into world space.
    transforms={obj:obj.matrix_world.copy() for obj in meshes}
    points=[transforms[obj]@Vector(v) for obj in meshes for v in obj.bound_box]
    low=Vector([min(v[i] for v in points) for i in range(3)])
    high=Vector([max(v[i] for v in points) for i in range(3)])
    if high.z-low.z<=0:raise ValueError(f'Degenerate model bounds: {path}')
    factor=height/(high.z-low.z)
    fit=Matrix.Translation(Vector([center[0],center[1],0]))@Matrix.Rotation(yaw,4,'Z')@Matrix.Diagonal(Vector([factor]*3+[1]))@Matrix.Translation(-Vector([(low.x+high.x)/2,(low.y+high.y)/2,low.z]))
    for index,obj in enumerate(meshes):
        obj.parent=None
        obj.matrix_world=Matrix.Identity(4)
        obj.data=obj.data.copy()
        obj.data.transform(fit@transforms[obj])
        obj.name=f'{name} {index+1}'
    for obj in imported:
        if obj.type!='MESH':bpy.data.objects.remove(obj,do_unlink=True)
    bpy.context.view_layer.update()
    return meshes

def tint_imported(bpy,meshes,color,roughness=None):
    """Push a downloaded model's albedo towards this room's palette.

    The glTF ships its own scanned texture; multiplying it keeps every joint,
    grain line and drawer gap while moving the whole piece to a warmer timber.
    """
    seen=set()
    for obj in meshes:
        for slot in obj.material_slots:
            mat=slot.material
            if not mat or mat.name in seen or not mat.use_nodes:continue
            seen.add(mat.name);nodes,links=mat.node_tree.nodes,mat.node_tree.links
            shader=next((n for n in nodes if n.type=='BSDF_PRINCIPLED'),None)
            if not shader:continue
            base=shader.inputs['Base Color']
            source=base.links[0].from_socket if base.is_linked else None
            mix=nodes.new('ShaderNodeMix');mix.data_type='RGBA';mix.blend_type='MULTIPLY'
            mix.inputs['Factor'].default_value=1
            if source:links.new(source,mix.inputs['A'])
            else:mix.inputs['A'].default_value=tuple(base.default_value)
            mix.inputs['B'].default_value=(*color,1)
            links.new(mix.outputs['Result'],base)
            if roughness is not None:
                for socket in ('Roughness',):
                    if not shader.inputs[socket].is_linked:shader.inputs[socket].default_value=roughness
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
    if floor:
        # A 2.8 m scan contains about twelve real boards, rather than stretching
        # the scan over the entire room. The scan includes seams and worn knots.
        mapping.inputs['Scale'].default_value=(1/2.8,1/2.8,1/2.8)
        shader.inputs['Roughness'].default_value=.78
        set_shader_input(shader, 'Coat Weight', 0.025)
        set_shader_input(shader, 'Coat Roughness', 0.65)
        diffuse=next(n for n in nodes if n.type=='TEX_IMAGE' and '_diff_' in n.image.name)
        bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.28;bump.inputs['Distance'].default_value=.0018
        links.new(diffuse.outputs['Color'],bump.inputs['Height']);links.new(bump.outputs['Normal'],shader.inputs['Normal'])
    else:
        set_shader_input(shader, 'Coat Weight', 0.16);set_shader_input(shader, 'Coat Roughness', 0.28)
    return mat

def _coords(nodes,links,scale=(1,1,1)):
    """Object-space coordinates in metres; scale stretches texture features."""
    tex=nodes.new('ShaderNodeTexCoord');mapping=nodes.new('ShaderNodeMapping')
    mapping.inputs['Scale'].default_value=scale;links.new(tex.outputs['Object'],mapping.inputs['Vector']);return mapping

def _noise(nodes,links,vector,scale,detail=3,roughness=.5,distortion=0):
    node=nodes.new('ShaderNodeTexNoise');node.inputs['Scale'].default_value=scale
    node.inputs['Detail'].default_value=detail;node.inputs['Roughness'].default_value=roughness
    node.inputs['Distortion'].default_value=distortion;links.new(vector,node.inputs['Vector']);return node

def _range(nodes,links,source,low,high):
    node=nodes.new('ShaderNodeMapRange');node.inputs['To Min'].default_value=low;node.inputs['To Max'].default_value=high
    links.new(source,node.inputs['Value']);return node

def _bump(nodes,links,height,strength,distance,normal=None):
    node=nodes.new('ShaderNodeBump');node.inputs['Strength'].default_value=strength;node.inputs['Distance'].default_value=distance
    links.new(height,node.inputs['Height'])
    if normal is not None:links.new(normal,node.inputs['Normal'])
    return node

def varnished_worktop(bpy,name):
    """Oiled birch bench top: bent grain, open pores, no lacquer film."""
    mat=material(bpy,name,(.46,.33,.18),roughness=.5);nodes=mat.node_tree.nodes;links=mat.node_tree.links
    shader=nodes.get('Principled BSDF')
    # X is the slab's length: every pattern is stretched along it so grain lines run true.
    grain=_coords(nodes,links,(1.0,7.0,7.0))
    # No sawn board has dead-straight fibres: the growth rings and the saw wander
    # sideways over tens of centimetres, which is what stops a top looking printed.
    bend=_noise(nodes,links,_coords(nodes,links,(1.0,1.05,1.05)).outputs['Vector'],1.1,4,.55)
    bias=nodes.new('ShaderNodeMath');bias.operation='MULTIPLY_ADD'
    links.new(bend.outputs['Fac'],bias.inputs[0]);bias.inputs[1].default_value=-.26;bias.inputs[2].default_value=.13
    shift=nodes.new('ShaderNodeCombineXYZ');links.new(bias.outputs[0],shift.inputs['Y'])
    warped=nodes.new('ShaderNodeVectorMath');warped.operation='ADD'
    links.new(grain.outputs['Vector'],warped.inputs[0]);links.new(shift.outputs[0],warped.inputs[1])
    def wave(scale,distortion,detail,detail_scale):
        node=nodes.new('ShaderNodeTexWave');node.wave_type='BANDS';node.bands_direction='Y'
        node.inputs['Scale'].default_value=scale;node.inputs['Distortion'].default_value=distortion
        node.inputs['Detail'].default_value=detail;node.inputs['Detail Scale'].default_value=detail_scale
        links.new(warped.outputs[0],node.inputs['Vector']);return node
    # One distorted band set carries the whole figure; a second, finer set on top
    # of it reads as corduroy rather than timber.
    broad=wave(2.4,9.0,4,1.6)
    # Slow irregularity: no two metres of a real slab look the same.
    drift=nodes.new('ShaderNodeMath');drift.operation='MULTIPLY_ADD'
    links.new(_noise(nodes,links,_coords(nodes,links,(1.0,2.2,2.2)).outputs['Vector'],1.1,3,.5).outputs['Fac'],drift.inputs[0])
    drift.inputs[1].default_value=.20;drift.inputs[2].default_value=-.07
    tone=nodes.new('ShaderNodeMath');tone.operation='ADD';links.new(broad.outputs['Fac'],tone.inputs[0]);links.new(drift.outputs[0],tone.inputs[1])
    ramp=nodes.new('ShaderNodeValToRGB');ramp.color_ramp.interpolation='EASE'
    ramp.color_ramp.elements[0].position=.18;ramp.color_ramp.elements[0].color=(.058,.035,.017,1)
    ramp.color_ramp.elements[1].position=.48;ramp.color_ramp.elements[1].color=(.190,.137,.075,1)
    extra=ramp.color_ramp.elements.new(.86);extra.color=(.216,.162,.094,1)
    links.new(tone.outputs[0],ramp.inputs[0]);links.new(ramp.outputs['Color'],shader.inputs['Base Color'])
    # Oiled, unpolished timber: the surface scatters almost everything and the
    # little that does mirror the room is broken up by the open pores.
    pore_coords=_coords(nodes,links,(2.0,320,320))
    pores=_noise(nodes,links,pore_coords.outputs['Vector'],3.0,3,.6)
    sheen=nodes.new('ShaderNodeMath');sheen.operation='MULTIPLY_ADD'
    links.new(pores.outputs['Fac'],sheen.inputs[0]);sheen.inputs[1].default_value=.13
    links.new(tone.outputs[0],sheen.inputs[2])
    links.new(_range(nodes,links,sheen.outputs[0],.68,.92).outputs[0],shader.inputs['Roughness'])
    # No lacquer film: a coat would put a smooth IOR 1.5 layer over the whole slab
    # and turn a sawn board into a mirror. Only a faint wax rub remains.
    set_shader_input(shader, 'Coat Weight', 0.0)
    links.new(_range(nodes,links,_noise(nodes,links,_coords(nodes,links,(2.0,3.4,3.4)).outputs['Vector'],1.0,3,.5).outputs['Fac'],.52,.78).outputs[0],shader_socket(shader, 'Coat Roughness'))
    # Bare timber reflects well below glass or varnish (F0 ~0.008 here).
    for socket in ('Specular IOR Level','Specular'):
        if socket in shader.inputs:shader.inputs[socket].default_value=.10;break
    # Grain relief is shallow; the pores and polishing marks carry the micro detail.
    grain_bump=_bump(nodes,links,tone.outputs[0],.16,.00022)
    pore_bump=_bump(nodes,links,pores.outputs['Fac'],.34,.00005,grain_bump.outputs['Normal'])
    polish=_noise(nodes,links,_coords(nodes,links,(30,1400,1400)).outputs['Vector'],1.0,3,.6)
    polish_bump=_bump(nodes,links,polish.outputs['Fac'],.13,.00003,pore_bump.outputs['Normal'])
    links.new(polish_bump.outputs['Normal'],shader.inputs['Normal'])
    return mat

def enamel_finish(bpy,name,color):
    """Sprayed enamel over steel: a polished running band, dusty walls, orange peel."""
    mat=material(bpy,name,color,metal=.07,roughness=.34);nodes=mat.node_tree.nodes;links=mat.node_tree.links
    shader=nodes.get('Principled BSDF');mapping=_coords(nodes,links)
    # The ball only ever touches the middle of the trough: that strip is rubbed clean,
    # the walls keep settling dust. |Y| is the distance from the running line.
    geometry=nodes.new('ShaderNodeNewGeometry');split=nodes.new('ShaderNodeSeparateXYZ')
    links.new(geometry.outputs['Position'],split.inputs['Vector'])
    across=nodes.new('ShaderNodeMath');across.operation='ABSOLUTE';links.new(split.outputs['Y'],across.inputs[0])
    band=nodes.new('ShaderNodeMath');band.operation='MULTIPLY';links.new(across.outputs[0],band.inputs[0]);band.inputs[1].default_value=7.4
    wear=nodes.new('ShaderNodeMath');wear.operation='ADD'
    links.new(band.outputs[0],wear.inputs[0]);links.new(_noise(nodes,links,_coords(nodes,links,(1.4,1.4,1.4)).outputs['Vector'],1.0,3,.6).outputs['Fac'],wear.inputs[1])
    links.new(_range(nodes,links,wear.outputs[0],.10,.40).outputs[0],shader.inputs['Roughness'])
    tint=nodes.new('ShaderNodeValToRGB');tint.color_ramp.interpolation='EASE'
    tint.color_ramp.elements[0].position=.12;tint.color_ramp.elements[0].color=(color[0]*1.55,color[1]*1.30,color[2]*1.28,1)
    tint.color_ramp.elements[1].position=.95;tint.color_ramp.elements[1].color=(color[0]*.82,color[1]*.80,color[2]*.80,1)
    links.new(wear.outputs[0],tint.inputs[0]);links.new(tint.outputs['Color'],shader.inputs['Base Color'])
    set_shader_input(shader, 'Coat Weight', 0.34)
    links.new(_range(nodes,links,_noise(nodes,links,mapping.outputs['Vector'],4.5,4,.6).outputs['Fac'],.05,.22).outputs[0],shader_socket(shader, 'Coat Roughness'))
    streaks=_noise(nodes,links,_coords(nodes,links,(2,240,240)).outputs['Vector'],1.0,3,.55)
    peel=_noise(nodes,links,mapping.outputs['Vector'],60,2,.5)
    grit=_noise(nodes,links,mapping.outputs['Vector'],430,2,.5)
    rolled=_bump(nodes,links,streaks.outputs['Fac'],.40,.00055)
    skin=_bump(nodes,links,peel.outputs['Fac'],.34,.00075,rolled.outputs['Normal'])
    dusty=_bump(nodes,links,grit.outputs['Fac'],.18,.00005,skin.outputs['Normal'])
    links.new(dusty.outputs['Normal'],shader.inputs['Normal'])
    return mat

def brushed_aluminium(bpy,name,color):
    """Anodised rail with lengthwise brush marks instead of uniform gloss."""
    mat=material(bpy,name,color,metal=.78,roughness=.40);nodes=mat.node_tree.nodes;links=mat.node_tree.links
    shader=nodes.get('Principled BSDF');mapping=_coords(nodes,links)
    brush=_noise(nodes,links,_coords(nodes,links,(5,700,700)).outputs['Vector'],1.0,4,.62)
    links.new(_range(nodes,links,brush.outputs['Fac'],.30,.54).outputs[0],shader.inputs['Roughness'])
    grain=_bump(nodes,links,brush.outputs['Fac'],.45,.00006)
    links.new(grain.outputs['Normal'],shader.inputs['Normal'])
    return mat

def textured_material(bpy,name,color,roughness=.5,metal=0,scale=160,bump_distance=.00012):
    mat=material(bpy,name,color,metal,roughness);nodes=mat.node_tree.nodes;links=mat.node_tree.links;shader=nodes.get('Principled BSDF')
    noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=scale;noise.inputs['Detail'].default_value=2
    rough=nodes.new('ShaderNodeMapRange');rough.inputs['From Min'].default_value=0;rough.inputs['From Max'].default_value=1
    rough.inputs['To Min'].default_value=roughness*.85;rough.inputs['To Max'].default_value=min(.95,roughness*1.15)
    links.new(noise.outputs['Fac'],rough.inputs[0]);links.new(rough.outputs[0],shader.inputs['Roughness'])
    bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.12;bump.inputs['Distance'].default_value=bump_distance
    links.new(noise.outputs['Fac'],bump.inputs['Height']);links.new(bump.outputs[0],shader.inputs['Normal']);return mat

def mineral_surface(bpy,name,color,floor=False):
    """World-scale mineral texture: broad mottling, trowel grain and fine pores."""
    mat=material(bpy,name,color,roughness=.9)
    nodes=mat.node_tree.nodes;links=mat.node_tree.links;shader=nodes.get('Principled BSDF')
    # Position keeps the grain at a consistent physical size across wall pieces.
    geometry=nodes.new('ShaderNodeNewGeometry')
    def noise(label,scale,detail):
        node=nodes.new('ShaderNodeTexNoise');node.label=label
        node.inputs['Scale'].default_value=scale;node.inputs['Detail'].default_value=detail
        node.inputs['Roughness'].default_value=.72
        links.new(geometry.outputs['Position'],node.inputs['Vector']);return node
    clouds=noise('Subtle mineral / plaster colour variation',2.8,4)
    grain=noise('Aggregate' if floor else 'Trowelled plaster grain',95 if floor else 48,3)
    pores=noise('Fine mineral pores',650,2)
    tint=nodes.new('ShaderNodeValToRGB')
    tint.color_ramp.elements[0].position=.18;tint.color_ramp.elements[0].color=(*(v*.78 for v in color),1)
    tint.color_ramp.elements[1].position=.82;tint.color_ramp.elements[1].color=(*(v*1.12 for v in color),1)
    links.new(clouds.outputs['Fac'],tint.inputs[0]);links.new(tint.outputs['Color'],shader.inputs['Base Color'])
    rough=nodes.new('ShaderNodeMapRange');rough.inputs['To Min'].default_value=.76 if floor else .82;rough.inputs['To Max'].default_value=.98
    links.new(grain.outputs['Fac'],rough.inputs[0]);links.new(rough.outputs[0],shader.inputs['Roughness'])
    fine=nodes.new('ShaderNodeBump');fine.inputs['Strength'].default_value=.32;fine.inputs['Distance'].default_value=.00045
    links.new(pores.outputs['Fac'],fine.inputs['Height'])
    bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.48;bump.inputs['Distance'].default_value=.003 if floor else .0025
    links.new(grain.outputs['Fac'],bump.inputs['Height']);links.new(fine.outputs['Normal'],bump.inputs['Normal']);links.new(bump.outputs['Normal'],shader.inputs['Normal'])
    return mat


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

def plant(bpy,name,location,size=1,pot_color=(.25,.09,.047)):
    from mathutils import Vector
    x,y,z=location;terracotta=textured_material(bpy,name+' ceramic',pot_color,.78)
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

ENVIRONMENT_THEME='home_workshop'

def build_room(bpy,c):
    from track_geometry import table_parts,surface
    # Physical tabletop dimensions and all contact surfaces remain identical.
    top=varnished_worktop(bpy,'Pale birch worktop')
    steel=textured_material(bpy,'Black powder coated workbench frame',(.024,.031,.035),.56,metal=.42,scale=240,bump_distance=.000035)
    wall=mineral_surface(bpy,'Cool grey workshop plaster',(.29,.34,.35))
    flooring=pbr_wood(bpy,'Worn warm oak plank flooring',floor=True)
    trim=material(bpy,'Grey aluminium window frame',(.43,.48,.49),metal=.5,roughness=.37)
    box(bpy,'Matte wooden plank floor',[0,0,-.045],[12,12,.09],flooring)
    for name,loc,size in [('Wall left',[-2.65,1.95,1.55],[.7,.10,3.1]),('Wall right',[1.65,1.95,1.55],[4.7,.10,3.1]),('Below window',[-1.5,1.95,.60],[1.6,.10,1.2]),('Above window',[-1.5,1.95,2.9],[1.6,.10,.4])]:box(bpy,name,loc,size,wall)
    box(bpy,'Workshop return wall',[-3,0,1.55],[.1,4,3.1],wall)
    box(bpy,'Dark base trim',[0,1.88,.06],[7,.035,.12],steel,bevel=.002)
    for x in (-2.31,-1.5,-.69):box(bpy,'Window vertical',[x,1.89,1.95],[.035,.075,1.55],trim,bevel=.003)
    for z in (1.18,1.95,2.72):box(bpy,'Window horizontal',[-1.5,1.89,z],[1.66,.075,.035],trim,bevel=.003)
    box(bpy,'Metal windowsill',[-1.5,1.78,1.17],[1.76,.24,.025],trim,bevel=.004)
    blind=material(bpy,'Grey roller blind',(.25,.29,.30),roughness=.88)
    box(bpy,'Rolled window shade',[-1.5,1.79,2.67],[1.67,.04,.13],blind,bevel=.015)
    for part in table_parts(c):box(bpy,part['name'],part['location'],part['size'],top if part['kind']=='wood' and part['name']=='Oak worktable' else steel,bevel=.005)
    # Cross braces below the surface establish the steel workbench silhouette.
    for y in (-.43,.43):box(bpy,'Steel lower brace',[.4,y,.18],[2.8,.035,.035],steel,bevel=.003)
    panel=wood(bpy,'Birch tool pegboard',(.31,.21,.12),(.17,.105,.052));dark=material(bpy,'Peg holes',(.013,.016,.018),roughness=.95)
    box(bpy,'Tool pegboard',[.72,1.885,1.50],[1.75,.025,.99],panel,bevel=.007)
    for i in range(22):
        for j in range(12):
            hole=cylinder(bpy,'Pegboard hole',[-.08+i*.074,1.869,1.09+j*.075],.004,.001,dark,12);hole.rotation_euler[0]=math.pi/2
    bright_metal=material(bpy,'Workshop tool steel',(.25,.30,.31),metal=.83,roughness=.31)
    for x,color in ((.10,(.13,.27,.24)),(.27,(.42,.10,.055)),(.44,(.35,.31,.09))):
        cylinder(bpy,'Screwdriver handle',[x,1.83,1.58],.013,.105,textured_material(bpy,'Tool handle',color,.60))
        rod(bpy,'Screwdriver blade',[x,1.83,1.53],[x,1.83,1.40],.003,bright_metal)
    rod(bpy,'Hammer handle',[.75,1.82,1.39],[.75,1.82,1.70],.012,wood(bpy,'Hammer ash handle'))
    box(bpy,'Hammer head',[.75,1.82,1.71],[.13,.045,.035],bright_metal,bevel=.007)
    box(bpy,'Tape measure',[1.08,1.82,1.47],[.07,.042,.065],material(bpy,'Tape measure yellow',(.61,.35,.035)),bevel=.014)
    box(bpy,'Tape measure inset',[1.08,1.795,1.47],[.035,.002,.025],steel,bevel=.004)
    # The tool cabinet is gone: a downloaded desk stands under the pegboard.
    desk_top=.92
    desk=fitted_model(bpy,'desk.glb','Imported desk',desk_top,[.72,1.56],math.pi/2)
    tint_imported(bpy,desk,(.42,.31,.22),roughness=.55)
    # Two small things on the desk so it does not read as an empty slab.
    plant(bpy,'Desk rubber plant',[.30,1.60,desk_top],.55,pot_color=(.135,.125,.115))
    book(bpy,'Desk manual',[1.24,1.58,desk_top+.014],[.21,.155,.028],(.15,.20,.26))
    book(bpy,'Desk notebook',[1.26,1.56,desk_top+.045],[.185,.14,.021],(.36,.17,.10))
    # Keep table decorations outside the complete box and ball motion corridor.
    box(bpy,'Workshop notebook',[1.78,.38,c['table_height']+.012],[.24,.22,.024],material(bpy,'Workshop notebook cover',(.08,.15,.17)),bevel=.003)
    for x in (-.75,-.3,.25,.54):
        z,_=surface(x,c);h=z-c['track_thickness']-c['table_height']
        for y in (-.065,.065):box(bpy,'Track support',[x,y,c['table_height']+h/2],[.025,.025,h],steel,bevel=.002)
    box(bpy,'Support foot',[0,0,c['table_height']+.006],[1.8,.27,.012],steel,bevel=.005)
    for x in (-.8,.7):
        for y in (-.105,.105):cylinder(bpy,'Support fastener',[x,y,c['table_height']+.014],.005,.004,bright_metal,20)
    return top


def configure_lighting(bpy,scene):
    from mathutils import Vector
    world=bpy.data.worlds.new('Wooden lounge HDR lighting');scene.world=world;world.use_nodes=True
    nodes=world.node_tree.nodes;links=world.node_tree.links;tex=nodes.new('ShaderNodeTexEnvironment')
    path=ASSETS/'wooden_lounge_2k.hdr'
    if not path.exists():raise FileNotFoundError(f'{path}: run fetch_visual_assets.py once')
    tex.image=bpy.data.images.load(str(path),check_existing=True)
    mapping=nodes.new('ShaderNodeMapping');mapping.inputs['Rotation'].default_value[2]=1.2;coords=nodes.new('ShaderNodeTexCoord')
    links.new(coords.outputs['Generated'],mapping.inputs['Vector']);links.new(mapping.outputs['Vector'],tex.inputs['Vector'])
    background=nodes.get('Background');background.inputs['Strength'].default_value=.21;links.new(tex.outputs['Color'],background.inputs['Color'])
    for name,location,target,power,size,color in [
        ('Window daylight',[-1.45,1.59,2.32],[.3,0,.75],400,1.35,(1,.97,.90)),
        ('Large camera bounce',[1,-2.7,2.4],[.3,0,.9],58,1.8,(.72,.84,1.0)),
        ('Right wall bounce',[2.5,.6,2.1],[.5,0,.9],46,1.6,(.85,.93,1.0))]:
        bpy.ops.object.light_add(type='AREA',location=location);obj=bpy.context.object;obj.name=name;obj.data.energy=power;obj.data.shape='DISK';obj.data.size=size;obj.data.color=color
        obj.rotation_euler=(Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler()
    bpy.ops.object.light_add(type='SUN',location=[-3,2,5]);sun=bpy.context.object;sun.name='Soft afternoon sun';sun.data.energy=.55;sun.data.angle=.16;sun.data.color=(1,.96,.87)
    sun.rotation_euler=(Vector([.5,-.5,.72])-sun.location).to_track_quat('-Z','Y').to_euler()

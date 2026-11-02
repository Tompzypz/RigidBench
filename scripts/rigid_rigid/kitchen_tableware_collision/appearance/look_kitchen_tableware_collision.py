"""Imported kitchen architecture, physically sized ceramic dishes and PBR details."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math
from pathlib import Path
from scene_geometry import PROFILE,COM_HEIGHT,COUNTER_Z

APPEARANCE_VERSION=1
MODELS=_PCVE_ROOT/'assets'/'models'


def material(bpy,name,color,roughness=.35,metallic=0.):
    m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True
    bs=m.node_tree.nodes.get('Principled BSDF')
    bs.inputs['Base Color'].default_value=(*color,1)
    bs.inputs['Roughness'].default_value=roughness;bs.inputs['Metallic'].default_value=metallic
    return m


def ceramic(bpy,name,color):
    m=material(bpy,name,color,.23);nt=m.node_tree;n=nt.nodes;l=nt.links
    bs=n.get('Principled BSDF')
    if bs.inputs.get('Coat Weight'):bs.inputs['Coat Weight'].default_value=.32
    if bs.inputs.get('Coat Roughness'):bs.inputs['Coat Roughness'].default_value=.19
    tex=n.new('ShaderNodeTexNoise');tex.inputs['Scale'].default_value=650;tex.inputs['Detail'].default_value=2
    ramp=n.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].position=.58
    ramp.color_ramp.elements[0].color=(*color,1)
    ramp.color_ramp.elements[1].position=.77
    ramp.color_ramp.elements[1].color=(*(v*.45 for v in color),1)
    l.new(tex.outputs['Fac'],ramp.inputs[0]);l.new(ramp.outputs[0],bs.inputs['Base Color'])
    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.10;bump.inputs['Distance'].default_value=.00012
    l.new(tex.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs[0],bs.inputs['Normal'])
    return m


def stone(bpy):
    m=material(bpy,'Honed ivory quartz - micro mineral grain',(.63,.59,.51),.31)
    n=m.node_tree.nodes;l=m.node_tree.links;bs=n.get('Principled BSDF')
    coord=n.new('ShaderNodeTexCoord');noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=180
    l.new(coord.outputs['Object'],noise.inputs['Vector'])
    ramp=n.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].color=(.40,.37,.31,1)
    ramp.color_ramp.elements[1].color=(.68,.64,.56,1)
    l.new(noise.outputs['Fac'],ramp.inputs[0]);l.new(ramp.outputs[0],bs.inputs['Base Color'])
    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.14;bump.inputs['Distance'].default_value=.00018
    l.new(noise.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs[0],bs.inputs['Normal'])
    return m


def wood(bpy):
    m=material(bpy,'Natural oak - elongated end grain',(.28,.15,.07),.44)
    n=m.node_tree.nodes;l=m.node_tree.links;bs=n.get('Principled BSDF')
    coord=n.new('ShaderNodeTexCoord');mapping=n.new('ShaderNodeVectorMath');mapping.operation='MULTIPLY'
    mapping.inputs[1].default_value=(5,5,.15);l.new(coord.outputs['Object'],mapping.inputs[0])
    noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=12;noise.inputs['Detail'].default_value=3
    l.new(mapping.outputs[0],noise.inputs['Vector']);ramp=n.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].color=(.12,.065,.026,1);ramp.color_ramp.elements[1].color=(.37,.24,.12,1)
    l.new(noise.outputs['Fac'],ramp.inputs[0]);l.new(ramp.outputs[0],bs.inputs['Base Color'])
    return m


def cube(bpy,name,location,dimensions,mat,bevel=.004):
    bpy.ops.mesh.primitive_cube_add(size=1,location=location);o=bpy.context.object;o.name=name;o.dimensions=dimensions
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);o.data.materials.append(mat)
    if bevel:
        mod=o.modifiers.new('Soft manufactured edges','BEVEL');mod.width=bevel;mod.segments=3
        o.modifiers.new('Corner normals','WEIGHTED_NORMAL')
    return o


def lathe(bpy,name,profile,mat,segments=160):
    verts=[(r*math.cos(i*2*math.pi/segments),r*math.sin(i*2*math.pi/segments),z) for r,z in profile for i in range(segments)]
    faces=[]
    for j in range(len(profile)-1):
        for i in range(segments):
            a=j*segments+i;b=j*segments+(i+1)%segments
            faces.append((a,b,b+segments,a+segments))
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,[],faces);mesh.update()
    o=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(o);o.data.materials.append(mat)
    for p in mesh.polygons:p.use_smooth=True
    return o


def make_dishes(bpy):
    blue=ceramic(bpy,'A - muted celadon blue glazed stoneware',(.065,.22,.245))
    cream=ceramic(bpy,'B - warm ivory glazed stoneware',(.70,.63,.48))
    foot=material(bpy,'Unglazed ceramic foot ring',(.39,.29,.18),.78)
    objects={}
    for key,name,mat in [('bowl_a','Celadon shallow bowl A',blue),('bowl_b','Ivory shallow bowl B',cream)]:
        o=lathe(bpy,name,[(r,z-COM_HEIGHT) for r,z in PROFILE],mat)
        o.data.materials.append(foot)
        for p in o.data.polygons:
            if p.center.z < .003-COM_HEIGHT:p.material_index=1
        objects[key]=o
    return objects


def import_kitchen(bpy):
    from mathutils import Matrix,Vector
    path=MODELS/'modern_kitchen.glb'
    if not path.is_file():raise FileNotFoundError(f'Missing local asset: {path}')
    previous=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str(path))
    imported=[o for o in bpy.data.objects if o not in previous]
    for o in imported:
        o.animation_data_clear()
        if o.type in {'CAMERA','LIGHT'}:bpy.data.objects.remove(o,do_unlink=True)
    # Native model is double scale. Rotate its long island into the physics X axis.
    transform=Matrix.Translation(Vector((-.65,0,0)))@Matrix.Rotation(math.pi/2,4,'Z')@Matrix.Scale(.5,4)
    for o in imported:
        if o.name in bpy.data.objects and o.parent is None:o.matrix_world=transform@o.matrix_world
    bpy.context.view_layer.update()
    quartz=stone(bpy);oak=wood(bpy)
    cabinet=material(bpy,'Warm greige satin cabinet enamel',(.39,.38,.33),.42)
    wall=material(bpy,'Warm chalk plaster',(.67,.65,.58),.83)
    floor=material(bpy,'Warm grey limestone floor',(.30,.29,.26),.64)
    for o in imported:
        if o.name not in bpy.data.objects or o.type!='MESH':continue
        name=o.name.lower()
        for m in o.data.materials:
            if not m or not m.use_nodes:continue
            for node in m.node_tree.nodes:
                if node.type=='BSDF_PRINCIPLED':
                    if node.inputs.get('Emission Strength'):node.inputs['Emission Strength'].default_value=0
                    rough=node.inputs.get('Roughness')
                    if rough and not rough.is_linked:rough.default_value=max(.28,rough.default_value)
        override=None
        if name.startswith('counters_'):override=quartz
        elif name.startswith('cupboards_'):override=cabinet
        elif name.startswith('stools_'):override=oak
        elif name.startswith('floor_'):override=floor
        elif name.startswith(('structure_','ceiling_','windowwall_')):override=wall
        if override:o.data.materials.clear();o.data.materials.append(override)
        if name.startswith(('counters_','cupboards_','trim_')):
            # Mesh scale is 0.005 in this GLB; use world-space dimensions by baking the mesh transform.
            o.data=o.data.copy();o.data.transform(o.matrix_world);o.parent=None;o.matrix_world=Matrix.Identity(4)
            bevel=o.modifiers.new('Small cabinet edge highlights','BEVEL');bevel.width=.0015;bevel.segments=3
            o.modifiers.new('Cabinet normals','WEIGHTED_NORMAL')
    return oak


def imported_bowl_stack(bpy):
    from mathutils import Vector,Matrix
    path=MODELS/'bowl_and_chops.glb'
    if not path.is_file():raise FileNotFoundError(f'Missing local asset: {path}')
    previous=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str(path))
    imported=[o for o in bpy.data.objects if o not in previous]
    meshes=[o for o in imported if o.type=='MESH']
    points=[o.matrix_world@Vector(c) for o in meshes for c in o.bound_box]
    lo=Vector([min(p[i] for p in points) for i in range(3)])
    hi=Vector([max(p[i] for p in points) for i in range(3)])
    center=Vector(((lo.x+hi.x)/2,(lo.y+hi.y)/2,lo.z));scale=.20/max(hi.x-lo.x,hi.y-lo.y)
    target=Vector((-1.14,.27,COUNTER_Z+.001))
    for o in meshes:
        mat=o.matrix_world.copy();o.parent=None;o.matrix_world=Matrix.Translation(target)@Matrix.Scale(scale,4)@Matrix.Translation(-center)@mat
        for poly in o.data.polygons:poly.use_smooth=True
    for o in imported:
        if o.type!='MESH':bpy.data.objects.remove(o,do_unlink=True)


def build_environment(bpy,scene):
    from mathutils import Vector
    oak=import_kitchen(bpy);imported_bowl_stack(bpy)
    # Back of the island is outside every dynamic bowl's swept area.
    cube(bpy,'Oak chopping board',(1.03,.32,COUNTER_Z+.009),(.40,.26,.018),oak,.012)
    linen=material(bpy,'Woven flax dish towel',(.41,.46,.42),.95)
    n=32
    verts=[(.64+(i/n-.5)*.25,.34+(j/n-.5)*.19,
            COUNTER_Z+.002+.003*(1+math.sin(i/n*math.pi*8))*(.35+.65*j/n)) for j in range(n+1) for i in range(n+1)]
    faces=[(j*(n+1)+i,j*(n+1)+i+1,(j+1)*(n+1)+i+1,(j+1)*(n+1)+i) for j in range(n) for i in range(n)]
    mesh=bpy.data.meshes.new('Linen gentle folds');mesh.from_pydata(verts,[],faces);mesh.update()
    towel=bpy.data.objects.new('Folded linen towel',mesh);scene.collection.objects.link(towel);mesh.materials.append(linen)
    for p in mesh.polygons:p.use_smooth=True
    solid=towel.modifiers.new('Cloth thickness','SOLIDIFY');solid.thickness=.001
    nodes=linen.node_tree.nodes;links=linen.node_tree.links;bs=nodes.get('Principled BSDF')
    tex=nodes.new('ShaderNodeTexNoise');tex.inputs['Scale'].default_value=1400
    bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.22;bump.inputs['Distance'].default_value=.00015
    links.new(tex.outputs['Fac'],bump.inputs['Height']);links.new(bump.outputs[0],bs.inputs['Normal'])
    white=ceramic(bpy,'White porcelain utensil crock',(.65,.63,.54))
    pot=lathe(bpy,'Porcelain utensil holder',[(0,0),(.054,0),(.056,.004),(.058,.14),(.055,.145),(.05,.14),(.048,.01),(0,.01)],white)
    pot.location=(2.25,2.99,COUNTER_Z)
    # A wooden spoon and spatula in the background crock.
    for i in range(3):
        stick=cube(bpy,'Wooden kitchen utensil '+str(i),(2.23+i*.024,2.99,COUNTER_Z+.20),(.013,.008,.25),oak,.003)
        stick.rotation_euler.y=(i-1)*.16
    world=bpy.data.worlds.new('Soft daylight');world.use_nodes=True
    world.node_tree.nodes.get('Background').inputs['Color'].default_value=(.66,.76,.85,1)
    world.node_tree.nodes.get('Background').inputs['Strength'].default_value=.24;scene.world=world
    def area(name,location,target,power,size,color):
        data=bpy.data.lights.new(name,'AREA');data.energy=power;data.shape='DISK';data.size=size;data.color=color
        obj=bpy.data.objects.new(name,data);scene.collection.objects.link(obj);obj.location=location
        obj.rotation_euler=(Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler()
    area('Large soft window daylight',(-2.0,-.9,3.4),(0,0,.9),210,2.2,(.85,.92,1.))
    area('Warm kitchen bounce',(1.0,2.0,2.7),(0,0,1),160,2.,(1.,.82,.64))
    area('Front ceramic edge reflection',(.3,-2.3,2.6),(0,0,1),75,1.7,(1.,.94,.85))
    sun=bpy.data.lights.new('Afternoon sun','SUN');sun.energy=1.1;sun.angle=math.radians(8)
    obj=bpy.data.objects.new('Afternoon sun',sun);scene.collection.objects.link(obj);obj.rotation_euler=(.45,-.55,-.45)

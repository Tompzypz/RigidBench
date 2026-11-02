"""Courtyard environment and physically based ground shading.

The ground is the simulation mesh itself: nothing here moves a vertex. Real
material response (albedo, roughness, normal, ambient occlusion) comes from CC0
Poly Haven texture sets, which supply exactly the sub-centimetre relief the 5 cm
collision grid cannot carry. When a texture set is missing the material degrades
to the earlier procedural look instead of failing.

Three physics-neutral cues make the undulation read:
  1. a low raking sun, so every crest throws a shadow into the trough beside it,
  2. baked cavity/slope tint from the height field itself (dust settles in
     hollows, crests are scuffed bare),
  3. normal and displacement maps at sub-mesh scale.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
from pathlib import Path
import json,math,random

HERE=_PCVE_ROOT/'assets'/'polyhaven'/'uneven_ground_ball'
# Same location and naming as the other scenes in /scripts: <asset>_<channel>_<res>.jpg
ASSETS=HERE
PATH_TEXTURE='floor_pebbles_01'
GRASS_TEXTURE='grass_ground'
RESOLUTION='2k'
CHANNELS=('diff','disp','nor_gl','rough','ao')

def material(bpy,name,color,metal=0,roughness=.5):
    mat=bpy.data.materials.new(name);mat.diffuse_color=(*color,1);mat.use_nodes=True
    shader=mat.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value=(*color,1);shader.inputs['Metallic'].default_value=metal;shader.inputs['Roughness'].default_value=roughness
    return mat

def wood(bpy,name,light=(.40,.24,.115),dark=(.20,.095,.038)):
    mat=material(bpy,name,light,roughness=.48);nodes=mat.node_tree.nodes;links=mat.node_tree.links
    coords=nodes.new('ShaderNodeTexCoord');scale=nodes.new('ShaderNodeVectorMath');scale.operation='MULTIPLY';scale.inputs[1].default_value=(2,95,5)
    links.new(coords.outputs['Generated'],scale.inputs[0]);noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=2.5;noise.inputs['Detail'].default_value=3
    links.new(scale.outputs[0],noise.inputs['Vector']);ramp=nodes.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].color=(*dark,1);ramp.color_ramp.elements[1].color=(*light,1)
    links.new(noise.outputs['Fac'],ramp.inputs[0]);shader=nodes.get('Principled BSDF');links.new(ramp.outputs['Color'],shader.inputs['Base Color'])
    bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.16;bump.inputs['Distance'].default_value=.0007
    links.new(noise.outputs['Fac'],bump.inputs['Height']);links.new(bump.outputs[0],shader.inputs['Normal']);return mat

def box(bpy,name,location,size,mat,pitch=0,bevel=0):
    bpy.ops.mesh.primitive_cube_add(size=1,location=location);obj=bpy.context.object;obj.name=name;obj.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);obj.rotation_euler[1]=pitch;obj.data.materials.append(mat)
    if bevel:
        mod=obj.modifiers.new('Manufactured edge','BEVEL');mod.width=bevel;mod.segments=3;obj.modifiers.new('Weighted normals','WEIGHTED_NORMAL')
    return obj

def load_texture_set(bpy,asset,resolution=RESOLUTION):
    """Return {channel: bpy.types.Image} for a fetched Poly Haven set, or {}."""
    images={}
    for channel in CHANNELS:
        path=ASSETS/f'{asset}_{channel}_{resolution}.jpg'
        if not path.exists():continue
        image=bpy.data.images.load(str(path),check_existing=True)
        image.colorspace_settings.name='sRGB' if channel=='diff' else 'Non-Color'
        images[channel]=image
    return images

def _mix(nodes,links,factor,first,second,blend='MIX'):
    """MixRGB that accepts either a socket, an RGB tuple, or a numeric factor."""
    node=nodes.new('ShaderNodeMixRGB');node.blend_type=blend
    if isinstance(factor,(int,float)):node.inputs[0].default_value=factor
    else:links.new(factor,node.inputs[0])
    for source,index in ((first,1),(second,2)):
        if isinstance(source,tuple):
            node.inputs[index].default_value=tuple(source)+(1.,)*(4-len(source)) if len(source)<4 else source
        else:links.new(source,node.inputs[index])
    return node.outputs['Color']

def _samplers(nodes,links,uv,images,metres_per_tile,label):
    """One mapping per texture set; every channel shares it so tiling is exact."""
    mapping=nodes.new('ShaderNodeMapping');mapping.vector_type='POINT'
    mapping.inputs['Scale'].default_value=(1/metres_per_tile,)*3
    links.new(uv,mapping.inputs['Vector'])
    out={}
    for channel,image in images.items():
        sampler=nodes.new('ShaderNodeTexImage');sampler.image=image
        sampler.label=f'{label} {channel} ({metres_per_tile:g} m per tile)'
        links.new(mapping.outputs['Vector'],sampler.inputs['Vector'])
        out[channel]=sampler.outputs['Color']
    return out

def ground_material(bpy,c,guide='none',path_asset=PATH_TEXTURE,grass_asset=GRASS_TEXTURE,
                    path_half_width=1.90,edge_width=.34,vertex_tint='terrain_shading'):
    path=load_texture_set(bpy,path_asset);grass=load_texture_set(bpy,grass_asset)
    mat=material(bpy,'Weathered courtyard path',(.36,.30,.22),roughness=.85)
    nodes,links=mat.node_tree.nodes,mat.node_tree.links;shader=nodes.get('Principled BSDF')
    uv=nodes.new('ShaderNodeTexCoord').outputs['UV']
    separate=nodes.new('ShaderNodeSeparateXYZ');links.new(uv,separate.inputs[0])
    path_sources=_samplers(nodes,links,uv,path,.62,'path') if path else {}
    grass_sources=_samplers(nodes,links,uv,grass,.42,'lawn') if grass else {}

    # --- worn path / lawn boundary, broken up so the edge is never a straight line
    boundary=nodes.new('ShaderNodeTexNoise');boundary.inputs['Scale'].default_value=2.6;boundary.inputs['Detail'].default_value=5
    links.new(uv,boundary.inputs['Vector'])
    wobble=nodes.new('ShaderNodeMath');wobble.operation='MULTIPLY';wobble.inputs[1].default_value=.42
    links.new(boundary.outputs['Fac'],wobble.inputs[0])
    absolute_y=nodes.new('ShaderNodeMath');absolute_y.operation='ABSOLUTE';links.new(separate.outputs['Y'],absolute_y.inputs[0])
    shifted=nodes.new('ShaderNodeMath');shifted.operation='ADD'
    links.new(absolute_y.outputs[0],shifted.inputs[0]);links.new(wobble.outputs[0],shifted.inputs[1])
    is_lawn=nodes.new('ShaderNodeMapRange');is_lawn.interpolation_type='SMOOTHSTEP'
    is_lawn.inputs['From Min'].default_value=path_half_width;is_lawn.inputs['From Max'].default_value=path_half_width+edge_width
    links.new(shifted.outputs[0],is_lawn.inputs['Value'])
    lawn=is_lawn.outputs['Result']

    if path_sources:
        # Damp/dry patches: one much coarser noise multiply kills the obvious repeat.
        macro=nodes.new('ShaderNodeTexNoise');macro.inputs['Scale'].default_value=.38;macro.inputs['Detail'].default_value=4
        stretch=nodes.new('ShaderNodeVectorMath');stretch.operation='MULTIPLY';stretch.inputs[1].default_value=(1.6,.85,1.)
        links.new(uv,stretch.inputs[0]);links.new(stretch.outputs[0],macro.inputs['Vector'])
        macro_ramp=nodes.new('ShaderNodeValToRGB')
        macro_ramp.color_ramp.elements[0].position=.32;macro_ramp.color_ramp.elements[0].color=(.74,.68,.60,1)
        macro_ramp.color_ramp.elements[1].position=.70;macro_ramp.color_ramp.elements[1].color=(1.08,1.04,.97,1)
        links.new(macro.outputs['Fac'],macro_ramp.inputs[0])
        path_colour=_mix(nodes,links,1.,path_sources['diff'],macro_ramp.outputs['Color'],'MULTIPLY')
        path_rough=path_sources.get('rough',(.72,.72,.72))
        path_height=path_sources.get('disp',(.5,.5,.5))
        path_normal=path_sources.get('nor_gl',(.5,.5,1.))
    else:
        noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=5.;noise.inputs['Detail'].default_value=3
        links.new(uv,noise.inputs['Vector'])
        path_colour=_mix(nodes,links,noise.outputs['Fac'],(.175,.145,.105,1),(.31,.255,.185,1))
        path_rough=path_height=path_normal=(.5,.5,.5);path_normal=(.5,.5,1.)

    if grass_sources:
        # The scanned lawn is dark olive; push it towards living turf so the path
        # edge reads as earth-versus-grass instead of two similar browns.
        grass_colour=_mix(nodes,links,1.,grass_sources['diff'],(1.0,1.16,.80),'MULTIPLY')
        grass_rough=grass_sources.get('rough',(.80,.80,.80))
        grass_height=grass_sources.get('disp',(.5,.5,.5))
        grass_normal=grass_sources.get('nor_gl',(.5,.5,1.))
    else:
        noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=9.;noise.inputs['Detail'].default_value=6
        links.new(uv,noise.inputs['Vector'])
        grass_colour=_mix(nodes,links,noise.outputs['Fac'],(.045,.085,.028,1),(.135,.195,.055,1))
        grass_rough=(.86,.86,.86);grass_height=(.5,.5,.5);grass_normal=(.5,.5,1.)

    albedo=_mix(nodes,links,lawn,path_colour,grass_colour)
    if path_sources.get('ao') or grass_sources.get('ao'):
        occlusion=_mix(nodes,links,lawn,path_sources.get('ao',(1.,1.,1.)),grass_sources.get('ao',(1.,1.,1.)))
        albedo=_mix(nodes,links,.75,albedo,occlusion,'MULTIPLY')
    if vertex_tint:
        tint=nodes.new('ShaderNodeVertexColor');tint.layer_name=vertex_tint
        albedo=_mix(nodes,links,1.,albedo,tint.outputs['Color'],'MULTIPLY')
    links.new(albedo,shader.inputs['Base Color'])

    span=nodes.new('ShaderNodeMapRange');span.inputs['To Min'].default_value=.58;span.inputs['To Max'].default_value=.97
    links.new(_mix(nodes,links,lawn,path_rough,grass_rough),span.inputs['Value'])
    links.new(span.outputs['Result'],shader.inputs['Roughness'])

    # --- micro relief: mixed tangent-space normals, then the height map ------
    normal_map=nodes.new('ShaderNodeNormalMap');normal_map.inputs['Strength'].default_value=.9;normal_map.space='TANGENT'
    normal_map.uv_map='World metres'
    links.new(_mix(nodes,links,lawn,path_normal,grass_normal),normal_map.inputs['Color'])
    bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.95;bump.inputs['Distance'].default_value=.02
    links.new(_mix(nodes,links,lawn,path_height,grass_height),bump.inputs['Height'])
    links.new(normal_map.outputs['Normal'],bump.inputs['Normal'])
    links.new(bump.outputs['Normal'],shader.inputs['Normal'])

    if guide=='contours':
        position=nodes.new('ShaderNodeNewGeometry');xyz=nodes.new('ShaderNodeSeparateXYZ');links.new(position.outputs['Position'],xyz.inputs[0])
        grade=nodes.new('ShaderNodeMath');grade.operation='MULTIPLY';grade.inputs[1].default_value=c['terrain_slope'];links.new(xyz.outputs['X'],grade.inputs[0])
        subtract=nodes.new('ShaderNodeMath');subtract.operation='SUBTRACT';links.new(xyz.outputs['Z'],subtract.inputs[0]);links.new(grade.outputs[0],subtract.inputs[1])
        baseline=nodes.new('ShaderNodeMath');baseline.operation='SUBTRACT';baseline.inputs[1].default_value=c['terrain_base_height'];links.new(subtract.outputs[0],baseline.inputs[0])
        scale=nodes.new('ShaderNodeMath');scale.operation='MULTIPLY';scale.inputs[1].default_value=50.;links.new(baseline.outputs[0],scale.inputs[0])
        repeat=nodes.new('ShaderNodeMath');repeat.operation='PINGPONG';repeat.inputs[1].default_value=.5;links.new(scale.outputs[0],repeat.inputs[0])
        threshold=nodes.new('ShaderNodeMath');threshold.operation='LESS_THAN';threshold.inputs[1].default_value=.016;links.new(repeat.outputs[0],threshold.inputs[0])
        overlay=nodes.new('ShaderNodeMixRGB');overlay.blend_type='MIX'
        links.new(albedo,overlay.inputs[1]);overlay.inputs[2].default_value=(.03,.09,.10,1)
        links.new(threshold.outputs[0],overlay.inputs[0])
        links.new(overlay.outputs['Color'],shader.inputs['Base Color'])
    return mat

def bake_terrain_shading(mesh,vertices,c):
    """Bake cavity and slope into a colour attribute: shading data, not geometry.

    Hollows collect damp fine material and read darker; exposed crests are
    scuffed lighter. The tint is derived from the same height field the ball
    collides with, so it cannot contradict the motion.
    """
    import numpy as np
    from terrain_geometry import curvature
    x=vertices[:,0];y=vertices[:,1]
    lap=curvature(x,y,c)
    # Positive Laplacian = hollow (surface curves up around the point).
    cavity=np.clip(lap/6.,-1.,1.)
    brightness=1.-.34*cavity
    warm=np.clip(-cavity,0.,1.)
    tint=np.stack((brightness+.05*warm,brightness,brightness-.06*warm),axis=1)
    tint=np.clip(tint,0.,2.2)
    attribute=mesh.color_attributes.new(name='terrain_shading',type='FLOAT_COLOR',domain='POINT')
    rgba=np.concatenate((tint,np.ones((len(tint),1))),axis=1)
    attribute.data.foreach_set('color',rgba.astype(np.float32).ravel())
    return tint

def ball_material(bpy):
    mat=material(bpy,'Orange and ivory rubber ball',(.74,.20,.035),roughness=.55)
    nodes,links=mat.node_tree.nodes,mat.node_tree.links;shader=nodes.get('Principled BSDF')
    coord=nodes.new('ShaderNodeTexCoord');sep=nodes.new('ShaderNodeSeparateXYZ');links.new(coord.outputs['Generated'],sep.inputs[0])
    centred=[]
    for axis in ('X','Y'):
        node=nodes.new('ShaderNodeMath');node.operation='SUBTRACT';node.inputs[1].default_value=.5;links.new(sep.outputs[axis],node.inputs[0]);centred.append(node)
    angle=nodes.new('ShaderNodeMath');angle.operation='ARCTAN2';links.new(centred[1].outputs[0],angle.inputs[0]);links.new(centred[0].outputs[0],angle.inputs[1])
    freq=nodes.new('ShaderNodeMath');freq.operation='MULTIPLY';freq.inputs[1].default_value=2;links.new(angle.outputs[0],freq.inputs[0])
    wave=nodes.new('ShaderNodeMath');wave.operation='SINE';links.new(freq.outputs[0],wave.inputs[0]);split=nodes.new('ShaderNodeMath');split.operation='GREATER_THAN';links.new(wave.outputs[0],split.inputs[0])
    mix=nodes.new('ShaderNodeMixRGB');mix.inputs[1].default_value=(.72,.16,.025,1);mix.inputs[2].default_value=(.87,.82,.66,1);links.new(split.outputs[0],mix.inputs[0]);links.new(mix.outputs[0],shader.inputs['Base Color'])
    for name,value in (('Coat Weight',.25),('Coat Roughness',.28)):
        if name in shader.inputs:shader.inputs[name].default_value=value
    noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=220.;links.new(coord.outputs['Generated'],noise.inputs['Vector'])
    bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.14;bump.inputs['Distance'].default_value=.00018;links.new(noise.outputs['Fac'],bump.inputs['Height']);links.new(bump.outputs[0],shader.inputs['Normal'])
    return mat

def build_environment(bpy,c,path_half_width=1.90):
    from terrain_geometry import environment_boxes,height
    timber=wood(bpy,'Oiled garden timber',(.31,.16,.065),(.095,.040,.016));pot=material(bpy,'Terracotta planter',(.43,.20,.095),roughness=.9)
    for part in environment_boxes(c):box(bpy,part['name'],part['location'],part['size'],pot if part['kind']=='pot' else timber,bevel=.005)
    soil=material(bpy,'Planter soil',(.08,.055,.025),roughness=1);leaves=material(bpy,'Garden herbs',(.10,.26,.075),roughness=.9)
    for x in (-1.9,2.9):
        z=float(height(x,2.55,c));box(bpy,'Soil in planter',[x,2.55,z+.322],[.34,.32,.012],soil)
        for i in range(7):
            angle=2*math.pi*i/7
            bpy.ops.mesh.primitive_uv_sphere_add(segments=12,ring_count=8,radius=1,location=[x+.10*math.cos(angle),2.55+.08*math.sin(angle),z+.40+.04*(i%2)])
            leaf=bpy.context.object;leaf.name='Herb cluster';leaf.scale=(.09,.07,.14);leaf.data.materials.append(leaves)
            for face in leaf.data.polygons:face.use_smooth=True
    # Fine grass blades are decorative vegetation, kept clear of the rolling path.
    rng=random.Random(418);vertices=[];faces=[]
    for _ in range(2600):
        x=rng.uniform(-3.4,6.6);y=rng.choice((-1,1))*rng.uniform(path_half_width+.22,3.05);z=float(height(x,y,c))
        angle=rng.uniform(0,2*math.pi);width=rng.uniform(.003,.006);length=rng.uniform(.014,.040)
        dx=width*math.cos(angle);dy=width*math.sin(angle);start=len(vertices)
        vertices.extend([(x-dx,y-dy,z),(x+dx,y+dy,z),(x+.006*math.cos(angle+.7),y+.006*math.sin(angle+.7),z+length)])
        faces.append((start,start+1,start+2))
    mesh=bpy.data.meshes.new('Garden grass blades');mesh.from_pydata(vertices,[],faces);mesh.update()
    grass=bpy.data.objects.new('Grass around path',mesh);bpy.context.scene.collection.objects.link(grass);grass.data.materials.append(material(bpy,'Grass blades',(.085,.175,.038),roughness=.9))

def stone_material(bpy):
    mat=material(bpy,'Path grit and small stones',(.30,.27,.22),roughness=.82)
    nodes,links=mat.node_tree.nodes,mat.node_tree.links;shader=nodes.get('Principled BSDF')
    coord=nodes.new('ShaderNodeTexCoord');noise=nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value=180.;noise.inputs['Detail'].default_value=8
    links.new(coord.outputs['Object'],noise.inputs['Vector'])
    ramp=nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position=.28;ramp.color_ramp.elements[0].color=(.085,.078,.064,1)
    ramp.color_ramp.elements[1].position=.74;ramp.color_ramp.elements[1].color=(.52,.48,.41,1)
    links.new(noise.outputs['Fac'],ramp.inputs[0])
    tint=nodes.new('ShaderNodeVertexColor');tint.layer_name='stone_tint'
    albedo=_mix(nodes,links,1.,ramp.outputs['Color'],tint.outputs['Color'],'MULTIPLY')
    links.new(albedo,shader.inputs['Base Color'])
    bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.55;bump.inputs['Distance'].default_value=.003
    links.new(noise.outputs['Fac'],bump.inputs['Height']);links.new(bump.outputs[0],shader.inputs['Normal'])
    return mat

def _unit_stone(rings=4,segments=7):
    """Angular, cheap, and irregular once squashed: reads as grit, not a ball."""
    vertices=[(0.,0.,1.)];faces=[]
    for ring in range(1,rings):
        phi=math.pi*ring/rings;radius=math.sin(phi);z=math.cos(phi)
        for segment in range(segments):
            theta=2*math.pi*segment/segments
            vertices.append((radius*math.cos(theta),radius*math.sin(theta),z))
    vertices.append((0.,0.,-1.));south=len(vertices)-1
    for segment in range(segments):
        faces.append((0,1+segment,1+(segment+1)%segments))
    for ring in range(rings-2):
        for segment in range(segments):
            a=1+ring*segments+segment;b=1+ring*segments+(segment+1)%segments
            faces.extend([(a,b,b+segments),(a,b+segments,a+segments)])
    base=1+(rings-2)*segments
    for segment in range(segments):
        faces.append((south,base+(segment+1)%segments,base+segment))
    return vertices,faces

def scatter_gravel(bpy,c,frames,path_half_width=1.90,count=520,seed=517):
    """Loose grit and small stones lying on the path.

    Decorative only: every stone is rejected if it lands inside the corridor the
    ball sweeps, so the visible surface never contradicts the simulated contact
    geometry. Placement is seeded, so a rerun reproduces the same stones.
    """
    from terrain_geometry import height
    rng=random.Random(seed)
    template,template_faces=_unit_stone()
    trajectory=[(frame['ball']['location'][0],frame['ball']['location'][1]) for frame in frames]
    clearance=c['ball_radius']+.09
    vertices=[];faces=[];tints=[];placed=0
    for _ in range(count*4):
        if placed>=count:break
        x=rng.uniform(-3.6,3.1);y=rng.uniform(-2.1,2.1)
        if min(math.hypot(x-tx,y-ty) for tx,ty in trajectory)<clearance:continue
        z=float(height(x,y,c))
        roll=rng.random()
        size=rng.uniform(.009,.026) if roll<.90 else rng.uniform(.030,.058)
        squash=rng.uniform(.40,.60);spin=rng.uniform(0,2*math.pi);tilt=rng.uniform(-.40,.40)
        ca,sa,ct,st=math.cos(spin),math.sin(spin),math.cos(tilt),math.sin(tilt)
        shade=rng.uniform(.48,1.12);warmth=rng.uniform(.92,1.12)
        tint=(shade*warmth,shade,shade/warmth,1.)
        base_vertices=len(vertices)
        for vx,vy,vz in template:
            # tilt, then spin, then squash, then settle into the ground
            ty,tz=vy*ct-vz*st,vy*st+vz*ct
            fx,fy=vx*ca-ty*sa,vx*sa+ty*ca
            vertices.append((x+fx*size,y+fy*size,z+tz*size*squash-size*squash*.42))
            tints.append(tint)
        for corner in template_faces:
            faces.append(tuple(base_vertices+index for index in corner))
        placed+=1
    mesh=bpy.data.meshes.new('Loose grit');mesh.from_pydata(vertices,[],faces);mesh.update()
    attribute=mesh.color_attributes.new(name='stone_tint',type='FLOAT_COLOR',domain='POINT')
    attribute.data.foreach_set('color',__import__('numpy').asarray(tints,dtype='float32').ravel())
    stones=bpy.data.objects.new('Loose grit on path',mesh);bpy.context.scene.collection.objects.link(stones)
    stones.data.materials.append(stone_material(bpy))
    return placed

def build_lighting(bpy,scene):
    """One low raking sun for relief, plus sky and soft bounce fills.

    A diffuse dome from above renders a rutted path as flat colour; the whole
    point here is that a low sun throws a shadow across every crest.
    """
    sun_target=(.85,-.25,.10);sun_from=(5.00,.05,.95)
    bpy.ops.object.light_add(type='SUN');sun=bpy.context.object;sun.name='Low raking sun'
    sun.data.energy=5.0;sun.data.angle=.018;sun.data.color=(1.,.83,.63);sun.data.use_shadow=True
    if hasattr(sun.data,'shadow_maximum_resolution'):sun.data.shadow_maximum_resolution=.0002
    sun.rotation_euler=_aim(sun_target,sun_from)
    for name,location,power,size,color in [('Sky bounce',[-1.9,-3.2,2.6],13,4.5,(.66,.78,1.)),
                                           ('Warm bounce',[.6,2.6,1.1],6,3.2,(1.,.86,.70))]:
        bpy.ops.object.light_add(type='AREA',location=location);light=bpy.context.object;light.name=name
        light.data.energy=power;light.data.shape='DISK';light.data.size=size;light.data.color=color;light.data.use_shadow=True
        light.rotation_euler=_aim((.7,.4,.12),location)
    return sun

def _aim(target,source):
    from mathutils import Vector
    return (Vector(target)-Vector(source)).to_track_quat('-Z','Y').to_euler()

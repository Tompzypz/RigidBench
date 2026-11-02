"""A daylight split-level sitting room; all geometry is authored at metre scale."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math
from pathlib import Path
import random
import bpy
from mathutils import Vector, Matrix
from runtime_support import MODELS, ASSETS
from scene_geometry import boxes, ROOM_X, ROOM_Y

PLANT_ASSET = 'fiddle_leaf_fig.glb'
PLANT_HEIGHT_M = 1.24
PLANT_POSITION_XY = (3.92, 1.82)
PLANT_ROTATION_DEG = 135.

def material(name,color,roughness=.6,bump=0):
    m=bpy.data.materials.new(name); m.use_nodes=True
    bs=m.node_tree.nodes.get('Principled BSDF')
    bs.inputs['Base Color'].default_value=(*color,1)
    bs.inputs['Roughness'].default_value=roughness
    if bump:
        n=m.node_tree.nodes.new('ShaderNodeTexNoise'); n.inputs['Scale'].default_value=180
        t=m.node_tree.nodes.new('ShaderNodeTexCoord')
        m.node_tree.links.new(t.outputs['Object'],n.inputs['Vector'])
        b=m.node_tree.nodes.new('ShaderNodeBump'); b.inputs['Strength'].default_value=.22
        b.inputs['Distance'].default_value=bump
        m.node_tree.links.new(n.outputs['Fac'],b.inputs['Height'])
        m.node_tree.links.new(b.outputs[0],bs.inputs['Normal'])
    return m

def cube(name,center,size,mat,bevel=0):
    bpy.ops.mesh.primitive_cube_add(size=1,location=center)
    o=bpy.context.object; o.name=name; o.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    o.data.materials.append(mat)
    if bevel:
        mod=o.modifiers.new('Small real edge radius','BEVEL'); mod.width=bevel; mod.segments=3
        o.modifiers.new('Weighted corner normals','WEIGHTED_NORMAL')
    return o

def aim(obj,point):
    obj.rotation_euler=(Vector(point)-obj.location).to_track_quat('-Z','Y').to_euler()

def area(name,pos,target,power,size,color):
    d=bpy.data.lights.new(name,'AREA'); d.energy=power; d.shape='DISK'; d.size=size; d.color=color
    o=bpy.data.objects.new(name,d); bpy.context.collection.objects.link(o); o.location=pos; aim(o,target)

def scanned_surface(name,stem,scale,wood=False):
    m=material(name,(.4,.35,.27),.48)
    n,l=m.node_tree.nodes,m.node_tree.links; bs=n.get('Principled BSDF')
    uv=n.new('ShaderNodeTexCoord'); mapping=n.new('ShaderNodeVectorMath'); mapping.operation='SCALE'
    mapping.inputs['Scale'].default_value=scale
    l.new(uv.outputs['Object'],mapping.inputs[0])
    diff=n.new('ShaderNodeTexImage'); diff.image=bpy.data.images.load(str(ASSETS/f'{stem}_diff_2k.jpg'),check_existing=True)
    l.new(mapping.outputs['Vector'],diff.inputs['Vector']); l.new(diff.outputs['Color'],bs.inputs['Base Color'])
    if wood:
        b=n.new('ShaderNodeBump'); b.inputs['Strength'].default_value=.15; b.inputs['Distance'].default_value=.0015
        l.new(diff.outputs['Color'],b.inputs['Height']); l.new(b.outputs[0],bs.inputs['Normal'])
    else:
        # Concrete source is weathered: lighten it into a sealed residential slab.
        mix=n.new('ShaderNodeMixRGB'); mix.blend_type='MIX'; mix.inputs[0].default_value=.50
        mix.inputs[2].default_value=(.46,.43,.37,1)
        l.new(diff.outputs['Color'],mix.inputs[1]); l.new(mix.outputs[0],bs.inputs['Base Color'])
        rough=n.new('ShaderNodeTexImage'); rough.image=bpy.data.images.load(str(ASSETS/f'{stem}_rough_2k.jpg'),check_existing=True)
        rough.image.colorspace_settings.name='Non-Color'
        l.new(mapping.outputs[0],rough.inputs['Vector'])
        remap=n.new('ShaderNodeMapRange'); remap.inputs['To Min'].default_value=.38; remap.inputs['To Max'].default_value=.65
        l.new(rough.outputs['Color'],remap.inputs['Value']); l.new(remap.outputs[0],bs.inputs['Roughness'])
        norm=n.new('ShaderNodeTexImage'); norm.image=bpy.data.images.load(str(ASSETS/f'{stem}_nor_gl_2k.jpg'),check_existing=True)
        norm.image.colorspace_settings.name='Non-Color'; l.new(mapping.outputs[0],norm.inputs['Vector'])
        normal=n.new('ShaderNodeNormalMap'); normal.inputs['Strength'].default_value=.18
        l.new(norm.outputs['Color'],normal.inputs['Color']); l.new(normal.outputs[0],bs.inputs['Normal'])
    return m

def import_mesh(path,name):
    """Evaluate GLB hierarchy/skin and bake once before rescaling in world units."""
    before=set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath=str(path))
    imported=set(bpy.data.objects)-before
    bpy.context.view_layer.update(); deps=bpy.context.evaluated_depsgraph_get(); result=[]
    for o in imported:
        if o.type!='MESH': continue
        mesh=bpy.data.meshes.new_from_object(o.evaluated_get(deps),depsgraph=deps)
        mesh.transform(o.matrix_world)
        obj=bpy.data.objects.new(name,mesh); bpy.context.collection.objects.link(obj); result.append(obj)
    for o in imported: bpy.data.objects.remove(o,do_unlink=True)
    bpy.ops.object.select_all(action='DESELECT')
    for o in result: o.select_set(True)
    bpy.context.view_layer.objects.active=result[0]
    if len(result)>1: bpy.ops.object.join()
    return bpy.context.object

def make_ball(filename,key,radius):
    o=import_mesh(MODELS/filename,key)
    lo=Vector(tuple(min(v.co[i] for v in o.data.vertices) for i in range(3)))
    hi=Vector(tuple(max(v.co[i] for v in o.data.vertices) for i in range(3)))
    c=(lo+hi)/2
    outer=max((v.co-c).length for v in o.data.vertices)
    for v in o.data.vertices: v.co=(v.co-c)*(radius/outer)
    o.data.update(); o.name=key
    for f in o.data.polygons: f.use_smooth=True
    for m in o.data.materials:
        if not m or not m.use_nodes: continue
        for n in m.node_tree.nodes:
            if n.type!='BSDF_PRINCIPLED': continue
            for field,value in [('Metallic',0.),('Roughness',.57 if key=='soccer' else .72),('Emission Strength',0.)]:
                for link in list(n.inputs[field].links): m.node_tree.links.remove(link)
                n.inputs[field].default_value=value
    # Fixed mesh-space orientation, independent of physical centre and quaternion.
    o.data.transform(Matrix.Rotation(.36 if key=='soccer' else .55,4,'X') @ Matrix.Rotation(.38,4,'Z'))
    return o

def build_room(s):
    h=s['physics']['step_height']
    plaster=material('Warm mineral plaster',(.62,.58,.49),.86,.0008)
    cream=material('Ivory painted joinery',(.76,.74,.66),.44,.0002)
    dark=material('Anodized bronze frames',(.065,.055,.042),.33)
    oak=material('Oiled oak end grain',(.28,.15,.068),.50,.0007)
    linen=material('Natural flax upholstery',(.50,.44,.34),.88,.0012)
    concrete=scanned_surface('Sealed warm concrete','concrete_floor',.45)
    wood=scanned_surface('Photographic worn oak floor','wood_floor_worn',.50,True)
    for name,center,size in boxes(h):
        if name=='back_wall': continue
        cube(name,center,size,concrete if name=='floor' else wood if name=='platform' else plaster,
             .0006 if name=='platform' else 0)
    # Window opening in a continuous plaster wall; the actual daylight enters here.
    y=ROOM_Y[1]+.1; xmin,xmax=ROOM_X; wl,wr=-1.75,.45; wb,wt=.82,2.72
    for name,center,size in [
        ('Back wall left',((xmin+wl)/2,y,1.6),(wl-xmin,.2,3.2)),
        ('Back wall right',((wr+xmax)/2,y,1.6),(xmax-wr,.2,3.2)),
        ('Under window',((wl+wr)/2,y,wb/2),(wr-wl,.2,wb)),
        ('Above window',((wl+wr)/2,y,(wt+3.2)/2),(wr-wl,.2,3.2-wt))]: cube(name,center,size,plaster)
    for x in (wl,wr,(wl+wr)/2): cube('Window vertical frame',(x,2.83,(wb+wt)/2),(.045,.08,wt-wb),dark,.002)
    for z in (wb,wt,1.8): cube('Window horizontal frame',((wl+wr)/2,2.83,z),(wr-wl,.08,.042),dark,.002)
    cube('Deep stone window sill',((wl+wr)/2,2.74,wb), (wr-wl+.1,.30,.05),cream,.006)
    # Outdoor colour and a distant hedge give depth through the real opening.
    sky=material('Overcast garden beyond window',(.62,.73,.80),1)
    cube('Garden sky',(-.65,5.8,2.7),(6,.05,5.4),sky)
    hedge=material('Soft garden green',(.12,.20,.075),.9,.02)
    hn,hl=hedge.node_tree.nodes,hedge.node_tree.links
    noise=hn.new('ShaderNodeTexNoise'); noise.inputs['Scale'].default_value=15
    ramp=hn.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].color=(.025,.055,.012,1)
    ramp.color_ramp.elements[1].color=(.19,.29,.085,1)
    hl.new(noise.outputs['Fac'],ramp.inputs[0]); hl.new(ramp.outputs[0],hn.get('Principled BSDF').inputs['Base Color'])
    rng=random.Random(92)
    for i in range(17):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12,ring_count=8,radius=rng.uniform(.3,.6),location=(-3+i*.3,5.2,rng.uniform(.25,.65)))
        bpy.context.object.name='Distant garden foliage'; bpy.context.object.data.materials.append(hedge)
        for f in bpy.context.object.data.polygons: f.use_smooth=True
    glass=material('Lightly frosted privacy glazing',(.88,.94,.98),.25)
    gn,gl=glass.node_tree.nodes,glass.node_tree.links
    gbs=gn.get('Principled BSDF'); gbs.inputs['Transmission Weight'].default_value=1
    gbs.inputs['IOR'].default_value=1.45
    # Transmitted daylight is supplied by the exterior area light, without noisy caustics.
    lightpath=gn.new('ShaderNodeLightPath'); transparent=gn.new('ShaderNodeBsdfTransparent')
    mix=gn.new('ShaderNodeMixShader'); gl.new(lightpath.outputs['Is Shadow Ray'],mix.inputs[0])
    gl.new(gbs.outputs[0],mix.inputs[1]); gl.new(transparent.outputs[0],mix.inputs[2])
    gl.new(mix.outputs[0],gn.get('Material Output').inputs['Surface'])
    cube('Privacy window glazing',((wl+wr)/2,2.88,(wb+wt)/2),(wr-wl,.008,wt-wb),glass)
    # Low built-in bench stays well away from the ball lane (y=-0.18).
    for x in (1.30,3.35): cube('Bench leg',(x,2.27,h+.19),(.075,.48,.38),oak,.009)
    cube('Oak bench seat',(2.325,2.27,h+.395),(2.35,.64,.08),oak,.018)
    cube('Flax seat cushion',(2.325,2.24,h+.47),(2.24,.57,.095),linen,.038)
    # Wall artwork: physical frame, mat, paper and raised abstract pigment.
    cube('Oak picture frame',(2.5,2.72,1.72),(.94,.05,1.08),oak,.006)
    cube('Ivory print mount',(2.5,2.686,1.72),(.89,.012,1.03),cream)
    paper=material('Textured cotton art paper',(.64,.57,.43),.94,.0005)
    rust=material('Abstract clay pigment',(.35,.13,.065),.95)
    cube('Artwork paper',(2.5,2.678,1.72),(.68,.006,.81),paper)
    cube('Artwork pigment',(2.43,2.673,1.67),(.27,.002,.49),rust,.06)
    cube('Artwork charcoal accent',(2.69,2.672,1.9),(.10,.002,.20),dark)
    # Floor skirting follows both levels; the curb riser remains fully visible.
    cube('Back skirting lower',(-1.9,2.785,.045),(3.8,.03,.09),cream,.002)
    cube('Back skirting upper',(2.6,2.785,h+.045),(5.2,.03,.09),cream,.002)
    cube('Right skirting',(5.185,-.5,h+.045),(.03,6.6,.09),cream,.002)
    cube('Ceiling',(.7,-.5,3.26),(9.2,6.8,.12),cream)
    # Keep the fig's original leaf/pot proportions with one uniform metre-scale factor.
    plant=import_mesh(MODELS/PLANT_ASSET,'Fiddle Leaf Fig / supplied textured mesh')
    lo=Vector(tuple(min(v.co[j] for v in plant.data.vertices) for j in range(3)))
    hi=Vector(tuple(max(v.co[j] for v in plant.data.vertices) for j in range(3)))
    native_height=hi.z-lo.z
    if native_height<=0: raise ValueError('Fiddle Leaf Fig has zero height')
    # Anchor the pot rather than the asymmetric canopy, and put its bottom on the slab.
    base=[v.co for v in plant.data.vertices if v.co.z <= lo.z+native_height*.12]
    center=Vector(((min(v.x for v in base)+max(v.x for v in base))/2,
                   (min(v.y for v in base)+max(v.y for v in base))/2,lo.z))
    scale=PLANT_HEIGHT_M/native_height
    for v in plant.data.vertices: v.co=(v.co-center)*scale
    plant.data.update()
    plant.location=(*PLANT_POSITION_XY,h)
    plant['source_asset']=str(MODELS/PLANT_ASSET)
    plant['height_m']=PLANT_HEIGHT_M
    plant['uniform_scale_from_source']=scale
    plant.rotation_euler.z=math.radians(PLANT_ROTATION_DEG)
    from plant_styling import integrate_scan,ceramic_planter
    integrate_scan(plant,PLANT_HEIGHT_M)
    ceramic_planter(plant.location,material)
    scene=bpy.context.scene
    scene.world=bpy.data.worlds.new('Daylight interior world'); scene.world.use_nodes=True
    bg=scene.world.node_tree.nodes.get('Background'); bg.inputs['Color'].default_value=(.65,.74,.84,1); bg.inputs['Strength'].default_value=.16
    area('Large window soft daylight',(-.7,3.12,2.05),(.2,-.6,.1),360,1.9,(.84,.91,1.))
    area('Warm interior bounce',(-2.8,-2.0,2.5),(.5,.3,.2),100,3.0,(1.,.86,.69))
    area('Ceiling reflected light',(2.2,.2,3.05),(.5,-.3,0),80,2.5,(1.,.94,.83))
    area('Soft reflected daylight near bench',(2.9,-.2,2.2),(3.92,1.82,.95),35,1.3,(1.,.96,.85))
    # Grazing afternoon light casts the mullion shadows onto the lower floor.
    bpy.ops.object.light_add(type='SUN',location=(-2,4,5))
    sun=bpy.context.object; sun.name='Afternoon sun through rear window'; sun.data.energy=1.6
    sun.data.angle=math.radians(7); sun.data.color=(1.,.89,.72); aim(sun,(.8,-1.4,0))

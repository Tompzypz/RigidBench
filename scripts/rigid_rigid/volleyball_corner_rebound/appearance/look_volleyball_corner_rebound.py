"""Photographic materials and metre-scale architectural room, authored locally."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math
from pathlib import Path
ROOT = _PCVE_ROOT
import bpy
from mathutils import Vector
from scene_config import MODELS
from scene_geometry import (AC_BACK_GAP, AC_CENTER, AC_HEIGHT, AC_WIDTH, CABINET_CENTER,
    CABINET_SIZE, SPARE_BALL_CENTERS, SPARE_BALL_RADIUS, WINDOW_CENTER_Y)

# cafe_wall_pictures.glb stacks three pictures on one shared 0.49 x 0.33 m mesh that
# differ only in texture, so choosing the artwork is a name lookup: wall and frame
# geometry stay put.  Picture 1 is a photo-real window-and-coffee-jar still life, its
# dark frame and busy interior collapsing into a brown smudge at the size the far
# camera gives it; picture 3 is a coffee-bean owl on cream that vanishes against the
# pale wall; picture 2 is a copper mug on a flat blush ground and still reads as a
# picture from across the room.
PICTURE_MESH = 'wall_picture_2'

def material(name, color, roughness=.6, bump=.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Roughness'].default_value = roughness
    if bump:
        coord = nodes.new('ShaderNodeTexCoord')
        noise = nodes.new('ShaderNodeTexNoise')
        noise.inputs['Scale'].default_value = 170
        noise.inputs['Detail'].default_value = 2
        links.new(coord.outputs['Object'], noise.inputs['Vector'])
        node = nodes.new('ShaderNodeBump')
        node.inputs['Strength'].default_value = .22
        node.inputs['Distance'].default_value = bump
        links.new(noise.outputs['Fac'], node.inputs['Height'])
        links.new(node.outputs['Normal'], bsdf.inputs['Normal'])
    return mat

def cube(name, center, size, mat, bevel=0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    if bevel:
        mod = obj.modifiers.new('Soft manufactured edges', 'BEVEL')
        mod.width, mod.segments = bevel, 3
        obj.modifiers.new('Weighted normals', 'WEIGHTED_NORMAL')
    return obj

def aim(obj, point):
    obj.rotation_euler = (Vector(point)-obj.location).to_track_quat('-Z','Y').to_euler()

def area(name, pos, target, power, size, color=(1,.89,.75)):
    data = bpy.data.lights.new(name, 'AREA')
    data.energy, data.shape, data.size, data.color = power, 'DISK', size, color
    # These broad sources approximate bounced daylight, not visible fixtures.
    # The HDR and room geometry provide the actual glass reflections.
    data.specular_factor=0
    obj = bpy.data.objects.new(name,data)
    bpy.context.collection.objects.link(obj)
    obj.location = pos
    obj.visible_glossy=False
    aim(obj,target)
    return obj

def floor_material(path):
    mat = material('Oak boards / scanned worn wood', (.32,.19,.09), .48)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    uv = nodes.new('ShaderNodeTexCoord')
    sep = nodes.new('ShaderNodeSeparateXYZ')
    links.new(uv.outputs['Object'],sep.inputs[0])
    combine = nodes.new('ShaderNodeCombineXYZ')
    for axis in ('X','Y'):
        scale = nodes.new('ShaderNodeMath')
        scale.operation = 'MULTIPLY'
        scale.inputs[1].default_value = .62
        links.new(sep.outputs[axis],scale.inputs[0])
        links.new(scale.outputs[0],combine.inputs[axis])
    image = nodes.new('ShaderNodeTexImage')
    image.image = bpy.data.images.load(str(path), check_existing=True)
    image.extension = 'REPEAT'
    links.new(combine.outputs[0],image.inputs['Vector'])
    links.new(image.outputs['Color'],bsdf.inputs['Base Color'])
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = .18
    bump.inputs['Distance'].default_value = .002
    links.new(image.outputs['Color'],bump.inputs['Height'])
    links.new(bump.outputs['Normal'],bsdf.inputs['Normal'])
    return mat

def terrazzo_material():
    mat=material('Fine warm-grey terrazzo / 1 m slabs',(.25,.265,.26),.49)
    nodes,links=mat.node_tree.nodes,mat.node_tree.links
    bsdf=nodes.get('Principled BSDF')
    coord=nodes.new('ShaderNodeTexCoord')
    chips=nodes.new('ShaderNodeTexVoronoi')
    chips.inputs['Scale'].default_value=35
    chips.distance='EUCLIDEAN'
    links.new(coord.outputs['Object'],chips.inputs['Vector'])
    gate=nodes.new('ShaderNodeMath')
    gate.operation='LESS_THAN'
    gate.inputs[1].default_value=.36
    links.new(chips.outputs['Distance'],gate.inputs[0])
    palette=nodes.new('ShaderNodeValToRGB')
    palette.color_ramp.interpolation='CONSTANT'
    for index,(position,color) in enumerate(((0,(.055,.065,.06,1)),(.35,(.24,.19,.14,1)),(.5,(.43,.45,.43,1)),(.7,(.62,.60,.54,1)))):
        element=palette.color_ramp.elements[index] if index<2 else palette.color_ramp.elements.new(position)
        element.position=position
        element.color=color
    links.new(chips.outputs['Color'],palette.inputs[0])
    mix=nodes.new('ShaderNodeMixRGB')
    mix.inputs[1].default_value=(.25,.265,.26,1)
    links.new(gate.outputs[0],mix.inputs[0])
    links.new(palette.outputs['Color'],mix.inputs[2])
    separate=nodes.new('ShaderNodeSeparateXYZ')
    links.new(coord.outputs['Object'],separate.inputs[0])
    seams=[]
    for axis in ('X','Y'):
        fract=nodes.new('ShaderNodeMath')
        fract.operation='FRACT'
        links.new(separate.outputs[axis],fract.inputs[0])
        seam=nodes.new('ShaderNodeMath')
        seam.operation='LESS_THAN'
        seam.inputs[1].default_value=.003
        links.new(fract.outputs[0],seam.inputs[0])
        seams.append(seam)
    combine=nodes.new('ShaderNodeMath')
    combine.operation='MAXIMUM'
    for index,seam in enumerate(seams):
        links.new(seam.outputs[0],combine.inputs[index])
    grout=nodes.new('ShaderNodeMixRGB')
    links.new(combine.outputs[0],grout.inputs[0])
    links.new(mix.outputs[0],grout.inputs[1])
    grout.inputs[2].default_value=(.11,.12,.11,1)
    links.new(grout.outputs[0],bsdf.inputs['Base Color'])
    grain=nodes.new('ShaderNodeTexNoise')
    grain.inputs['Scale'].default_value=220
    grain.inputs['Detail'].default_value=2
    links.new(coord.outputs['Object'],grain.inputs['Vector'])
    bump=nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value=.13
    bump.inputs['Distance'].default_value=.00022
    links.new(grain.outputs['Fac'],bump.inputs['Height'])
    links.new(bump.outputs['Normal'],bsdf.inputs['Normal'])
    return mat

def porcelain_floor(width, depth):
    """Metre-scale ceramic slabs, with quiet surface variation and real joints."""
    grout=material('Warm grey fine grout',(.24,.23,.21),.82)
    cube('Floor structural base',(width/2,depth/2,-.08),(width,depth,.12),grout)
    finishes=[]
    for index,offset in enumerate((-.012,-.006,0,.006,.012)):
        mat=material(f'Matte limestone porcelain / tone {index}',(.38+offset,.365+offset,.335+offset),.47)
        nodes,links=mat.node_tree.nodes,mat.node_tree.links
        shader=nodes.get('Principled BSDF')
        coord=nodes.new('ShaderNodeTexCoord')
        cloud=nodes.new('ShaderNodeTexNoise')
        cloud.inputs['Scale'].default_value=2.3
        cloud.inputs['Detail'].default_value=2
        cloud.inputs['Roughness'].default_value=.55
        links.new(coord.outputs['Object'],cloud.inputs['Vector'])
        ramp=nodes.new('ShaderNodeValToRGB')
        ramp.color_ramp.elements[0].color=(.36+offset,.345+offset,.316+offset,1)
        ramp.color_ramp.elements[1].color=(.40+offset,.385+offset,.354+offset,1)
        links.new(cloud.outputs['Fac'],ramp.inputs[0])
        links.new(ramp.outputs[0],shader.inputs['Base Color'])
        fine=nodes.new('ShaderNodeTexNoise')
        fine.inputs['Scale'].default_value=360
        fine.inputs['Detail'].default_value=1
        links.new(coord.outputs['Object'],fine.inputs['Vector'])
        bump=nodes.new('ShaderNodeBump')
        bump.inputs['Strength'].default_value=.10
        bump.inputs['Distance'].default_value=.00005
        links.new(fine.outputs['Fac'],bump.inputs['Height'])
        links.new(bump.outputs[0],shader.inputs['Normal'])
        finishes.append(mat)
    size=1.2
    gap=.002
    for ix in range(math.ceil(width/size)):
        for iy in range(math.ceil(depth/size)):
            sx=min(size,width-ix*size)
            sy=min(size,depth-iy*size)
            tile=cube(f'Porcelain slab {ix:02d}-{iy:02d}',
                (ix*size+sx/2,iy*size+sy/2,-.01),(sx-gap,sy-gap,.02),
                finishes[(ix*7+iy*13)%len(finishes)],.0007)
            # World-space texture coordinates avoid repeating a pattern per slab.
            texture_origin=bpy.data.objects.get('Floor texture coordinates')
            if texture_origin is None:
                texture_origin=bpy.data.objects.new('Floor texture coordinates',None)
                bpy.context.collection.objects.link(texture_origin)
                for mat in finishes:
                    mat.node_tree.nodes.get('Texture Coordinate').object=texture_origin

def build_window():
    """A recessed casement in a real wall opening; no emissive glass."""
    before=set(bpy.data.objects)
    frame=material('Window / satin off-white aluminium',(.65,.67,.65),.3)
    reveal=material('Window / plaster reveal',(.59,.61,.57),.8)
    gasket=material('Window / EPDM seals',(.026,.031,.028),.72)
    sill=material('Window / honed limestone sill',(.48,.465,.43),.43,.00015)
    # Opening is y=2.8..4.2 and z=1.13..2.63, through a 20 cm wall.
    for y in (2.8,4.2):
        cube('Window plaster jamb',(-.10,y,1.88),(.2,.035,1.50),reveal,.002)
    cube('Window plaster head',(-.10,3.5,2.63),(.2,1.4,.035),reveal,.002)
    for y in (2.84,4.16):
        cube('Window outer frame / jamb',(-.105,y,1.88),(.075,.065,1.43),frame,.004)
    for z in (1.17,2.59):
        cube('Window outer frame / rail',(-.105,3.5,z),(.075,1.38,.065),frame,.004)
    cube('Window central mullion',(-.087,3.5,1.88),(.082,.055,1.40),frame,.003)
    glass=material('Window / clear double glazing',(.97,.985,1.0),.012)
    shader=glass.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Transmission Weight'].default_value=1
    shader.inputs['IOR'].default_value=1.46
    for yc in (3.17,3.83):
        for y in (yc-.285,yc+.285):
            cube('Casement rubber seal',(-.090,y,1.88),(.016,.012,1.31),gasket,.001)
        for z in (1.23,2.53):
            cube('Casement rubber seal',(-.090,yc,z),(.016,.58,.012),gasket,.001)
        cube('Window glass / transparent pane',(-.115,yc,1.88),(.004,.57,1.29),glass)
    cube('Stone sill / projecting eased edge',(.025,3.5,1.11),(.34,1.52,.045),sill,.005)
    metal=material('Window / brushed nickel hardware',(.36,.38,.37),.24)
    metal.node_tree.nodes.get('Principled BSDF').inputs['Metallic'].default_value=.8
    cube('Window handle base',(-.032,3.55,1.81),(.022,.025,.06),metal,.004)
    cube('Window handle lever',(-.009,3.55,1.77),(.024,.018,.10),metal,.006)
    # Daylight enters from outside the aperture; the frame casts real shadows.
    light=area('Overcast daylight through opening',(-2.0,3.3,4.2),(1.5,2.5,.3),650,1.4,(.88,.94,1))
    light.data.shape='RECTANGLE'
    light.data.size=1.25
    light.data.size_y=1.25
    light.visible_camera=False
    light.visible_glossy=False
    light.visible_transmission=False
    for obj in set(bpy.data.objects)-before:
        obj.location.y+=WINDOW_CENTER_Y-3.5

def build_room(scenario):
    w,d,h = scenario['physics']['room_size']
    plaster = material('Warm chalk plaster',(.59,.57,.51),.86,.0012)
    plaster_side = material('Muted sage limewash',(.31,.39,.34),.9,.0012)
    trim = material('Painted ivory joinery',(.72,.70,.64),.48,.0003)
    dark = material('Charcoal metal',(.025,.03,.029),.38)
    oak = material('Natural oak frame',(.22,.115,.055),.5,.0005)
    add_oak_grain(oak)
    paper = material('Uncoated art paper',(.69,.64,.52),.95)
    terracotta = material('Clay pigment',(.33,.12,.065),.95)
    # Extend the display floor past the camera-side cutaway to avoid exposed edges.
    visual_w, visual_d=max(w,12),max(d,12)
    if scenario['assets']['floor']=='matte_limestone_porcelain':
        porcelain_floor(visual_w,visual_d)
    else:
        floor_mat=terrazzo_material() if scenario['assets']['floor']=='procedural_fine_terrazzo' else floor_material(ROOT/'assets'/'polyhaven'/'volleyball_corner_rebound'/scenario['assets']['floor'])
        cube('Floor', (visual_w/2,visual_d/2,-.1),(visual_w,visual_d,.2),floor_mat)
    # Partition the wall around the actual window opening, retaining the solid
    # impact face elsewhere. The glazing closes the unchanged collision plane.
    for name,center,size in (
        ('Wall_X / corner side',(-.1,(WINDOW_CENTER_Y-.7)/2,(h+.07)/2),(.2,WINDOW_CENTER_Y-.7,h-.07)),
        ('Wall_X / outer side',(-.1,(WINDOW_CENTER_Y+.7+d)/2,(h+.07)/2),(.2,d-WINDOW_CENTER_Y-.7,h-.07)),
        ('Wall_X / below window',(-.1,WINDOW_CENTER_Y,.60),(.2,1.4,1.06)),
        ('Wall_X / above window',(-.1,WINDOW_CENTER_Y,(2.63+h)/2),(.2,1.4,h-2.63))):
        cube(name,center,size,plaster_side)
    cube('Wall_Y / impact face y=0',(w/2,-.1,(h+.07)/2),(w,.2,h-.07),plaster)
    cube('Far wall X / physical boundary',(w+.1,d/2,h/2),(.2,d,h),plaster_side)
    cube('Far wall Y / physical boundary',(w/2,d+.1,h/2),(w,.2,h),plaster)
    # Lit only by the sky and the daylight through the window (see
    # exempt_slab_from_fills), so its albedo carries the whole tone: 0.73
    # was tuned against a slab that the interior fills also brushed.
    ceiling=material('Ceiling / soft white plaster',(.88,.868,.832),.9)
    cube('Interior ceiling',(w/2,d/2,h+.08),(w,d,.16),ceiling)
    # Flush skirting: faces match the physics planes exactly, no visual protrusion.
    cube('Flush skirting X',(-.1,d/2,.035),(.2,d,.07),trim)
    cube('Flush skirting Y',(w/2,-.1,.035),(w,.2,.07),trim)
    import_wall_art(MODELS/scenario['assets']['paintings'])
    import_air_conditioner(MODELS/scenario['assets']['air_conditioner'])
    build_background(oak,trim,dark,terracotta,plaster_side)
    build_spare_balls(MODELS/scenario['assets']['ball'])
    # Outlet is on a part of the wall away from the ball trajectory.
    cube('Outlet face',(.004,2.9,.36),(.008,.085,.085),trim,.003)
    for yy in (2.88,2.92):
        cube('Outlet socket',(.009,yy,.36),(.003,.007,.016),dark,.001)
    build_window()
    area('Soft room fill',(4.2,4.5,2.88),(2.4,2.4,.2),200,3.5,(1,.96,.9))
    area('Ceiling bounce',(1.7,1.7,2.85),(1.2,1,.0),90,2.4,(1,.97,.92))
    # A broad, fixed fill lifts the foreground boards and the camera-facing
    # side of the ball throughout the trajectory, without tracking the ball.
    area('Broad foreground and ball fill',(7.0,5.8,2.65),(3.2,3.2,.8),120,3.5,(1,.97,.93))
    scene = bpy.context.scene
    scene.world = bpy.data.worlds.new('Quiet ambient interior')
    scene.world.use_nodes=True
    nodes,links=scene.world.node_tree.nodes,scene.world.node_tree.links
    environment=nodes.new('ShaderNodeTexEnvironment')
    environment.image=bpy.data.images.load(str(ROOT/'assets'/'polyhaven'/'volleyball_corner_rebound'/'overcast_industrial_courtyard_4k.hdr'),check_existing=True)
    coord=nodes.new('ShaderNodeTexCoord')
    mapping=nodes.new('ShaderNodeMapping')
    mapping.inputs['Rotation'].default_value[2]=math.radians(270)
    links.new(coord.outputs['Generated'],mapping.inputs['Vector'])
    links.new(mapping.outputs[0],environment.inputs['Vector'])
    links.new(environment.outputs['Color'],nodes['Background'].inputs['Color'])
    nodes['Background'].inputs['Strength'].default_value=1.1

def cylinder(name, center, radius, depth, mat):
    bpy.ops.mesh.primitive_cylinder_add(vertices=48,radius=radius,depth=depth,location=center)
    obj=bpy.context.object
    obj.name=name
    obj.data.materials.append(mat)
    for face in obj.data.polygons:
        face.use_smooth=True
    bevel=obj.modifiers.new('Ceramic rounded rim','BEVEL')
    bevel.width=.007
    bevel.segments=3
    obj.modifiers.new('Weighted normals','WEIGHTED_NORMAL')
    return obj

def add_oak_grain(mat):
    nodes,links=mat.node_tree.nodes,mat.node_tree.links
    if nodes.get('Oak grain color'):
        return
    coord=nodes.new('ShaderNodeTexCoord')
    scale=nodes.new('ShaderNodeVectorMath')
    scale.operation='MULTIPLY'
    scale.inputs[1].default_value=(1.5,65,6)
    links.new(coord.outputs['Object'],scale.inputs[0])
    noise=nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value=3.0
    noise.inputs['Detail'].default_value=2
    links.new(scale.outputs['Vector'],noise.inputs['Vector'])
    ramp=nodes.new('ShaderNodeValToRGB')
    ramp.name='Oak grain color'
    ramp.color_ramp.elements[0].position=.15
    ramp.color_ramp.elements[0].color=(.17,.083,.033,1)
    ramp.color_ramp.elements[1].position=.85
    ramp.color_ramp.elements[1].color=(.29,.16,.075,1)
    links.new(noise.outputs['Fac'],ramp.inputs[0])
    links.new(ramp.outputs['Color'],nodes.get('Principled BSDF').inputs['Base Color'])

def build_background(oak,trim,dark,clay,sage):
    x,y,z=CABINET_CENTER
    w,d,h=CABINET_SIZE
    cube('Closed oak sideboard',CABINET_CENTER,CABINET_SIZE,oak,.009)
    front=y+d/2
    for xx in (x-w/4,x+w/4):
        cube('Recessed cabinet door',(xx,front+.002,z),(.70,.005,h-.11),oak,.003)
        cube('Slim cabinet handle',(xx+.23,front+.015,z+.13),(.016,.026,.09),dark,.004)
    book_colors=((.12,.19,.24),(.53,.28,.16),(.59,.57,.45))
    top=h
    for i,color in enumerate(book_colors):
        cover=material(f'Clothbound book {i}',color,.85,.0005)
        bx=x-.36+(.025 if i==1 else 0)
        bz=top+.02+i*.038
        cube('Book paper block',(bx,y+.005,bz),(.31,.105,.029),trim,.002)
        for delta in (-.017,.017):
            cube('Book cloth cover',(bx,y+.005,bz+delta),(.33,.12,.005),cover,.002)
    cylinder('Earthenware vase',(x+.38,y,h+.15),.095,.30,clay)
    cylinder('Vase dark opening',(x+.38,y,h+.302),.058,.002,dark)
    # The corner is left empty: no planter, no foliage, nothing to trip the ball.

def exempt_slab_from_fills():
    """Let the ceiling hear the daylight and the sky, but not the interior fills.

    The three interior fills are 2.4-3.5 m disks hanging 0.12-0.35 m under the
    slab and tilted 45-70 degrees, so the rim of every one of them pokes up
    through it -- `cz + r * sqrt(1 - nz^2)` puts their top edges at 3.19, 4.13 and
    4.28 m against a slab whose underside is at 3.00 m.  Every other surface is
    lit by the disk's face and does not care.  The slab is lit only by the rim,
    at grazing angles, which is what the blotch on the ceiling is: measured over
    the slab, the interior fills alone give mean 51.8 with std 18.8, while the
    sky and the window daylight alone give a flat 0.4.

    Light linking states that directly instead of moving lights that everything
    else depends on.  Called once the whole shot exists, because the receiver
    collection has to hold every object that is not the slab.
    """
    slab = bpy.data.objects.get('Interior ceiling')
    if slab is None or not hasattr(slab, 'light_linking'):
        return None
    existing = bpy.data.collections.get('Lit by the interior fills')
    if existing is not None:
        return existing
    receivers = bpy.data.collections.new('Lit by the interior fills')
    bpy.context.scene.collection.children.link(receivers)
    for obj in bpy.context.scene.objects:
        if obj is not slab:
            receivers.objects.link(obj)
    for obj in bpy.context.scene.objects:
        if obj.type == 'LIGHT' and 'Overcast' not in obj.name:
            obj.light_linking.receiver_collection = receivers
    return receivers


def build_spare_balls(path):
    first=import_ball(path,SPARE_BALL_RADIUS)
    first.name='Spare volleyball 1 / static'
    for index,position in enumerate(SPARE_BALL_CENTERS):
        body=first if index==0 else first.copy()
        if index:
            body.data=first.data.copy()
            bpy.context.collection.objects.link(body)
        body.name=f'Spare volleyball {index+1} / static'
        body.animation_data_clear()
        body.location=position
        body.rotation_mode='XYZ'
        body.rotation_euler=((.4,.9,.2),(1.2,.3,2.1))[index]

def import_wall_art(path):
    from mathutils import Matrix
    before=set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    bpy.context.view_layer.update()
    imported=[o for o in bpy.data.objects if o not in before]
    candidates=sorted([o for o in imported if o.type=='MESH' and 'wall_picture' in o.name],key=lambda o:o.name)
    if not candidates:
        raise ValueError('No framed picture meshes in cafe_wall_pictures.glb')
    chosen=sorted([o for o in candidates if o.name.startswith(PICTURE_MESH)],key=lambda o:o.name)
    original=(chosen or candidates)[0]
    rotation=Matrix.Rotation(math.pi/2,4,'Z')
    for index,(x,z,height) in enumerate(((3.0,1.75,.90),)):
        mesh=original.data.copy()
        mesh.transform(rotation@original.matrix_world)
        lo=Vector(tuple(min(v.co[i] for v in mesh.vertices) for i in range(3)))
        hi=Vector(tuple(max(v.co[i] for v in mesh.vertices) for i in range(3)))
        origin=Vector(((lo.x+hi.x)/2,lo.y,(lo.z+hi.z)/2))
        scale=height/(hi.z-lo.z)
        for vertex in mesh.vertices:
            vertex.co=(vertex.co-origin)*scale+Vector((x,.006,z))
        body=bpy.data.objects.new(f'Imported framed art {index+1} / {original.name}',mesh)
        bpy.context.collection.objects.link(body)
        for mat in mesh.materials:
            if mat and mat.use_nodes:
                for node in mat.node_tree.nodes:
                    if node.type=='BSDF_PRINCIPLED':
                        node.inputs['Emission Strength'].default_value=0
    for obj in imported:
        bpy.data.objects.remove(obj,do_unlink=True)

def import_air_conditioner(path):
    from mathutils import Matrix
    before=set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported=[o for o in bpy.data.objects if o not in before]
    meshes=[o for o in imported if o.type=='MESH']
    if not meshes:
        raise ValueError('Indoor unit asset contains no meshes')
    bpy.ops.object.select_all(action='DESELECT')
    for obj in meshes:
        obj.animation_data_clear()
        obj.select_set(True)
    bpy.context.view_layer.objects.active=meshes[0]
    if len(meshes)>1:
        bpy.ops.object.join()
    body=bpy.context.object
    world=body.matrix_world.copy()
    body.parent=None
    body.matrix_world=world
    for obj in imported:
        if obj!=body and obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj,do_unlink=True)
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    # The asset's back is its +Y face and the louvre panel faces -Y.  The wall it
    # goes on is x=0 with the room on +X, so a quarter turn about Z (+Y -> -X)
    # lays the back on the plaster and points the panel into the room; the unit's
    # width then runs along Y and its depth along X, which is why AC_SIZE swaps
    # the two.  Width, not height, is what a split is specified by, so that is
    # the one dimension the uniform scale is pinned to.
    body.data.transform(Matrix.Rotation(math.pi/2,4,'Z'))
    lo=Vector(tuple(min(v.co[i] for v in body.data.vertices) for i in range(3)))
    hi=Vector(tuple(max(v.co[i] for v in body.data.vertices) for i in range(3)))
    factor=AC_WIDTH/(hi.y-lo.y)
    centre=Vector((lo.x,(lo.y+hi.y)*.5,(lo.z+hi.z)*.5))
    for vertex in body.data.vertices:
        vertex.co=(vertex.co-centre)*factor+Vector((AC_BACK_GAP,AC_CENTER[1],AC_CENTER[2]))
    body.location=(0,0,0)
    body.name='Split indoor unit'
    for poly in body.data.polygons:
        poly.use_smooth=True
    for mat in body.data.materials:
        if not mat or not mat.use_nodes:
            continue
        for node in mat.node_tree.nodes:
            if node.type=='BSDF_PRINCIPLED':
                node.inputs['Emission Strength'].default_value=0
                # The glb's packed metallic channel reads 0.91 over the painted
                # shell, which is an authoring slip rather than the object: a
                # split indoor unit is painted steel and plastic.  Under this
                # overcast HDR that value turns it into a mirror and it renders
                # blue-grey, so metallic is pinned to 0.  Roughness keeps the
                # supplied map, so the sheen is still the asset's own.
                for link in list(node.inputs['Metallic'].links):
                    mat.node_tree.links.remove(link)
                node.inputs['Metallic'].default_value=0

def import_ball(path, radius):
    before=set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported=[o for o in bpy.data.objects if o not in before]
    meshes=[o for o in imported if o.type=='MESH']
    if not meshes:
        raise ValueError('Volleyball asset contains no meshes')
    bpy.ops.object.select_all(action='DESELECT')
    for obj in meshes:
        obj.animation_data_clear()
        obj.select_set(True)
    bpy.context.view_layer.objects.active=meshes[0]
    if len(meshes)>1:
        bpy.ops.object.join()
    ball=bpy.context.object
    world=ball.matrix_world.copy()
    ball.parent=None
    ball.matrix_world=world
    for obj in imported:
        if obj!=ball and obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj,do_unlink=True)
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    # Bounding sphere centre, so the visual centre matches GEOM_SPHERE.
    lo=Vector(tuple(min(v.co[i] for v in ball.data.vertices) for i in range(3)))
    hi=Vector(tuple(max(v.co[i] for v in ball.data.vertices) for i in range(3)))
    center=(lo+hi)*.5
    factor=2*radius/max(hi-lo)
    for vertex in ball.data.vertices:
        vertex.co=(vertex.co-center)*factor
    ball.location=(0,0,0)
    ball.name='volleyball'
    for poly in ball.data.polygons:
        poly.use_smooth=True
    for mat in ball.data.materials:
        if not mat or not mat.use_nodes:
            continue
        for node in mat.node_tree.nodes:
            if node.type=='BSDF_PRINCIPLED':
                node.inputs['Emission Strength'].default_value=0
                if not node.inputs['Roughness'].is_linked:
                    node.inputs['Roughness'].default_value=.68
    return ball

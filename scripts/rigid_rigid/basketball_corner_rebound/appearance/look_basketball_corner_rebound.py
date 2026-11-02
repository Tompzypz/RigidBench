"""Photographic materials and metre-scale architectural room, authored locally."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math
import bpy
from mathutils import Vector
from scene_config import MODELS, ROOT

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
    obj = bpy.data.objects.new(name,data)
    bpy.context.collection.objects.link(obj)
    obj.location = pos
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

# The shared picture library packs three framed prints into one file; this
# scene hangs one of them, and the render block says which and where.
DEFAULT_PICTURE = {'model': 'cafe_wall_pictures.glb', 'object': 'wall_picture_2',
                   'height_m': .62, 'location': [3.05, .03, 1.55]}


def hang_picture(spec):
    """Hang one framed print from assets/models flat against the y=0 wall.

    The library model is a group of three frames whose local +X is the pane
    normal, so a quarter turn about Z stands the chosen one up facing into the
    room. It is then scaled to a real wall height and slid back against the
    plaster, which keeps the frame out of every ball trajectory.
    """
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(MODELS / spec['model']))
    imported = [o for o in bpy.data.objects if o not in before]
    frames = [o for o in imported if o.type == 'MESH' and o.name.startswith(spec['object'] + '_')]
    if len(frames) != 1:
        raise ValueError(f"{spec['model']} has no single mesh named {spec['object']!r}")
    picture = frames[0]
    bpy.ops.object.select_all(action='DESELECT')
    picture.select_set(True)
    bpy.context.view_layer.objects.active = picture
    if picture.parent:
        bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    for obj in imported:
        if obj is not picture and obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    # glTF imports arrive in quaternion mode, where rotation_euler is inert.
    picture.rotation_mode = 'XYZ'
    picture.rotation_euler = (0, 0, math.pi/2)
    bpy.context.view_layer.update()
    corners = [picture.matrix_world @ Vector(c) for c in picture.bound_box]
    height = max(c.z for c in corners) - min(c.z for c in corners)
    factor = spec['height_m'] / max(height, 1e-6)
    picture.scale = (factor, factor, factor)
    bpy.context.view_layer.update()
    corners = [picture.matrix_world @ Vector(c) for c in picture.bound_box]
    low = [min(c[i] for c in corners) for i in range(3)]
    high = [max(c[i] for c in corners) for i in range(3)]
    target = spec['location']
    picture.location = (target[0] - (low[0] + high[0])/2,
                        target[1] - low[1],
                        target[2] - (low[2] + high[2])/2)
    picture.name = 'Wall picture'
    return picture


def frosted_glass():
    """A pane of acid-etched glass rather than a white card.

    The daylight lamp that stands in for the window hangs a hand's width in
    front of this pane, so a lit BSDF clips into a flat white rectangle. The
    pane therefore scatters light of its own: a top-down falloff, the washed-out
    shapes of whatever stands outside, and a fine etch grain, all fed straight
    into an emission node so the value never reaches clipping.
    """
    mat = bpy.data.materials.new('Frosted window glass')
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    for node in [n for n in nodes if n.type != 'OUTPUT_MATERIAL']:
        nodes.remove(node)
    emission = nodes.new('ShaderNodeEmission')
    emission.inputs['Strength'].default_value = 2.60
    coord = nodes.new('ShaderNodeTexCoord')
    grain = nodes.new('ShaderNodeTexNoise')
    grain.inputs['Scale'].default_value = 20.0
    grain.inputs['Detail'].default_value = 8.0
    grain.inputs['Roughness'].default_value = .55
    links.new(coord.outputs['Object'], grain.inputs['Vector'])
    haze = nodes.new('ShaderNodeTexNoise')
    haze.inputs['Scale'].default_value = 0.9
    haze.inputs['Detail'].default_value = 2.0
    links.new(coord.outputs['Object'], haze.inputs['Vector'])
    column = nodes.new('ShaderNodeSeparateXYZ')
    links.new(coord.outputs['Generated'], column.inputs[0])

    def maths(operation, left, right=None):
        node = nodes.new('ShaderNodeMath')
        node.operation = operation
        for index, source in enumerate((left, right)):
            if source is None:
                continue
            if isinstance(source, float):
                node.inputs[index].default_value = source
            else:
                links.new(source, node.inputs[index])
        return node.outputs[0]

    level = maths('ADD', maths('MULTIPLY', column.outputs['Z'], .40), .30)
    level = maths('ADD', level, maths('MULTIPLY', maths('SUBTRACT', haze.outputs['Fac'], .5), .34))
    level = maths('ADD', level, maths('MULTIPLY', maths('SUBTRACT', grain.outputs['Fac'], .5), .05))
    # Falloff towards the pane border: the reveal stands between the glazing
    # and the sky, so the glass dims as it approaches the frame.
    edge = maths('MINIMUM',
                 maths('MINIMUM', column.outputs['Y'],
                       maths('SUBTRACT', 1.0, column.outputs['Y'])),
                 maths('MINIMUM', column.outputs['Z'],
                       maths('SUBTRACT', 1.0, column.outputs['Z'])))
    edge = maths('MINIMUM', maths('MULTIPLY', edge, 7.0), 1.0)
    emission.inputs['Strength'].default_value = 2.60
    links.new(maths('ADD', .22, maths('MULTIPLY', edge, .78)), emission.inputs['Strength'])
    tone = nodes.new('ShaderNodeValToRGB')
    tone.color_ramp.elements[0].position = 0.0
    tone.color_ramp.elements[0].color = (.34, .40, .48, 1)
    tone.color_ramp.elements[1].position = 1.0
    tone.color_ramp.elements[1].color = (.99, 1.0, 1.0, 1)
    links.new(level, tone.inputs['Fac'])
    links.new(tone.outputs['Color'], emission.inputs['Color'])
    links.new(emission.outputs['Emission'], nodes['Material Output'].inputs['Surface'])
    return mat


def wall_with_opening(name, x_span, y_span, z_span, hole, mat):
    """Build a wall panel as four pieces around a rectangular opening.

    A window only reads as part of a wall if the wall has a hole to sit in: the
    reveal then has the full wall thickness behind the joinery, which is what
    tells the eye how deep the wall is.
    """
    x0, x1 = x_span
    y0, y1 = y_span
    z0, z1 = z_span
    hy0, hy1, hz0, hz1 = hole
    xc, thick = (x0 + x1) / 2, x1 - x0
    cube(f'{name} / below opening', (xc, (hy0 + hy1) / 2, (z0 + hz0) / 2),
         (thick, hy1 - hy0, hz0 - z0), mat)
    cube(f'{name} / above opening', (xc, (hy0 + hy1) / 2, (hz1 + z1) / 2),
         (thick, hy1 - hy0, z1 - hz1), mat)
    cube(f'{name} / before opening', (xc, (y0 + hy0) / 2, (z0 + z1) / 2),
         (thick, hy0 - y0, z1 - z0), mat)
    cube(f'{name} / after opening', (xc, (hy1 + y1) / 2, (z0 + z1) / 2),
         (thick, y1 - hy1, z1 - z0), mat)

def window_ring(name, centre, outer_w, outer_h, bar, depth, mat, bevel=.0015):
    """Four members closing a rectangle in the y-z plane, butted, not fused.

    The rails run the full width and the jambs are cut in between them, so no two
    members share a coplanar face: the corners read as joints instead of a decal.
    """
    x0, x1 = depth
    xc, (yc, zc) = (x0 + x1) / 2, centre
    thick = x1 - x0
    cube(f'{name} head', (xc, yc, zc + (outer_h - bar) / 2), (thick, outer_w, bar), mat, bevel)
    cube(f'{name} bottom rail', (xc, yc, zc - (outer_h - bar) / 2), (thick, outer_w, bar), mat, bevel)
    for sign, side in ((-1, 'near jamb'), (1, 'far jamb')):
        cube(f'{name} {side}', (xc, yc + sign * (outer_w - bar) / 2, zc),
             (thick, bar, outer_h - 2 * bar), mat, bevel)

def build_room(scenario):
    w,d,h = scenario['physics']['room_size']
    plaster = material('Warm chalk plaster',(.59,.57,.51),.86,.0012)
    plaster_side = material('Muted sage limewash',(.31,.39,.34),.9,.0012)
    trim = material('Painted ivory joinery',(.54,.52,.47),.9,.0003)
    dark = material('Charcoal metal',(.025,.03,.029),.38)
    oak = material('Natural oak frame',(.22,.115,.055),.5,.0005)
    # Extend the display floor past the camera-side cutaway to avoid exposed edges.
    visual_w, visual_d=max(w,12),max(d,12)
    cube('Floor', (visual_w/2,visual_d/2,-.1),(visual_w,visual_d,.2),floor_material(ROOT/'assets'/'polyhaven'/'basketball_corner_rebound'/scenario['assets']['floor']))
    # A window needs a hole to sit in, so wall X is four panels around one:
    # the reveal then has the wall's real thickness to show.
    window_hole = (1.875, 3.225, 1.130, 2.630)
    wall_with_opening('Wall_X / impact face x=0', (-.2, 0.0), (-.1, d + .1), (.07, h),
                      window_hole, plaster_side)
    cube('Wall_Y / impact face y=0',(w/2,-.1,(h+.07)/2),(w,.2,h-.07),plaster)
    # Flush skirting: faces match the physics planes exactly, no visual protrusion.
    cube('Flush skirting X',(-.1,d/2,.035),(.2,d,.07),trim)
    cube('Flush skirting Y',(w/2,-.1,.035),(w,.2,.07),trim)
    # A framed print from the shared model library, hung clear of the ball path.
    hang_picture(scenario.get('render', {}).get('picture') or DEFAULT_PICTURE)
    # Outlet is on a part of the wall away from the ball trajectory.
    cube('Outlet face',(.004,2.9,.36),(.008,.085,.085),trim,.003)
    for yy in (2.88,2.92):
        cube('Outlet socket',(.009,yy,.36),(.003,.007,.016),dark,.001)
    # A timber window inside that opening: lined through the full wall thickness,
    # sash set 55 mm into the reveal, glazing behind it. Backlit joinery is a
    # silhouette against its own light, so the members are painted a shade off
    # white and only their arrises pick up the room light.
    glass = frosted_glass()
    sash_paint = material('Eggshell sash paint', (.19, .186, .178), .96, .0)
    for _paint in (sash_paint, trim):
        _paint.node_tree.nodes['Principled BSDF'].inputs['Specular IOR Level'].default_value = .0
    win_y, win_z = 2.55, 1.88
    window_ring('Window sash', (win_y, win_z), 1.354, 1.504, .050, (-.100, -.064), sash_paint, .0008)
    cube('Window glass', (-.190, win_y, win_z), (.008, 1.292, 1.442), glass)
    # The transom runs across; the mullion is cut between it and the rails, so the
    # two never share a front face and every joint stays a joint.
    inner_w, inner_h = 1.354 - .100, 1.504 - .100
    cube('Window transom', (-.082, win_y, win_z), (.036, inner_w, .044), sash_paint, .0008)
    for sign, side in ((1, 'above'), (-1, 'below')):
        cube(f'Window mullion {side}', (-.082, win_y, win_z + sign * (.022 + (inner_h / 2 - .022) / 2)),
             (.036, .044, inner_h / 2 - .022), sash_paint, .0008)
    cube('Window sill', (-.049, win_y, 1.115), (.178, 1.470, .046), trim, .0008)
    # Daylight starts inside the opening, not in the room: the wall then masks
    # it to the shape of the hole, the sash stays silhouetted, and the reveal
    # picks up the glow instead of the plaster around the frame.
    area('Broad window daylight',(-.030,2.55,1.88),(6.0,2.55,1.88),1150,1.50,(.86,.92,1))
    area('Warm reflected room light',(3.8,3.6,2.6),(.8,.7,.2),28,2.5,(1,.87,.70))
    area('Ceiling bounce',(1.7,1.7,2.85),(1.2,1,.0),17,2.4,(1,.96,.88))
    scene = bpy.context.scene
    scene.world = bpy.data.worlds.new('Quiet ambient interior')
    scene.world.use_nodes=True
    scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.68,.76,.83,1)
    scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=.22

def import_ball(path, radius):
    before=set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported=[o for o in bpy.data.objects if o not in before]
    meshes=[o for o in imported if o.type=='MESH']
    if not meshes:
        raise ValueError('Basketball asset contains no meshes')
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
    ball.name='basketball'
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

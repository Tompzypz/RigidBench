"""Local scanned ball, scanned turf, and light-weight explicit grass blades."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math
from pathlib import Path
import random
from scene_geometry import RADIUS, KEYS

ROOT = _PCVE_ROOT
MODELS = ROOT / 'assets/models'
ASSETS = ROOT / 'assets' / 'polyhaven' / 'soccer_ball_collision'
APPEARANCE_VERSION = 'soccer-natural-turf-v2'


def material(bpy, name, color, roughness=.7):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    bs = mat.node_tree.nodes.get('Principled BSDF')
    bs.inputs['Base Color'].default_value = (*color, 1)
    bs.inputs['Roughness'].default_value = roughness
    return mat


def turf_material(bpy):
    mat = material(bpy, 'Scanned short grass and soil', (.065,.12,.025), .9)
    n, l = mat.node_tree.nodes, mat.node_tree.links
    bs = n.get('Principled BSDF')
    coord = n.new('ShaderNodeTexCoord')
    mapping = n.new('ShaderNodeVectorMath'); mapping.operation = 'SCALE'
    mapping.inputs['Scale'].default_value = 1 / .65
    l.new(coord.outputs['UV'], mapping.inputs[0])
    images = {}
    for channel in ('diff','rough','nor_gl','disp'):
        path = ASSETS / f'grass_ground_{channel}_2k.jpg'
        image = bpy.data.images.load(str(path), check_existing=True)
        image.colorspace_settings.name = 'sRGB' if channel == 'diff' else 'Non-Color'
        tex = n.new('ShaderNodeTexImage'); tex.image = image
        l.new(mapping.outputs[0], tex.inputs['Vector']); images[channel] = tex
    tint = n.new('ShaderNodeMixRGB'); tint.blend_type = 'MULTIPLY'
    tint.inputs[0].default_value = .7; tint.inputs[2].default_value = (.63,.98,.40,1)
    l.new(images['diff'].outputs['Color'], tint.inputs[1])
    l.new(tint.outputs[0], bs.inputs['Base Color'])
    l.new(images['rough'].outputs['Color'], bs.inputs['Roughness'])
    normal = n.new('ShaderNodeNormalMap'); normal.inputs['Strength'].default_value = .65
    l.new(images['nor_gl'].outputs['Color'], normal.inputs['Color'])
    bump = n.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = .45
    bump.inputs['Distance'].default_value = .006
    l.new(images['disp'].outputs['Color'], bump.inputs['Height'])
    l.new(normal.outputs['Normal'], bump.inputs['Normal'])
    l.new(bump.outputs['Normal'], bs.inputs['Normal'])
    return mat


def grass_blades(bpy):
    """One batched mesh; deterministic bent ribbons avoid hair/particle overhead."""
    rng = random.Random(618)
    palette = [(.035,.105,.009), (.055,.16,.014), (.095,.225,.022),
               (.145,.26,.035), (.07,.14,.012), (.24,.25,.065)]
    mats = []
    for i, color in enumerate(palette):
        mat = material(bpy, f'Grass blade variation {i}', color, .73)
        shader = mat.node_tree.nodes.get('Principled BSDF')
        shader.inputs['Subsurface Weight'].default_value = .065
        mats.append(mat)
    verts, faces, ids = [], [], []
    for _ in range(720000):
        x, y = rng.uniform(-4,4), rng.uniform(-3.2,7)
        # Higher density around the action; far turf is a texture + sparse blades.
        if y > 3 and rng.random() < min(.55, (y-3)*.14):
            continue
        height = rng.uniform(.014,.034)
        width = rng.uniform(.0008,.0022)
        theta = rng.random() * math.tau
        dx, dy = math.cos(theta)*width, math.sin(theta)*width
        bend_x, bend_y = rng.uniform(-.009,.009), rng.uniform(-.009,.009)
        z = -.006
        start = len(verts)
        verts.extend([(x-dx,y-dy,z), (x+dx,y+dy,z),
                      (x+dx*.6+bend_x*.3,y+dy*.6+bend_y*.3,z+height*.57),
                      (x-dx*.6+bend_x*.3,y-dy*.6+bend_y*.3,z+height*.57),
                      (x+bend_x,y+bend_y,z+height)])
        faces.extend([(start,start+1,start+2,start+3), (start+3,start+2,start+4)])
        index = rng.choices(range(6), [22,29,25,10,12,2])[0]
        ids.extend([index,index])
    mesh = bpy.data.meshes.new('Batched short bent turf blades')
    mesh.from_pydata(verts, [], faces); mesh.update()
    obj = bpy.data.objects.new('Individual living grass blades', mesh)
    bpy.context.collection.objects.link(obj)
    for mat in mats: mesh.materials.append(mat)
    mesh.polygons.foreach_set('material_index', ids)


def build_environment(bpy, scene):
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0,0,-.006))
    ground = bpy.context.object; ground.name = 'Level grass field'
    ground.scale = (200,200,1)
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    # UV units in metres, independent of the large horizon plane.
    for poly in ground.data.polygons:
        for vi, li in zip(poly.vertices,poly.loop_indices):
            v = ground.data.vertices[vi].co
            ground.data.uv_layers.active.data[li].uv = (v.x,v.y)
    ground.data.materials.append(turf_material(bpy))
    grass_blades(bpy)
    # A restrained field marking, away from the collision and outside its physics.
    chalk = material(bpy, 'Weathered chalk field marking', (.66,.70,.52), .95)
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0,3.5,-.0045))
    line = bpy.context.object; line.name = 'Distant touchline'; line.scale = (30,.065,1)
    line.data.materials.append(chalk)
    world = bpy.data.worlds.new('Clear outdoor daylight'); world.use_nodes = True
    scene.world = world
    n, l = world.node_tree.nodes, world.node_tree.links
    sky = n.new('ShaderNodeTexSky'); sky.sky_type = 'NISHITA'
    sky.sun_elevation = math.radians(32); sky.sun_rotation = math.radians(140)
    sky.sun_disc = False; sky.altitude = .15; sky.air_density = 1.1
    l.new(sky.outputs['Color'],n.get('Background').inputs['Color'])
    n.get('Background').inputs['Strength'].default_value = .32
    bpy.ops.object.light_add(type='SUN', location=(-3,-4,6))
    sun = bpy.context.object; sun.name = 'Warm afternoon sun'
    sun.rotation_euler = (math.radians(30), math.radians(-28), math.radians(-32))
    sun.data.energy = 3.; sun.data.angle = math.radians(4)
    sun.data.color = (1.,.91,.77)


def make_balls(bpy):
    from mathutils import Matrix, Vector
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(MODELS/'cheap_soccer_ball.glb'))
    imported = set(bpy.data.objects) - before
    meshes = [o for o in imported if o.type == 'MESH' and len(o.data.materials)]
    if len(meshes) != 1:
        raise RuntimeError('Expected one soccer ball mesh in supplied GLB')
    obj = meshes[0]
    # Evaluate the supplied rig once, then bake its world transform into the mesh.
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(deps), depsgraph=deps)
    mesh.transform(obj.matrix_world)
    lo = Vector(tuple(min(v.co[j] for v in mesh.vertices) for j in range(3)))
    hi = Vector(tuple(max(v.co[j] for v in mesh.vertices) for j in range(3)))
    center = (lo+hi)*.5
    radius = max((v.co-center).length for v in mesh.vertices)
    for v in mesh.vertices:
        v.co = (v.co-center) * (RADIUS/radius)
    mesh.update()
    for o in imported: bpy.data.objects.remove(o, do_unlink=True)
    for poly in mesh.polygons: poly.use_smooth = True
    # Leather/rubber is a dielectric. Retain the supplied albedo, wear and seams.
    for mat in mesh.materials:
        if not mat or not mat.use_nodes: continue
        for shader in mat.node_tree.nodes:
            if shader.type != 'BSDF_PRINCIPLED': continue
            for name, value in [('Metallic',0.),('Roughness',.59)]:
                for link in list(shader.inputs[name].links): mat.node_tree.links.remove(link)
                shader.inputs[name].default_value = value
    result = {}
    for i, key in enumerate(KEYS):
        root = bpy.data.objects.new(key, None); bpy.context.collection.objects.link(root)
        visual = bpy.data.objects.new(f'{key}_scanned_leather', mesh)
        bpy.context.collection.objects.link(visual); visual.parent = root
        visual.rotation_euler = (.20+i*.55,.35+i*.8,-.18+i*.6)
        result[key] = root
    print(f'[assets] soccer radius={RADIUS} m; {len(mesh.vertices)} vertices', flush=True)
    return result

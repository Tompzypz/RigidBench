"""Procedural middle-school physics lab and the two visible rigid bodies.

Only geometry and appearance live here. Nothing in this module knows about
physics parameters, so a mass or speed edit changes the clip without touching
a single material, and the collision shapes in ``simulate_pendulum_box_collision.py``
stay the authority on size and contact.

The set is built the way the other bench-top scenes build theirs: every prop is
procedural except for the local textured blackboard and pen assets; the bench top is exactly ``TABLE_Z`` so the
block visibly rests on the surface the solver uses, and the retort stand's rod
ends at ``scene_geometry.PIVOT`` so the drawn thread leaves from the point the
constraint hangs from.

Layout, seen from the default camera at -Y
------------------------------------------
* the block starts left of centre and slides right;
* the bob hangs at x = 0, just above the bench, and swings in the X-Z plane;
* the retort stand stands to the right, its cross-arm reaching left to the
  pivot, so neither the rod nor its base is ever in the block's path;
* the slate board, splashback and shelf stay behind y = 1.2, out of reach.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)

import sys
from pathlib import Path
sys.path.insert(0, str(_PCVE_ROOT / 'scripts'))
from pcve_blender_compat import (shader_socket, set_shader_input, eevee_engine, set_eevee_property, set_color_property)
import math, random
from pathlib import Path
from scene_geometry import (
    BENCH_SIZE, BOB_RADIUS, BOX_SIZE, PENDULUM_LENGTH, PIVOT, TABLE_Z)

ENVIRONMENT_THEME = 'school_physics_lab_pendulum_bench'
APPEARANCE_VERSION = 4

# The visible bench top must be the same surface the solver drops the block on.
BENCH_TOP = TABLE_Z
STAND = (0.40, 0.12)          # foot of the retort stand, on the bench
STAND_TOP = PIVOT[2] + .055


# --------------------------------------------------------------- materials


def _material(bpy, name, color, rough=.62, metallic=0., coat=0., bump=0., bump_scale=14.,
              grain=None, speckle=None, speckle_color=None, bump_distance=.00025):
    """Principled surface with optional procedural relief, wood grain or aggregate."""
    material = bpy.data.materials.new(name)
    material.diffuse_color = (*color, 1.); material.use_nodes = True
    nodes = material.node_tree.nodes; links = material.node_tree.links
    bsdf = nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (*color, 1.)
    bsdf.inputs['Roughness'].default_value = rough
    if metallic:
        bsdf.inputs['Metallic'].default_value = metallic
    if coat:
        set_shader_input(bsdf, 'Coat Weight', coat)
        set_shader_input(bsdf, 'Coat Roughness', 0.24)
    if not (bump > 0. or speckle):
        return material
    vector = nodes.new('ShaderNodeTexCoord').outputs['Object']
    if grain:
        mapping = nodes.new('ShaderNodeMapping'); mapping.inputs['Scale'].default_value = grain
        links.new(mapping.inputs['Vector'], vector); vector = mapping.outputs['Vector']
    if bump > 0.:
        noise = nodes.new('ShaderNodeTexNoise')
        noise.inputs['Scale'].default_value = bump_scale
        noise.inputs['Detail'].default_value = 3.
        noise.inputs['Roughness'].default_value = .52
        links.new(noise.inputs['Vector'], vector)
        relief = nodes.new('ShaderNodeBump')
        relief.inputs['Strength'].default_value = bump
        relief.inputs['Distance'].default_value = bump_distance
        links.new(relief.inputs['Height'], noise.outputs['Fac'])
        links.new(bsdf.inputs['Normal'], relief.outputs['Normal'])
    if speckle:
        aggregate = nodes.new('ShaderNodeTexVoronoi'); aggregate.inputs['Scale'].default_value = speckle
        links.new(aggregate.inputs['Vector'], vector)
        ramp = nodes.new('ShaderNodeValToRGB')
        ramp.color_ramp.elements[0].position = .36; ramp.color_ramp.elements[0].color = (*color, 1.)
        ramp.color_ramp.elements[1].position = .68
        ramp.color_ramp.elements[1].color = (*(speckle_color or tuple(c * .55 for c in color)), 1.)
        links.new(ramp.inputs['Fac'], aggregate.outputs['Distance'])
        links.new(bsdf.inputs['Base Color'], ramp.outputs['Color'])
    return material


def _wood(bpy, name, light, dark, scale=(1.6, 9., 22.), rough=.44, coat=.12):
    """Two-tone grain: a stretched noise drives a colour ramp, plus fine relief.

    A single flat brown cube reads as plastic at this distance. Wood needs the
    value to wander along the length of the board, which is what the very
    anisotropic mapping scale does: fine across the grain, long along it.
    """
    material = bpy.data.materials.new(name); material.use_nodes = True
    nodes = material.node_tree.nodes; links = material.node_tree.links
    bsdf = nodes['Principled BSDF']
    bsdf.inputs['Roughness'].default_value = rough
    set_shader_input(bsdf, 'Coat Weight', coat)
    set_shader_input(bsdf, 'Coat Roughness', 0.22)
    coord = nodes.new('ShaderNodeTexCoord')
    mapping = nodes.new('ShaderNodeMapping'); mapping.inputs['Scale'].default_value = scale
    links.new(mapping.inputs['Vector'], coord.outputs['Object'])
    grain = nodes.new('ShaderNodeTexNoise')
    grain.inputs['Scale'].default_value = 5.2
    grain.inputs['Detail'].default_value = 5.
    grain.inputs['Roughness'].default_value = .55
    links.new(grain.inputs['Vector'], mapping.outputs['Vector'])
    ramp = nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = .30; ramp.color_ramp.elements[0].color = (*dark, 1.)
    ramp.color_ramp.elements[1].position = .70; ramp.color_ramp.elements[1].color = (*light, 1.)
    links.new(ramp.inputs['Fac'], grain.outputs['Fac'])
    links.new(bsdf.inputs['Base Color'], ramp.outputs['Color'])
    pores = nodes.new('ShaderNodeTexNoise')
    pores.inputs['Scale'].default_value = 240.
    pores.inputs['Detail'].default_value = 3.
    links.new(pores.inputs['Vector'], mapping.outputs['Vector'])
    relief = nodes.new('ShaderNodeBump')
    relief.inputs['Strength'].default_value = .12
    relief.inputs['Distance'].default_value = .00018
    links.new(relief.inputs['Height'], pores.outputs['Fac'])
    links.new(bsdf.inputs['Normal'], relief.outputs['Normal'])
    return material


def _bench_top(bpy, name, color, rough=.46):
    """Dark lino bench top: tonal drift, long scuffs and a wide soft sheen."""
    material = bpy.data.materials.new(name); material.use_nodes = True
    nodes = material.node_tree.nodes; links = material.node_tree.links
    bsdf = nodes['Principled BSDF']
    bsdf.inputs['Roughness'].default_value = rough
    set_shader_input(bsdf, 'Coat Weight', 0.12)
    set_shader_input(bsdf, 'Coat Roughness', 0.34)
    coord = nodes.new('ShaderNodeTexCoord')
    drift = nodes.new('ShaderNodeTexNoise')
    drift.inputs['Scale'].default_value = 1.5
    drift.inputs['Detail'].default_value = 4.
    drift.inputs['Roughness'].default_value = .62
    links.new(drift.inputs['Vector'], coord.outputs['Object'])
    tone = nodes.new('ShaderNodeValToRGB')
    tone.color_ramp.elements[0].position = .26
    tone.color_ramp.elements[0].color = (*(c * .78 for c in color), 1.)
    tone.color_ramp.elements[1].position = .78
    tone.color_ramp.elements[1].color = (*(min(1., c * 1.26) for c in color), 1.)
    links.new(tone.inputs['Fac'], drift.outputs['Fac'])
    links.new(bsdf.inputs['Base Color'], tone.outputs['Color'])
    scuff_coord = nodes.new('ShaderNodeMapping')
    scuff_coord.inputs['Scale'].default_value = (2.6, 8., 3.)
    links.new(scuff_coord.inputs['Vector'], coord.outputs['Object'])
    scuff = nodes.new('ShaderNodeTexNoise')
    scuff.inputs['Scale'].default_value = 4.0
    scuff.inputs['Detail'].default_value = 2.
    links.new(scuff.inputs['Vector'], scuff_coord.outputs['Vector'])
    mask = nodes.new('ShaderNodeValToRGB')
    mask.color_ramp.elements[0].position = .64; mask.color_ramp.elements[0].color = (0., 0., 0., 1.)
    mask.color_ramp.elements[1].position = .77; mask.color_ramp.elements[1].color = (1., 1., 1., 1.)
    links.new(mask.inputs['Fac'], scuff.outputs['Fac'])
    wear = nodes.new('ShaderNodeMixRGB'); wear.inputs['Fac'].default_value = 1.
    links.new(wear.inputs['Fac'], mask.outputs['Color'])
    links.new(wear.inputs['Color1'], tone.outputs['Color'])
    wear.inputs['Color2'].default_value = (*(c * .70 for c in color), 1.)
    links.new(bsdf.inputs['Base Color'], wear.outputs['Color'])
    gloss = nodes.new('ShaderNodeMixRGB'); gloss.blend_type = 'MIX'
    links.new(gloss.inputs['Fac'], mask.outputs['Color'])
    gloss.inputs['Color1'].default_value = (rough, rough, rough, 1.)
    gloss.inputs['Color2'].default_value = (.64, .64, .64, 1.)
    links.new(bsdf.inputs['Roughness'], gloss.outputs['Color'])
    relief = nodes.new('ShaderNodeBump')
    relief.inputs['Strength'].default_value = .05
    relief.inputs['Distance'].default_value = .00012
    links.new(relief.inputs['Height'], mask.outputs['Color'])
    links.new(bsdf.inputs['Normal'], relief.outputs['Normal'])
    return material


def _place_blackboard_asset(bpy):
    """Use the board's original mesh, UVs and PBR maps; omit its pinned note."""
    from mathutils import Matrix, Vector
    asset = _PCVE_ROOT / 'assets' / 'models' / 'realistic_blackboard.glb'
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(asset))
    imported = set(bpy.data.objects) - before
    bpy.context.view_layer.update()
    meshes = [obj for obj in imported if obj.type == 'MESH']
    if not meshes:
        raise ValueError(f'Blackboard asset contains no mesh: {asset}')
    def bounds(obj):
        points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        return (Vector(tuple(min(v[i] for v in points) for i in range(3))),
                Vector(tuple(max(v[i] for v in points) for i in range(3))))
    source = max(meshes, key=lambda obj: (bounds(obj)[1] - bounds(obj)[0]).length)
    low, high = bounds(source)
    centre = (low + high) / 2
    scale = .74 / (high.z - low.z)
    mesh = source.data.copy()
    mesh.transform(source.matrix_world)
    board = bpy.data.objects.new('Real blackboard (realistic_blackboard.glb)', mesh)
    bpy.context.scene.collection.objects.link(board)
    board.matrix_world = (Matrix.Translation((-.20, 1.24, 1.085))
                          @ Matrix.Scale(scale, 4) @ Matrix.Translation(-centre))
    board['asset_path'] = 'assets/models/realistic_blackboard.glb'
    for obj in imported:
        bpy.data.objects.remove(obj, do_unlink=True)
    return board


def _place_pen_asset(bpy):
    """Keep the GLB's UVs/materials and seat its actual bounds on the bench."""
    from mathutils import Matrix, Vector
    asset = _PCVE_ROOT / 'assets' / 'models' / 'the_pen.glb'
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(asset))
    imported = set(bpy.data.objects) - before
    bpy.context.view_layer.update()
    points = [obj.matrix_world @ Vector(corner) for obj in imported
              if obj.type == 'MESH' for corner in obj.bound_box]
    if not points:
        raise ValueError(f'Pen asset contains no mesh: {asset}')
    low = Vector(tuple(min(v[i] for v in points) for i in range(3)))
    high = Vector(tuple(max(v[i] for v in points) for i in range(3)))
    scale = .145 / (high.x - low.x)
    centre = (low + high) / 2
    root = bpy.data.objects.new('Desk pen (the_pen.glb)', None)
    bpy.context.scene.collection.objects.link(root)
    for obj in imported:
        if obj.parent not in imported:
            obj.parent = root
    root.matrix_world = (Matrix.Translation((-.30, -.235, BENCH_TOP + .00015))
                         @ Matrix.Rotation(.32, 4, 'Z') @ Matrix.Scale(scale, 4)
                         @ Matrix.Translation((-centre.x, -centre.y, -low.z)))
    root['asset_path'] = 'assets/models/the_pen.glb'
    root['length_m'] = .145
    return root


def _alpha_material(bpy, name, color, rough):
    """Translucent surface helper; Cycles needs no blend mode, EEVEE does."""
    material = bpy.data.materials.new(name); material.use_nodes = True
    bsdf = material.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (*color, 1.)
    bsdf.inputs['Roughness'].default_value = rough
    for attribute, value in (('surface_render_method', 'DITHERED'), ('blend_method', 'BLEND')):
        try:
            setattr(material, attribute, value)
        except Exception:
            pass
    return material


def _alpha_surface(material, bsdf, alpha_socket):
    """Mix with a Transparent BSDF instead of using Principled's Alpha.

    Feeding Alpha leaves the surface blocking shadow rays, which turns a film of
    pigment into a black rectangle on whatever is behind it.
    """
    nodes = material.node_tree.nodes; links = material.node_tree.links
    output = [node for node in nodes if node.type == 'OUTPUT_MATERIAL'][0]
    for link in list(output.inputs['Surface'].links):
        links.remove(link)
    clear = nodes.new('ShaderNodeBsdfTransparent')
    mix = nodes.new('ShaderNodeMixShader')
    links.new(mix.inputs[0], alpha_socket)
    links.new(mix.inputs[1], clear.outputs[0])
    links.new(mix.inputs[2], bsdf.outputs[0])
    links.new(output.inputs['Surface'], mix.outputs[0])
    return mix


def _chalk_material(bpy, name, color, dust=.42, value_spread=.22, bump=.30):
    """Pigment that skips and fades like pressed chalk instead of flat paint."""
    material = _alpha_material(bpy, name, color, .94)
    nodes = material.node_tree.nodes; links = material.node_tree.links
    bsdf = nodes['Principled BSDF']
    set_shader_input(bsdf, 'Specular IOR Level', 0.02)
    coord = nodes.new('ShaderNodeTexCoord')
    coverage = nodes.new('ShaderNodeTexNoise')
    coverage.inputs['Scale'].default_value = 64.
    coverage.inputs['Detail'].default_value = 3.
    coverage.inputs['Roughness'].default_value = .58
    links.new(coverage.inputs['Vector'], coord.outputs['Object'])
    ramp = nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = .36; ramp.color_ramp.elements[0].color = (0., 0., 0., 1.)
    ramp.color_ramp.elements[1].position = .64; ramp.color_ramp.elements[1].color = (1., 1., 1., 1.)
    links.new(ramp.inputs['Fac'], coverage.outputs['Fac'])
    coarse = nodes.new('ShaderNodeMath'); coarse.operation = 'MULTIPLY_ADD'
    coarse.inputs[1].default_value = 1. - dust; coarse.inputs[2].default_value = dust
    links.new(coarse.inputs[0], ramp.outputs['Color'])
    grain = nodes.new('ShaderNodeTexNoise')
    grain.inputs['Scale'].default_value = 520.
    grain.inputs['Detail'].default_value = 4.
    grain.inputs['Roughness'].default_value = .5
    links.new(grain.inputs['Vector'], coord.outputs['Object'])
    speckle = nodes.new('ShaderNodeValToRGB')
    speckle.color_ramp.elements[0].position = .28; speckle.color_ramp.elements[0].color = (0., 0., 0., 1.)
    speckle.color_ramp.elements[1].position = .58; speckle.color_ramp.elements[1].color = (1., 1., 1., 1.)
    links.new(speckle.inputs['Fac'], grain.outputs['Fac'])
    lift = nodes.new('ShaderNodeMath'); lift.operation = 'MULTIPLY_ADD'
    lift.inputs[1].default_value = .55; lift.inputs[2].default_value = .45
    links.new(lift.inputs[0], speckle.outputs['Color'])
    alpha = nodes.new('ShaderNodeMath'); alpha.operation = 'MULTIPLY'
    links.new(alpha.inputs[0], coarse.outputs['Value']); links.new(alpha.inputs[1], lift.outputs['Value'])
    _alpha_surface(material, bsdf, alpha.outputs['Value'])
    tone = nodes.new('ShaderNodeMixRGB'); tone.blend_type = 'MIX'
    tone.inputs['Color1'].default_value = (*color, 1.)
    tone.inputs['Color2'].default_value = (*(c * (1. - value_spread) for c in color), 1.)
    links.new(tone.inputs['Fac'], coverage.outputs['Fac'])
    links.new(bsdf.inputs['Base Color'], tone.outputs['Color'])
    if bump > 0.:
        relief = nodes.new('ShaderNodeBump')
        relief.inputs['Strength'].default_value = bump
        relief.inputs['Distance'].default_value = .00008
        links.new(relief.inputs['Height'], grain.outputs['Fac'])
        links.new(bsdf.inputs['Normal'], relief.outputs['Normal'])
    return material


def _chalk_halo_material(bpy, name, color, strength=.13):
    """Loose powder hugging a mark: wide, ragged and almost transparent."""
    material = _alpha_material(bpy, name, color, .96)
    nodes = material.node_tree.nodes; links = material.node_tree.links
    bsdf = nodes['Principled BSDF']
    set_shader_input(bsdf, 'Specular IOR Level', 0.02)
    coord = nodes.new('ShaderNodeTexCoord')
    noise = nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = 110.
    noise.inputs['Detail'].default_value = 4.
    noise.inputs['Roughness'].default_value = .62
    links.new(noise.inputs['Vector'], coord.outputs['Object'])
    ramp = nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = .30; ramp.color_ramp.elements[0].color = (0., 0., 0., 1.)
    ramp.color_ramp.elements[1].position = .62; ramp.color_ramp.elements[1].color = (1., 1., 1., 1.)
    links.new(ramp.inputs['Fac'], noise.outputs['Fac'])
    level = nodes.new('ShaderNodeMath'); level.operation = 'MULTIPLY'
    level.inputs[1].default_value = strength
    links.new(level.inputs[0], ramp.outputs['Color'])
    _alpha_surface(material, bsdf, level.outputs['Value'])
    return material


def _residue_material(bpy, name, color):
    """Ghost of erased writing: horizontal wipes plus uneven haze."""
    material = _alpha_material(bpy, name, color, .96)
    nodes = material.node_tree.nodes; links = material.node_tree.links
    bsdf = nodes['Principled BSDF']
    coord = nodes.new('ShaderNodeTexCoord')
    wipe_coord = nodes.new('ShaderNodeMapping')
    wipe_coord.inputs['Scale'].default_value = (2.2, 1., 17.)
    links.new(wipe_coord.inputs['Vector'], coord.outputs['Object'])
    wipe = nodes.new('ShaderNodeTexNoise')
    wipe.inputs['Scale'].default_value = 4.5
    wipe.inputs['Detail'].default_value = 3.
    wipe.inputs['Roughness'].default_value = .6
    links.new(wipe.inputs['Vector'], wipe_coord.outputs['Vector'])
    streak = nodes.new('ShaderNodeValToRGB')
    streak.color_ramp.elements[0].position = .44; streak.color_ramp.elements[0].color = (0., 0., 0., 1.)
    streak.color_ramp.elements[1].position = .78; streak.color_ramp.elements[1].color = (1., 1., 1., 1.)
    links.new(streak.inputs['Fac'], wipe.outputs['Fac'])
    haze = nodes.new('ShaderNodeTexNoise')
    haze.inputs['Scale'].default_value = 1.6
    haze.inputs['Detail'].default_value = 4.
    links.new(haze.inputs['Vector'], coord.outputs['Object'])
    veil = nodes.new('ShaderNodeValToRGB')
    veil.color_ramp.elements[0].position = .40; veil.color_ramp.elements[0].color = (.1, .1, .1, 1.)
    veil.color_ramp.elements[1].position = .72; veil.color_ramp.elements[1].color = (.55, .55, .55, 1.)
    links.new(veil.inputs['Fac'], haze.outputs['Fac'])
    mix = nodes.new('ShaderNodeMath'); mix.operation = 'MULTIPLY'
    links.new(mix.inputs[0], streak.outputs['Color']); links.new(mix.inputs[1], veil.outputs['Color'])
    strength = nodes.new('ShaderNodeMath'); strength.operation = 'MULTIPLY'
    strength.inputs[1].default_value = .085
    links.new(strength.inputs[0], mix.outputs['Value'])
    _alpha_surface(material, bsdf, strength.outputs['Value'])
    return material


# ------------------------------------------------------------------- meshes


def _cube_mesh(bpy, name, size):
    """A real-world-sized cube mesh, so Object texture coordinates stay isotropic."""
    x, y, z = (value * .5 for value in size)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(-x, -y, -z), (x, -y, -z), (x, y, -z), (-x, y, -z),
                      (-x, -y, z), (x, -y, z), (x, y, z), (-x, y, z)], [],
                     [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
                      (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)])
    mesh.update()
    return mesh


def _tube_mesh(bpy, name, radius, length, segments=48):
    import bmesh
    mesh = bpy.data.meshes.new(name); bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments,
                          radius1=radius, radius2=radius, depth=length)
    bm.to_mesh(mesh); bm.free(); mesh.update()
    return mesh


def _cone_mesh(bpy, name, radius1, radius2, length, segments=48):
    import bmesh
    mesh = bpy.data.meshes.new(name); bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments,
                          radius1=radius1, radius2=radius2, depth=length)
    bm.to_mesh(mesh); bm.free(); mesh.update()
    return mesh


def _sphere_mesh(bpy, name, radius, segments=64, rings=40):
    import bmesh
    mesh = bpy.data.meshes.new(name); bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=rings, radius=radius)
    bm.to_mesh(mesh); bm.free(); mesh.update()
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    return mesh


# ---------------------------------------------------------- hand-written chalk
# Each glyph is a set of monoline strokes on a 0..1 cap-height grid. Stroke
# geometry and pigment are what make the board read as chalk rather than as a
# font: see ``_chalk_stroke``.
def _arc(cx, cy, rx, ry, a0, a1, steps=14):
    return [(cx + rx * math.cos(math.radians(a0 + (a1 - a0) * i / steps)),
             cy + ry * math.sin(math.radians(a0 + (a1 - a0) * i / steps)))
            for i in range(steps + 1)]


def _bez(p0, p1, p2, steps=10):
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1])
            for t in (i / steps for i in range(steps + 1))]


_GLYPHS = {
    'A': (.62, [[(0, 0), (.31, 1), (.62, 0)], [(.13, .34), (.49, .34)]]),
    'B': (.54, [[(0, 0), (0, 1)],
                [(0, 1), (.22, 1)] + _arc(.24, .78, .24, .22, 90, -90) + [(0, .56)],
                [(0, .56), (.26, .56)] + _arc(.28, .28, .26, .28, 90, -90) + [(0, 0)]]),
    'C': (.56, [_arc(.30, .50, .28, .50, 56, 304, 20)]),
    'D': (.56, [[(0, 0), (0, 1)], [(0, 1), (.20, 1)] + _arc(.22, .50, .32, .50, 90, -90, 20) + [(0, 0)]]),
    'E': (.50, [[(0, 0), (0, 1)], [(0, 1), (.47, 1)], [(0, .55), (.38, .55)], [(0, 0), (.47, 0)]]),
    'F': (.48, [[(0, 0), (0, 1)], [(0, 1), (.45, 1)], [(0, .56), (.36, .56)]]),
    'H': (.54, [[(0, 0), (0, 1)], [(.52, 0), (.52, 1)], [(0, .52), (.52, .52)]]),
    'I': (.11, [[(.05, 0), (.05, 1)]]),
    'K': (.52, [[(0, 0), (0, 1)], [(.44, .58), (0, .26)], [(.14, .36), (.46, 0)]]),
    'L': (.48, [[(0, 1), (0, 0), (.45, 0)]]),
    'M': (.68, [[(0, 0), (0, 1), (.34, .40), (.68, 1), (.68, 0)]]),
    'N': (.54, [[(0, 0), (0, 1), (.52, 0), (.52, 1)]]),
    'O': (.58, [_arc(.29, .50, .28, .50, 0, 360, 28)]),
    'P': (.48, [[(0, 0), (0, 1)], [(0, 1), (.22, 1)] + _arc(.23, .76, .22, .24, 90, -90) + [(0, .52)]]),
    'S': (.50, [[(.48, .86), (.40, 1), (.16, 1), (.04, .88), (.03, .74), (.12, .60),
                 (.36, .53), (.46, .40), (.46, .16), (.34, 0), (.10, 0), (0, .14)]]),
    'T': (.52, [[(0, 1), (.52, 1)], [(.26, 1), (.26, 0)]]),
    'U': (.52, [[(0, 1), (0, .16)] + _arc(.26, .16, .26, .16, 180, 360, 16) + [(.52, 1)]]),
    'V': (.52, [[(0, 1), (.26, 0), (.52, 1)]]),
    'Y': (.56, [[(0, 1), (.27, .44), (.54, 1)], [(.27, .44), (.27, 0)]]),
    '0': (.50, [_arc(.25, .50, .23, .50, 0, 360, 26)]),
    '1': (.34, [[(.06, .78), (.22, 1), (.22, 0)]]),
    '2': (.50, [[(0, .80), (.06, .94), (.20, 1), (.34, .96), (.44, .82), (.38, .64),
                 (.04, .08), (0, .02), (.46, .02)]]),
    '4': (.56, [[(.40, 0), (.40, 1), (.02, .28), (.56, .28)]]),
    '5': (.48, [[(.44, 1), (.09, 1), (.07, .62), (.24, .66), (.40, .52), (.42, .30),
                 (.30, .10), (.12, .06), (0, .14)]]),
    '8': (.50, [_arc(.25, .76, .21, .24, 0, 360, 18), _arc(.25, .26, .23, .26, 0, 360, 20)]),
    '=': (.44, [[(0, .38), (.42, .38)], [(0, .66), (.42, .66)]]),
    '/': (.46, [[(.04, 0), (.40, 1)]]),
    '+': (.44, [[(0, .50), (.42, .50)], [(.21, .29), (.21, .71)]]),
    '.': (.10, [_arc(.05, .06, .045, .05, 0, 360, 10)]),
    '·': (.30, [[(.02, .44), (.16, .44)]]),
    'a': (.50, [_arc(.25, .34, .24, .34, 24, 336, 18) + [(.49, .66)], [(.49, .68), (.49, 0)]]),
    'g': (.50, [_arc(.25, .34, .24, .34, 24, 336, 18) + [(.49, .66)],
                [(.49, .66), (.49, -.20)] + _arc(.36, -.20, .13, .12, 0, -180, 8)]),
    'k': (.50, [[(0, 0), (0, 1)], [(.40, .56), (0, .28)], [(.13, .38), (.44, 0)]]),
    'm': (.58, [[(0, 0), (0, .54)],
                [(0, .54)] + _bez((0, .54), (.15, .71), (.29, .54)) + [(.29, 0)],
                [(.29, .54)] + _bez((.29, .54), (.44, .71), (.58, .54)) + [(.58, 0)]]),
    's': (.44, [[(.42, .62), (.34, .72), (.14, .72), (.04, .64), (.06, .52), (.18, .44),
                 (.36, .36), (.40, .24), (.30, .14), (.08, .14), (0, .22)]]),
    'v': (.48, [[(0, .68), (.23, 0), (.46, .68)]]),
}


def _chalk_stroke(bpy, scene, points, width, material, bow=.0, seed=0., depth=1.2145):
    """One chalk mark, built as a flat ribbon lying on the slate.

    A round bevelled curve reads as coloured wire on a blackboard: its top and
    sides catch the key light differently. Real chalk is a matte deposit with a
    constant surface normal, so the mark is a strip of quads and all the life
    comes from width drift, bow and the granular pigment shader.
    """
    count = len(points)
    verts = []; faces = []
    for index, (px, pz) in enumerate(points):
        t = index / (count - 1) if count > 1 else 0.
        wobble = bow * math.sin(t * math.pi * 1.35 + seed)
        press = 1. + .16 * math.sin(t * math.pi * 2.4 + seed * 1.7)
        press *= 1. - .30 * max(0., t - .88) / .12 - .30 * max(0., .12 - t) / .12
        pz = pz + wobble
        if count > 1:
            previous = points[max(0, index - 1)]; following = points[min(count - 1, index + 1)]
            tangent = (following[0] - previous[0], following[1] - previous[1])
        else:
            tangent = (1., 0.)
        length = math.hypot(*tangent) or 1.
        normal = (-tangent[1] / length, tangent[0] / length)
        half = width * .5 * max(.35, press)
        verts.append((px + normal[0] * half, 0., pz + normal[1] * half))
        verts.append((px - normal[0] * half, 0., pz - normal[1] * half))
    for index in range(count - 1):
        base = index * 2
        faces.append((base, base + 1, base + 3, base + 2))
    mesh = bpy.data.meshes.new('Chalk mark')
    mesh.from_pydata(verts, [], faces); mesh.update()
    mesh.materials.append(material)
    obj = bpy.data.objects.new('Chalk mark', mesh)
    obj.location.y = depth
    scene.collection.objects.link(obj)
    return obj


def _chalk_text(bpy, scene, text, x, z, cap, materials, seed=1, slant=.07, drift=.012,
                jitter=.020, tracking=.17, width=.092, halo=None, halo_scale=2.1):
    """Hand-lettered line: per-glyph drift, rotation, weight and shear."""
    rng = random.Random(seed)
    pen = 0.
    for character in text:
        if character == ' ':
            pen += cap * .30
            continue
        advance, strokes = _GLYPHS[character]
        offset_x = rng.uniform(-jitter, jitter) * cap
        offset_z = rng.uniform(-jitter, jitter) * cap * .7
        rotate = math.radians(rng.uniform(-2.4, 2.4))
        scale = rng.uniform(.94, 1.05)
        weight = cap * width * rng.uniform(.90, 1.12)
        material = materials[rng.randrange(len(materials))]
        centre_x, centre_z = advance * .5, .40
        cos_r, sin_r = math.cos(rotate), math.sin(rotate)
        for stroke in strokes:
            points = []
            for u, v in stroke:
                du = (u - centre_x) * scale; dv = (v - centre_z) * scale
                ru = du * cos_r - dv * sin_r + centre_x
                rv = du * sin_r + dv * cos_r + centre_z
                ru += offset_x / cap + slant * rv
                rv += offset_z / cap
                point_x = x + pen + ru * cap
                points.append((point_x, z + rv * cap + drift * (point_x - x)))
            if halo is not None:
                _chalk_stroke(bpy, scene, points, weight * halo_scale, halo,
                              bow=cap * .014, seed=rng.random() * 6., depth=1.2171)
            _chalk_stroke(bpy, scene, points, weight, material, bow=cap * .014, seed=rng.random() * 6.)
        pen += (advance + tracking) * cap
    return x + pen


def _chalk_rule(bpy, scene, x0, x1, z, material, cap, seed=2):
    points = []
    for index in range(13):
        t = index / 12
        points.append((x0 + (x1 - x0) * t, z + cap * .05 * math.sin(t * math.pi)))
    return _chalk_stroke(bpy, scene, points, cap * .034, material, bow=cap * .01, seed=seed)


# -------------------------------------------------------------------- set


def build_room(bpy, data):
    """Build the lab, the block and the bob.

    Returns ``(objects, rig)``: ``objects`` maps the simulation's body ids to the
    empties the renderer keyframes, ``rig`` carries the thread that has to be
    aimed at the bob every frame and the pivot it hangs from.
    """
    from mathutils import Vector
    scene = bpy.context.scene

    def mat(name, color, **kw):
        return _material(bpy, name, color, **kw)

    bench = _bench_top(bpy, 'Dark lino bench top', (.043, .050, .047), rough=.44)
    frame_wood = _wood(bpy, 'Beech bench frame', (.46, .30, .145), (.22, .125, .052))
    pine = _wood(bpy, 'Pine block', (.500, .340, .165), (.275, .175, .078),
                 scale=(1.1, 6., 18.), rough=.54, coat=.10)
    wall = mat('Pale mineral plaster', (.610, .585, .520), rough=.80,
               bump=.045, bump_scale=210., bump_distance=.00035)
    floor = mat('Grey terrazzo', (.255, .245, .222), rough=.55, bump=.05,
                bump_scale=140., speckle=64., speckle_color=(.125, .120, .112))
    steel = mat('Brushed steel', (.520, .530, .545), rough=.26, metallic=1.,
                bump=.012, bump_scale=320., bump_distance=.00006)
    chrome = mat('Polished chrome', (.640, .650, .665), rough=.13, metallic=1.)
    cast_iron = mat('Cast iron stand foot', (.052, .055, .058), rough=.52, metallic=.55,
                    bump=.10, bump_scale=180., bump_distance=.0003)
    # Satin, not mirror: at 48 mm across, a mirror finish gives one blown white
    # blob where the key light lands and no readable roundness anywhere else.
    steel_ball = mat('Satin steel bob', (.470, .480, .505), rough=.30, metallic=1.,
                     bump=.006, bump_scale=460., bump_distance=.00004)
    brass = mat('Tarnished brass', (.400, .285, .115), rough=.40, metallic=1.,
                bump=.03, bump_scale=260., bump_distance=.00012)
    # A medium grey, not black: the thread spends most of the clip in front of
    # the slate board (dark) and the last third in front of the bench (light),
    # and a mid tone is the only value that separates from both at 1 px wide.
    thread = mat('Pendulum thread', (.360, .345, .320), rough=.82)
    paper = mat('Worksheet paper', (.545, .520, .450), rough=.78,
                bump=.02, bump_scale=520., bump_distance=.00008)
    enamel = mat('Enamel tray', (.245, .300, .275), rough=.42, coat=.20)
    watch_case = mat('Black watch case', (.030, .031, .034), rough=.34, coat=.20)
    black_ink = mat('Printed ink', (.035, .036, .040), rough=.62)
    white_face = mat('Stopwatch dial', (.860, .855, .820), rough=.36, coat=.25)
    def cube(name, loc, size, material, parent=None, bevel=.003, rotation=None):
        obj = bpy.data.objects.new(name, _cube_mesh(bpy, name, size))
        scene.collection.objects.link(obj); obj.location = loc; obj.data.materials.append(material)
        if bevel:
            modifier = obj.modifiers.new('Soft manufactured edges', 'BEVEL')
            modifier.width = bevel; modifier.segments = 5
            obj.modifiers.new('Weighted normals', 'WEIGHTED_NORMAL')
        if rotation is not None:
            obj.rotation_euler = rotation
        if parent:
            obj.parent = parent
        return obj

    def rod(name, start, end, radius, material, segments=32):
        """Cylinder spanning two points; used for the stand, arm and thread."""
        begin = Vector(start); finish = Vector(end); direction = finish - begin
        obj = bpy.data.objects.new(name, _tube_mesh(bpy, name, radius, direction.length, segments))
        scene.collection.objects.link(obj); obj.data.materials.append(material)
        obj.location = (begin + finish) / 2
        obj.rotation_mode = 'QUATERNION'
        obj.rotation_quaternion = direction.to_track_quat('Z', 'Y')
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
        return obj

    def text(name, string, loc, size, material, parent=None, rotation=(math.pi / 2, 0, 0)):
        curve = bpy.data.curves.new(name, 'FONT'); curve.body = string; curve.size = size
        curve.align_x = 'CENTER'; curve.extrude = .0001
        obj = bpy.data.objects.new(name, curve); scene.collection.objects.link(obj)
        obj.location = loc; obj.rotation_euler = rotation
        curve.materials.append(material)
        if parent:
            obj.parent = parent
        return obj

    # --- room shell -----------------------------------------------------
    cube('Lab floor', (0, 0, -.06), (8, 5, .12), floor)
    cube('Plaster wall', (0, 1.35, 1.5), (8, .12, 3), wall)
    # A low upstand where the bench meets the wall: every school lab bench has
    # one, and it gives the slate board a shadow line to sit on.
    cube('Bench upstand', (-.15, 1.272, .782), (2.44, .026, .044), frame_wood, bevel=.003)

    # --- bench ----------------------------------------------------------
    # The top slab's upper face is exactly TABLE_Z: it is the surface the
    # collision slab uses, so the block never floats or sinks on screen.
    cube('Bench top', (0, 0, BENCH_TOP - BENCH_SIZE[2] / 2), BENCH_SIZE, bench, bevel=.004)
    cube('Bench apron', (0, 0, BENCH_TOP - BENCH_SIZE[2] - .035), (2.5, .92, .07), frame_wood, bevel=.004)
    for x in (-1.12, 1.12):
        for y in (-.36, .36):
            cube('Square bench leg', (x, y, (BENCH_TOP - .11) / 2), (.055, .055, BENCH_TOP - .11), frame_wood)
    for y in (-.36, .36):
        cube('Bench stretcher', (0, y, .10), (2.20, .035, .055), frame_wood, bevel=.002)

    # --- local blackboard asset (without the pinned note) ---------------
    _place_blackboard_asset(bpy)

    # --- retort stand ---------------------------------------------------
    cube('Retort stand foot', (STAND[0], STAND[1], BENCH_TOP + .008), (.26, .16, .016),
         cast_iron, bevel=.006)
    for dx, dy in ((-.085, -.055), (.085, -.055), (-.085, .055), (.085, .055)):
        rod('Foot pad', (STAND[0] + dx, STAND[1] + dy, BENCH_TOP),
            (STAND[0] + dx, STAND[1] + dy, BENCH_TOP + .004), .012, _material(
                bpy, 'Rubber foot', (.030, .030, .032), rough=.92))
    rod('Retort rod', (STAND[0], STAND[1], BENCH_TOP + .012),
        (STAND[0], STAND[1], STAND_TOP), .0085, chrome)
    cube('Boss head', (STAND[0], STAND[1], PIVOT[2]), (.040, .032, .046), cast_iron, bevel=.005)
    rod('Boss screw', (STAND[0] + .023, STAND[1], PIVOT[2]),
        (STAND[0] + .043, STAND[1], PIVOT[2]), .0075, brass, segments=12)
    # Cross-arm: from the boss head to the pivot, so the drawn thread starts
    # exactly where the solver's point constraint is anchored.
    rod('Cross arm', (STAND[0], STAND[1], PIVOT[2]), PIVOT, .0045, chrome)
    cube('Arm clamp', (PIVOT[0], PIVOT[1], PIVOT[2]), (.026, .026, .024), cast_iron, bevel=.003)

    # --- bench dressing (kept clear of the block's lane) ----------------
    # The weights tray sits beside the retort stand, where a lab keeps it, not
    # on the left half of the bench: that half is the slider's runway now, and
    # anything standing there turns into a pale shape the block has to slide
    # through.
    tray_x, tray_y = .26, .285
    cube('Weights tray', (tray_x, tray_y, BENCH_TOP + .012), (.24, .15, .024), enamel, bevel=.005)
    for index, (dx, dy) in enumerate(((-.07, -.035), (0, -.035), (.07, -.035),
                                      (-.035, .035), (.035, .035))):
        rod(f'Hooked weight {index}', (tray_x + dx, tray_y + dy, BENCH_TOP + .024),
            (tray_x + dx, tray_y + dy, BENCH_TOP + .078), .0165, brass)
        rod(f'Weight hook {index}', (tray_x + dx, tray_y + dy, BENCH_TOP + .078),
            (tray_x + dx, tray_y + dy, BENCH_TOP + .094), .0035, steel, segments=8)
    _place_pen_asset(bpy)
    rod('Metre rule', (.60, -.17, BENCH_TOP + .006), (.60, .17, BENCH_TOP + .006), .011, frame_wood)
    for index in range(20):
        cube('Ruler tick', (.60, -.15 + index * .016, BENCH_TOP + .0135),
             (.028 if index % 5 == 0 else .015, .0012, .0006), black_ink, bevel=0)
    # Stopwatch: body, dial, bezel and crown, lying face up on the bench.
    rod('Stopwatch case', (.16, -.175, BENCH_TOP + .006), (.16, -.175, BENCH_TOP + .018), .034, watch_case)
    rod('Stopwatch dial', (.16, -.175, BENCH_TOP + .0185), (.16, -.175, BENCH_TOP + .0195), .029, white_face)
    rod('Stopwatch crown', (.16, -.175, BENCH_TOP + .024), (.16, -.175, BENCH_TOP + .035), .006, watch_case, 12)
    for index in range(12):
        angle = index * math.pi / 6
        cube('Stopwatch tick', (.16 + .024 * math.sin(angle), -.175 + .024 * math.cos(angle),
                                BENCH_TOP + .0202), (.0018, .0045, .0004), black_ink,
             bevel=0, rotation=(0, 0, -angle))
    # --- the two rigid bodies -------------------------------------------
    objects = {}
    box_root = bpy.data.objects.new('box', None); scene.collection.objects.link(box_root)
    objects['box'] = box_root
    width, depth, height = BOX_SIZE
    cube('Pine block', (0, 0, 0), (width, depth, height), pine, box_root, bevel=.0025)
    cube('Block end grain', (-width / 2 + .0002, 0, 0), (.0004, depth * .98, height * .96),
         frame_wood, box_root, bevel=0)
    # A specimen tag, not a shipping label: the slider is 12 cm long, so the
    # sticker is 4 cm wide and sits low on the face where a lab would chalk it.
    cube('Block label', (0, -depth / 2 - .0004, -.010), (width * .30, .0005, height * .20),
         paper, box_root, bevel=.0003)
    text('Label lettering', 'WOOD  B', (0, -depth / 2 - .0007, -.010), .0085, black_ink, box_root)

    bob_root = bpy.data.objects.new('bob', None); scene.collection.objects.link(bob_root)
    objects['bob'] = bob_root
    ball = bpy.data.objects.new('Steel bob', _sphere_mesh(bpy, 'Steel bob', BOB_RADIUS))
    scene.collection.objects.link(ball); ball.parent = bob_root; ball.data.materials.append(steel_ball)

    # The thread and its eyelet live in the rod's frame, not the ball's: a real
    # bob turns freely on a swivel, so the eyelet must not whirl with the spin
    # the contact friction gives the ball.
    thread_obj = rod('Pendulum thread', PIVOT, (0, 0, PIVOT[2] - PENDULUM_LENGTH), .0007,
                     thread, segments=8)
    eyelet = bpy.data.objects.new('Eyelet', _tube_mesh(bpy, 'Eyelet', .0055, .012, 10))
    scene.collection.objects.link(eyelet); eyelet.data.materials.append(steel)
    eyelet.parent = thread_obj; eyelet.location = (0, 0, PENDULUM_LENGTH / 2 - BOB_RADIUS - .001)
    return objects, dict(thread=thread_obj, pivot=Vector(PIVOT), thread_length=PENDULUM_LENGTH)


def configure_lighting(bpy, scene):
    """Cool window key from the front left, warm fill, and a wash on the board."""
    from mathutils import Vector
    world = bpy.data.worlds.new('Lab ambient'); world.use_nodes = True
    background = world.node_tree.nodes['Background']
    background.inputs['Color'].default_value = (.145, .155, .170, 1.)
    background.inputs['Strength'].default_value = 1.0
    scene.world = world
    rig = [('Window key', (-1.35, -1.80, 2.95), 155., 2.4, (1., .962, .905), (-.10, 0., .92)),
           ('Soft fill', (1.90, -1.20, 2.10), 34., 2.2, (.94, .965, 1.), (.10, 0., .92)),
           ('Board wash', (-.30, .60, 2.10), 26., 2.2, (1., .99, .962), (-.20, 1.25, 1.20)),
           ('Bench kick', (.55, -1.10, 1.05), 12., 1.2, (.98, .97, .95), (-.05, 0., .86))]
    for name, location, power, size, color, target in rig:
        bpy.ops.object.light_add(type='AREA', location=location)
        lamp = bpy.context.object; lamp.name = f'{name} light'
        lamp.data.energy = power; lamp.data.shape = 'DISK'; lamp.data.size = size
        lamp.data.color = color
        lamp.rotation_euler = (Vector(target) - lamp.location).to_track_quat('-Z', 'Y').to_euler()

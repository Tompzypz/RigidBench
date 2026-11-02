"""A small machined laboratory instrument on an oak workbench; appearance only."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math
from pathlib import Path
import runtime_support
from scene_geometry import TABLE_HEIGHT, PIVOT_HEIGHT, PIVOTS, BOB_RADIUS, LENGTH
# newtons_cradle owns these material helpers; twin_pendulum reuses them.
import sys as _cross_sys
from pathlib import Path as _CrossPath
_NEWTONS_APPEARANCE = _CrossPath(__file__).resolve().parents[2] / 'newtons_cradle' / 'appearance'
if _NEWTONS_APPEARANCE.is_dir() and str(_NEWTONS_APPEARANCE) not in _cross_sys.path:
    _cross_sys.path.insert(0, str(_NEWTONS_APPEARANCE))
from look_newtons_cradle import material, textured_material, pbr_wood, box

APPEARANCE_VERSION = 1


def rod(bpy, name, start, end, radius, mat, vertices=32):
    from mathutils import Vector
    a, b = Vector(start), Vector(end)
    delta = b - a
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=1, location=(a + b) / 2)
    obj = bpy.context.object
    obj.name = name
    obj.scale.z = delta.length
    obj.rotation_mode = 'QUATERNION'
    obj.rotation_quaternion = delta.to_track_quat('Z', 'Y')
    obj.data.materials.append(mat)
    for face in obj.data.polygons:
        face.use_smooth = True
    bevel = obj.modifiers.new('Machined edge radius', 'BEVEL')
    bevel.width = min(radius * .12, .0006)
    bevel.segments = 3
    return obj


def text(bpy, name, body, location, size, mat, rotation=(math.pi / 2, 0, 0)):
    bpy.ops.object.text_add(location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.data.body = body
    obj.data.size = size
    obj.data.extrude = .000015
    obj.data.materials.append(mat)
    return obj


def build_environment(bpy, scene):
    top = TABLE_HEIGHT
    oak = pbr_wood(bpy, 'Workbench / scanned oak')
    black = textured_material(bpy, 'Graphite powder coat', (.032, .042, .046), roughness=.38, metal=.55, scale=480, bump_distance=.000018)
    steel = textured_material(bpy, 'Satin stainless steel', (.40, .46, .50), roughness=.23, metal=1, scale=1200, bump_distance=.000003)
    brass = textured_material(bpy, 'Warm machined brass', (.48, .30, .10), roughness=.25, metal=.88, scale=800, bump_distance=.000006)
    rubber = material(bpy, 'Soft black rubber', (.012, .015, .016), roughness=.74)
    paint = material(bpy, 'Warm lab wall', (.59, .62, .60), roughness=.86)
    lettering = material(bpy, 'Engraved pale metal', (.54, .59, .59), metal=.65, roughness=.36)
    box(bpy, 'Solid oak worktop', [0, .13, top - .028], [2.5, 1.15, .056], oak, bevel=.009)
    cabinet = material(bpy, 'Desaturated blue cabinet enamel', (.12, .20, .22), roughness=.42)
    for x in (-.91, .91):
        box(bpy, 'Bench cabinet', [x, .20, .35], [.55, .70, .70], cabinet, bevel=.009)
        for z in (.22, .45, .65):
            box(bpy, 'Cabinet drawer seam', [x, -.155, z], [.49, .004, .002], black, bevel=.0005)
            rod(bpy, 'Drawer handle', [x - .09, -.178, z - .048], [x + .09, -.178, z - .048], .006, steel)
    box(bpy, 'Back laboratory wall', [0, 1.35, 1.55], [5., .10, 3.1], paint, bevel=.005)
    box(bpy, 'Wall skirting', [0, 1.285, .07], [5., .025, .14], cabinet, bevel=.003)
    floor = textured_material(bpy, 'Matte stone floor', (.20, .22, .22), roughness=.78, scale=55, bump_distance=.0002)
    box(bpy, 'Floor', [0, 0, -.035], [6, 6, .07], floor, bevel=.003)
    # The unmarked board, shelves and instruments establish a real laboratory.
    board = textured_material(bpy, 'Slate green board', (.035, .088, .075), roughness=.91, scale=140, bump_distance=.00003)
    box(bpy, 'Board oak frame', [-.18, 1.275, 1.52], [1.50, .035, .74], oak, bevel=.008)
    box(bpy, 'Clean slate board', [-.18, 1.251, 1.52], [1.45, .012, .69], board, bevel=.002)
    rod(bpy, 'Chalk ledge', [-.90, 1.21, 1.16], [.54, 1.21, 1.16], .011, steel)
    box(bpy, 'Rear wall shelf', [.94, 1.14, 1.27], [.56, .23, .025], oak, bevel=.004)
    for x in (.76, 1.10):
        rod(bpy, 'Shelf bracket', [x, 1.25, 1.13], [x, 1.03, 1.25], .008, black)
    ceramic = material(bpy, 'Porcelain', (.70, .73, .68), roughness=.27)
    for x, height in ((.82, .12), (1.02, .17)):
        rod(bpy, 'Sample jar', [x, 1.12, 1.29], [x, 1.12, 1.29 + height], .043, ceramic)
        rod(bpy, 'Sample lid', [x, 1.12, 1.29 + height], [x, 1.12, 1.30 + height], .045, black)
    paper = material(bpy, 'Notebook paper', (.70, .69, .59), roughness=.88)
    cover = textured_material(bpy, 'Notebook woven cover', (.11, .18, .19), roughness=.80, scale=600, bump_distance=.000025)
    box(bpy, 'Laboratory notebook cover', [.64, .25, top + .005], [.23, .28, .009], cover, bevel=.003)
    box(bpy, 'Laboratory notebook pages', [.64, .25, top + .013], [.218, .264, .012], paper, bevel=.001)
    box(bpy, 'Laboratory notebook upper cover', [.64, .25, top + .022], [.23, .28, .005], cover, bevel=.002)
    rod(bpy, 'Pencil', [.51, .13, top + .030], [.72, .16, top + .030], .0034, brass, vertices=6)
    # Low base and widely spaced supports stay outside every allowed swing.
    for x in (-.355, .355):
        for y in (-.11, .11):
            rod(bpy, 'Adjustable rubber foot', [x, y, top], [x, y, top + .010], .018, rubber)
    box(bpy, 'Instrument cast base', [0, 0, top + .025], [.85, .31, .036], black, bevel=.009)
    box(bpy, 'Brushed aluminium inset', [0, -.010, top + .044], [.80, .26, .003], steel, bevel=.004)
    for x in (-.375, .375):
        for y in (-.095, .095):
            rod(bpy, 'Stand mounting collar', [x, y, top + .046], [x, y, top + .064], .018, brass)
            rod(bpy, 'Stainless upright', [x, y, top + .060], [x, y, PIVOT_HEIGHT + .050], .008, steel)
        rod(bpy, 'Rounded top cross member', [x, -.095, PIVOT_HEIGHT + .050], [x, .095, PIVOT_HEIGHT + .050], .008, steel)
    for y in (-.095, .095):
        rod(bpy, 'Upper horizontal rail', [-.375, y, PIVOT_HEIGHT + .050], [.375, y, PIVOT_HEIGHT + .050], .008, steel)
    for i, pivot in enumerate(PIVOTS):
        x, _, z = pivot
        box(bpy, f'Pivot bridge {i}', [x, 0, z + .050], [.026, .20, .018], black, bevel=.003)
        for y in (-.018, .018):
            box(bpy, f'Bearing lug {i}', [x, y, z + .014], [.020, .009, .041], brass, bevel=.003)
        rod(bpy, f'Pivot pin {i}', [x, -.027, z], [x, .027, z], .0035, steel)
        for y in (-.030, .030):
            rod(bpy, f'Pivot pin nut {i}', [x, y - .002, z], [x, y + .002, z], .0058, brass, vertices=6)
        # Permanent identity labels; no visual edits to indicate changed mass.
        text(bpy, f'Pivot identification {i}', 'A' if i == 0 else 'B', [x - .004, -.106, z + .044], .011, lettering)
    for x in (-.395, .395):
        for y in (-.12, .12):
            rod(bpy, 'Recessed base screw', [x, y, top + .045], [x, y, top + .048], .0045, black, vertices=6)
    # Engraved ruler and front maker's plate are physical surface details.
    for i in range(71):
        x = -.35 + i * .01
        length = .010 if i % 5 == 0 else .005
        box(bpy, 'Etched millimetre tick', [x, -.119 + length / 2, top + .0456], [.00045, length, .00008], black, bevel=0)
    box(bpy, 'Recessed nameplate', [0, -.1555, top + .025], [.24, .001, .023], brass, bevel=.002)
    text(bpy, 'Nameplate engraving', 'COUPLED PENDULUMS', [-.103, -.1562, top + .021], .012, black)
    # Neutral environment map supplies complex real reflections in the steel.
    world = bpy.data.worlds.new('Laboratory daylight')
    scene.world = world
    world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    bg = nodes.get('Background')
    bg.inputs['Strength'].default_value = .20
    hdr = runtime_support.ROOT / 'assets/polyhaven/newtons_cradle/wooden_lounge_2k.hdr'
    if hdr.exists():
        env = nodes.new('ShaderNodeTexEnvironment')
        env.image = bpy.data.images.load(str(hdr))
        links.new(env.outputs['Color'], bg.inputs['Color'])
    from mathutils import Vector
    for name, location, target, energy, size, color in (
        ('Large soft window', [-1.3, -.8, 2.3], [0, 0, 1.0], 85, 1.4, (.86, .93, 1.0)),
        ('Warm wall bounce', [.65, .65, 1.9], [0, 0, 1.0], 36, .9, (1.0, .86, .68)),
        ('Front reflection strip', [.3, -1.2, 1.8], [0, 0, 1.0], 24, .75, (1.0, .98, .93))):
        data = bpy.data.lights.new(name, 'AREA')
        data.energy, data.shape, data.size, data.color = energy, 'DISK', size, color
        obj = bpy.data.objects.new(name, data)
        scene.collection.objects.link(obj)
        obj.location = location
        obj.rotation_euler = (Vector(target) - obj.location).to_track_quat('-Z', 'Y').to_euler()
    return dict(steel=steel, brass=brass, black=black)


def make_pendulums(bpy, mats, first_frame):
    from mathutils import Vector
    balls, rods, moving = {}, {}, []
    for index, key in enumerate(('driver', 'receiver')):
        if not first_frame[key]['present']:
            continue
        bobmat = textured_material(bpy, key + ' polished steel', (.48, .53, .57), metal=1, roughness=.16, scale=1100, bump_distance=.000002)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=BOB_RADIUS)
        ball = bpy.context.object
        ball.name = key
        ball.data.materials.append(bobmat)
        for face in ball.data.polygons:
            face.use_smooth = True
        balls[key] = ball
        # A small threaded brass socket is rigidly attached to the spherical bob.
        boss = rod(bpy, key + ' threaded socket', [0, 0, BOB_RADIUS - .002], [0, 0, BOB_RADIUS + .006], .0042, mats['brass'])
        boss.parent = ball
        rods[key] = rod(bpy, key + ' suspension rod', PIVOTS[index],
                        Vector(first_frame[key]['location']) + Vector([0, 0, BOB_RADIUS]), .0011, mats['steel'])
        # A rotating hinge ring shares the pendulum's local upward direction.
        bpy.ops.mesh.primitive_torus_add(major_radius=.0042, minor_radius=.0012, major_segments=24, minor_segments=8,
                                        location=[0, 0, LENGTH], rotation=[math.pi / 2, 0, 0])
        eye = bpy.context.object
        eye.name = key + ' pivot eye'
        eye.data.materials.append(mats['brass'])
        eye.parent = ball
        moving.extend([ball, rods[key], boss, eye])
    return balls, rods, moving

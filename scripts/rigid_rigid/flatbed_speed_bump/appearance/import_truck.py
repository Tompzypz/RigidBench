"""Adapt the desktop CC-BY truck to the benchmark's chassis/deck rig.

The glb is a real-proportioned three-axle flatbed authored at 26.03 x 8.87 x
8.86 model units. It is *not* a 1:1 asset -- it is a real truck blown up to
roughly 3.4x life size, so every proportion is right and the absolute size is
not. This adapter therefore applies exactly one factor to it, ``scale``, on all
three axes::

    X = cfg.model_x(p.y)      Y = p.x * scale      Z = cfg.model_z(p.z)

``cfg.TRUCK_SCALE`` is that factor and ``cfg.model_x`` / ``cfg.model_z`` are the
same two functions the collision rig is built from, so the visible mesh and the
collider cannot disagree -- if the deck plank moves, the box the cargo rests on
moves with it. Nothing is stretched along a single axis: an earlier version
corbelled the 0.70 m between the model's sill and its bed into one band so the
deck could stay at 1.25 m, which is exactly what made the cab read as mounted on
stilts. The rig follows the model instead, so the deck sits at 0.737 m.

The one part that is not simply ``scale`` is the tyre: the rig models a single
wheel radius (``cfg.WHEEL_RADIUS``), which is the front tyre's 1.635 units times
``scale``. The front tyres therefore land exactly, and the narrower rear tandem
(1.489 units) is scaled up by 9.8 % so all six tyres can stand on the road. The
front axle is the one that strikes the bump, so the contact that matters is
exact.

Materials: the glb's paint map is a near-white panel sheet with rust along the
seams (see ``assets/models/flatbed_unity3d.glb`` image 0), and its paint
material is glTF ``roughness 0.0`` -- a mirror. The dark olive on the published
page is that mirror reflecting a dark environment, not a colour in the texture.
The tint below reproduces it by multiplying the map, so the grime survives, and
``PAINT_ROUGHNESS`` makes it read as paint rather than chrome.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
from pathlib import Path

import bpy
from mathutils import Vector

import scene_config as cfg

ASSET = _PCVE_ROOT / 'assets' / 'models' / 'flatbed_unity3d.glb'

# Multiplied into the paint map: a near-white base with baked rust streaks
# becomes the dark olive the published model shows, streaks and panel dirt
# intact.
PAINT_TINT = (0.30, 0.32, 0.20)
PAINT_ROUGHNESS = 0.34
WHEEL_ROUGHNESS = 0.52


def _bbox(points):
    lo = Vector(tuple(min(p[i] for p in points) for i in range(3)))
    hi = Vector(tuple(max(p[i] for p in points) for i in range(3)))
    return lo, hi, (lo + hi) * 0.5


def _tint_base_color(mat, tint) -> None:
    """Multiply ``mat``'s base-colour map by ``tint`` (the map is kept)."""
    if not mat or not mat.use_nodes:
        return
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf is None or not bsdf.inputs['Base Color'].is_linked:
        return
    source = bsdf.inputs['Base Color'].links[0].from_socket
    mix = nodes.new('ShaderNodeMix')
    mix.name = 'paint_tint'
    mix.data_type = 'RGBA'
    mix.blend_type = 'MULTIPLY'
    mix.clamp_factor = True
    sockets = {s.identifier: s for s in mix.inputs}
    factor = sockets.get('Factor_Float') or mix.inputs[0]
    factor.default_value = 1.0
    color_a = sockets.get('A_Color') or mix.inputs[6]
    color_b = sockets.get('B_Color') or mix.inputs[7]
    color_b.default_value = (tint[0], tint[1], tint[2], 1.0)
    result = next((s for s in mix.outputs if s.identifier == 'Result_Color'), mix.outputs[2])
    links.new(source, color_a)
    links.new(result, bsdf.inputs['Base Color'])


def build_truck(asset=None):
    source = Path(asset) if asset else ASSET
    if not source.is_file():
        raise FileNotFoundError(f"Required truck model not found: {source}")
    bpy.ops.import_scene.gltf(filepath=str(source))
    imported = list(bpy.context.selected_objects)
    bpy.context.view_layer.update()
    meshes = [o for o in imported if o.type == 'MESH']
    baked = [(o, [o.matrix_world @ v.co for v in o.data.vertices]) for o in meshes]
    for o in meshes:
        o.parent = None
        o.matrix_world.identity()
    for o in imported:
        if o.type != 'MESH':
            bpy.data.objects.remove(o, do_unlink=True)

    # --- wheel inventory: axle positions drive every later anchor ----------
    wheel_info = {}
    for obj, points in baked:
        if 'Wheel' in obj.name and points:
            lo, hi, centre = _bbox(points)
            wheel_info[obj.name] = (lo, hi, centre)
    front = [c.y for n, (_lo, _hi, c) in wheel_info.items() if 'F_Wheel' in n]
    rear = [c.y for n, (_lo, _hi, c) in wheel_info.items() if 'F_Wheel' not in n]
    if not front or not rear:
        raise RuntimeError('flatbed glb: expected front and rear wheels by name')

    scale = cfg.TRUCK_SCALE
    # The rig's axle spacing is ``scale`` times the model's by construction;
    # check it here so a swapped asset fails loudly instead of importing with a
    # silently wrong wheelbase.
    model_spread = abs(sum(front) / len(front) - sum(rear) / len(rear))
    if abs(model_spread * scale - cfg.WHEEL_BASE) > 1e-3:
        raise RuntimeError(
            f'flatbed glb: axle spread {model_spread:.4f} x {scale:.6f} = '
            f'{model_spread * scale:.4f} m, rig has {cfg.WHEEL_BASE:.4f} m'
        )

    def to_vehicle(p: Vector) -> Vector:
        """Model units -> vehicle frame (road at -R, axle line at 0, nose +X)."""
        return Vector((
            cfg.model_x(p.y),
            p.x * scale,
            cfg.model_z(p.z),
        ))

    chassis = bpy.data.objects.new('truck_chassis', None)
    deck = bpy.data.objects.new('truck_deck', None)
    bpy.context.collection.objects.link(chassis)
    bpy.context.collection.objects.link(deck)

    wheels = []
    for obj, points in baked:
        if obj.name in wheel_info:
            lo, hi, centre = wheel_info[obj.name]
            # The rig has one wheel radius; the front tyre is the exact one, the
            # rear tandem is 9.8 % larger (see the module docstring).
            wheel_scale = cfg.WHEEL_RADIUS / ((hi.z - lo.z) * 0.5)
            radius = (hi.z - lo.z) * 0.5 * wheel_scale
            position = to_vehicle(centre)
            pivot = bpy.data.objects.new(obj.name + '_axle', None)
            bpy.context.collection.objects.link(pivot)
            pivot.parent = chassis
            # The tyre has to meet the road: its centre goes on the physics axle
            # line, not where the body warp would have put it.
            pivot.location = (position.x, position.y, -cfg.CHASSIS_COM_Z)
            pivot['rolling_radius'] = radius
            obj.parent = pivot
            for v, p in zip(obj.data.vertices, points):
                q = p - centre
                # The model's axle runs along X; the pivot spins about its own Y.
                v.co = (-q.y * wheel_scale, q.x * wheel_scale, q.z * wheel_scale)
            wheels.append(pivot)
        else:
            obj.parent = chassis
            for v, p in zip(obj.data.vertices, points):
                vehicle = to_vehicle(p)
                v.co = (vehicle.x, vehicle.y, vehicle.z - cfg.CHASSIS_COM_Z)
            # Split the bed from the cab so the original suspension still works.
            # Faces behind the cab and above the sill belong to the bed.
            bed_faces = [poly.index for poly in obj.data.polygons if all(
                points[i].y > cfg.MODEL_BED_FRONT_Y and points[i].z > cfg.MODEL_BED_SILL_Z
                for i in poly.vertices)]
            if bed_faces:
                bpy.ops.object.select_all(action='DESELECT')
                obj.select_set(True)
                bpy.context.view_layer.objects.active = obj
                bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.select_all(action='DESELECT')
                bpy.ops.object.mode_set(mode='OBJECT')
                for index in bed_faces:
                    obj.data.polygons[index].select = True
                bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.separate(type='SELECTED')
                bpy.ops.object.mode_set(mode='OBJECT')
                for part in list(bpy.context.selected_objects):
                    if part != obj:
                        part.name = 'imported_sprung_' + part.name
                        part.parent = deck
                        for v in part.data.vertices:
                            v.co -= Vector((
                                cfg.DECK_CENTER_X, 0,
                                cfg.DECK_Z - cfg.CHASSIS_COM_Z,
                            ))
        for mat in obj.data.materials:
            if mat and mat.use_nodes:
                bsdf = next((n for n in mat.node_tree.nodes
                             if n.type == 'BSDF_PRINCIPLED'), None)
                if bsdf is None:
                    continue
                if 'Paint' in mat.name:
                    bsdf.inputs['Roughness'].default_value = PAINT_ROUGHNESS
                    _tint_base_color(mat, PAINT_TINT)
                elif 'Wheel' in mat.name:
                    bsdf.inputs['Roughness'].default_value = WHEEL_ROUGHNESS
                else:
                    bsdf.inputs['Roughness'].default_value = 0.40
    return chassis, deck, wheels

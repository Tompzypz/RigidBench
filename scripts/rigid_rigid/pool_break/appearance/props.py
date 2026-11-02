"""The seating and the bin for the pool hall.

Furniture in this room has been rebuilt twice. First it was primitives -- a
bench, a side table, a chair and a cabinet, each one a box or two standing on
legs. They were enough to say "room", but they said it the only way a box can:
no upholstery, no seat, square edges, a silhouette that reads "proxy" the moment
you look at it for more than a second.

Then the seating came from ``jayden_miles_individual_modular_props``: two chairs
with blue cushions and white frames, and a black bin. Better than boxes, but the
pack is a mobile-game asset -- the chairs are flat-shaded with a single 512 px
map, and at four metres their frames are the brightest thing in the frame after
the cloth, which pulls the eye off the break.

The chairs are now ``rustic_chair.glb``: a scanned wooden chair with a 2k map,
real joinery at the stretchers and a worn seat. Two copies, because a hall seats
more than one person. The bin still comes from the props pack -- a barrel is a
barrel, and it is meant to be the black shape in the frame.

Scale
-----
The props pack is a Sketchfab export of an FBX whose units are centimetres, and
Sketchfab's root matrix divides by 100 on the way in, so its meshes arrive at a
tenth of their authored size -- a chair 0.08 m tall. ``PROPS_IMPORT_SCALE`` puts
them back. The rustic chair does not need that correction: it arrives at 0.55 x
0.53 x 0.96 m, which is a chair, so it keeps its own scale.

Source (chairs): https://sketchfab.com/3d-models/rustic-chair (CC-BY-4.0)
Source (bin): https://sketchfab.com/3d-models/jayden-miles-individual-modular-props-67e7db80574443338eb112125117d5e1
(jamiles, CC-BY-4.0)
"""

from __future__ import annotations
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)

import math
from pathlib import Path

import bpy
from mathutils import Vector

PROPS_MODEL_PATH = (
    _PCVE_ROOT / "assets" / "models" / "jayden_miles_individual_modular_props.glb"
)
CHAIR_MODEL_PATH = _PCVE_ROOT / "assets" / "models" / "rustic_chair.glb"

# See the module docstring: the import already divided the authored centimetres
# by 100, so this factor is what restores them.
PROPS_IMPORT_SCALE = 10.0

TRASHBIN_MESH = "Trashbin_Mat_Trashbin_0"
KEPT_MESHES = (TRASHBIN_MESH,)


def _flatten(obj: bpy.types.Object, scale: float = 1.0) -> None:
    """Detach ``obj`` from its hierarchy with its world transform baked in.

    After this the object's origin sits at the centre of its own bounds and its
    mesh is in metres, so placing it means setting ``location`` and turning it --
    not undoing an inherited hierarchy whose scale is 100 on one level and 0.001
    on the next.
    """
    world = obj.matrix_world.copy()
    obj.parent = None
    obj.matrix_world = world
    if scale != 1.0:
        obj.scale = (
            obj.scale.x * scale,
            obj.scale.y * scale,
            obj.scale.z * scale,
        )
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    obj.select_set(False)
    # The glTF importer leaves these in quaternion mode, where ``rotation_euler``
    # is a stale copy of the last quaternion and writing to it does nothing at
    # all. Everything downstream turns the props by yaw, so switch them to Euler
    # up front.
    obj.rotation_mode = "XYZ"


def import_props() -> dict[str, bpy.types.Object]:
    """Import the props pack, keep the bin, hide the rest.

    Returns the kept object keyed by mesh name, already scaled to metres.
    """
    # Remember what was already in the file. The scene is built in pieces --
    # the table, the room, then these props -- and "hide everything I did not
    # keep" has to mean "everything this import brought in", or it hides the
    # walls and the table as well.
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(PROPS_MODEL_PATH))
    imported = [obj for obj in bpy.data.objects if obj not in before]

    kept: dict[str, bpy.types.Object] = {}
    for obj in imported:
        if obj.type != "MESH":
            continue
        if obj.name in KEPT_MESHES:
            _flatten(obj, PROPS_IMPORT_SCALE)
            kept[obj.name] = obj
        else:
            # The pack's own chairs, table and rails: the scene supplies its own.
            obj.hide_viewport = True
            obj.hide_render = True
    bpy.context.view_layer.update()
    return kept


def import_chairs(count: int = 2) -> list[bpy.types.Object]:
    """Import ``rustic_chair.glb`` and return ``count`` independently placeable chairs.

    One import, then copies: the copies share the mesh data (nothing downstream
    edits vertices, only object transforms) but each gets its own object, so
    ``place`` can stand them in different spots and at different angles.
    """
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(CHAIR_MODEL_PATH))
    imported = [obj for obj in bpy.data.objects if obj not in before]
    meshes = [obj for obj in imported if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError(f"No mesh found in {CHAIR_MODEL_PATH.name}")
    for obj in imported:
        if obj.type != "MESH":
            obj.hide_viewport = True
            obj.hide_render = True

    chair = meshes[0]
    _flatten(chair)
    chair.name = "rustic_chair"

    chairs = [chair]
    for index in range(1, count):
        copy = chair.copy()
        copy.name = f"rustic_chair_{index + 1}"
        bpy.context.scene.collection.objects.link(copy)
        chairs.append(copy)
    bpy.context.view_layer.update()
    return chairs


def yaw_facing(dx: float, dy: float) -> float:
    """The yaw that turns a prop's front toward the direction ``(dx, dy)``.

    Both the rustic chair and the pack's bin face model -Y (measured off the
    meshes: a chair's backrest is the only geometry above seat height, and on
    the rustic chair it sits on the +Y side; the bin is a barrel and does not
    care). A Blender Z rotation of ``theta`` sends that front to
    ``(sin t, -cos t)``, so ``theta = atan2(dx, -dy)`` is the one that points it
    at ``(dx, dy)``.
    """
    return math.atan2(dx, -dy)


def drop_to_floor(obj: bpy.types.Object, floor_z: float) -> None:
    """Put the object on the floor without touching its mesh.

    The meshes carry their authored offset in the vertices, so "on the floor"
    is a question about the lowest point of the world-space bounding box, not
    about the object's origin.
    """
    bpy.context.view_layer.update()
    lowest = min((obj.matrix_world @ Vector(corner)).z for corner in obj.bound_box)
    obj.location.z += floor_z - lowest
    bpy.context.view_layer.update()


def place(obj: bpy.types.Object, x: float, y: float, yaw: float, floor_z: float) -> None:
    """Move the object to ``(x, y)``, turn it to ``yaw`` and stand it on the floor.

    ``yaw`` is measured the Blender way: 0 rad points the model's front along
    -Y, and positive yaw turns it counter-clockwise seen from above.
    """
    obj.rotation_mode = "XYZ"
    obj.rotation_euler = (0.0, 0.0, yaw)
    obj.location.x = x
    obj.location.y = y
    drop_to_floor(obj, floor_z)


def face_towards(obj: bpy.types.Object, x: float, y: float,
                 target_x: float, target_y: float, floor_z: float) -> None:
    """Stand the object at ``(x, y)`` turned to look at ``(target_x, target_y)``."""
    place(obj, x, y, yaw_facing(target_x - x, target_y - y), floor_z)

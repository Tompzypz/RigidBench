"""Wall pictures for the pool hall, from the cafe_wall_pictures pack.

The walls used to carry two prints built out of boxes: a brass frame, a card
mount and a dark rectangle. At four metres that is a rectangle with a lighter
rectangle inside it -- no glass, no print, no depth. They were placeholders
that had stopped pretending.

This pack ships three framed prints with proper 2k maps, glass, a moulded
frame and a shadow gap behind. They cost one import.

Scale
-----
Unlike the props pack (which is a centimetre FBX that arrives at a tenth of
its size), this one is authored in metres: each picture measures 488 x 335 x
13 mm on import, which is a real cafe print and needs no correction factor.
The check is the thickness -- 13 mm is a picture frame, and 130 mm would not
be.

The three pictures sit on top of each other in the file
-----------------------------------------------------
All three meshes share one origin and identical bounds: the pack is a set of
interchangeable frames, not a composed arrangement. So each one is unparented
and treated as its own object, and the arrangement is decided here.

Source: https://sketchfab.com/3d-models/cafe-wall-pictures-7016b8389cdc45658bb1399f476fad00
(Guy in a Poncho, CC-BY-4.0)
"""

from __future__ import annotations
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)

from pathlib import Path

import bpy

CAFE_MODEL_PATH = (
    _PCVE_ROOT / "assets" / "models" / "cafe_wall_pictures.glb"
)

PICTURE_1 = "wall_picture_1_wall_picture_1_2k_0"
PICTURE_2 = "wall_picture_2_wall_picture_2_2k_0"
PICTURE_3 = "wall_picture_3_wall_picture_3_0"

PICTURE_MESHES = (PICTURE_1, PICTURE_2, PICTURE_3)

# The pack's three frames are not the same size, and one of them is a portrait:
# PICTURE_1 is 488 x 335, PICTURE_2 is 428 x 623 (the portrait), PICTURE_3 is
# 591 x 406 mm. At 0.88 they come out 429 x 295, 377 x 548 and 520 x 357 mm,
# which is cafe-print size on a 4 m wall. The names do not sort by size -- the
# portrait is PICTURE_2, not PICTURE_3 -- so check the numbers, not the index.
#
# The factor dates from the 25 mm rig, whose top of frame stopped at z = 0.77 m
# above the felt: the portrait at 1:1 is 623 mm, and at any height clear of the
# cap rail it broke the top edge. The current 21 mm rig sees up to z = 1.00 m, so
# 1:1 would fit now -- the set is left at 0.88 because the arrangement was solved
# against these sizes and nothing about the frame wants them bigger.
PICTURE_SCALE = 0.88

# The frame's moulding faces model +X and the print sits at the top of that
# face, so a picture hung with no rotation looks at +X -- i.e. away from the
# far wall and into the room, which is where the camera is.
PICTURE_FRONT_AXIS = "+X"


def _flatten_alpha(materials) -> None:
    """Turn the pack's blended glass into dithered glass.

    All three materials import with ``alphaMode: BLEND`` and an alpha channel
    packed into the base texture. In EEVEE a blended surface has no depth
    sorting of its own, so the glass pane and the print it covers resolve in
    whatever order the triangles happen to be drawn in -- the prints came out
    with large white and dark wedges sliced across them, which is what a
    sorted-by-guess transparency looks like.

    Stochastic alpha (``DITHERED``, which is ``HASHED`` in 4.x terms) keeps the
    glass but resolves coverage per sample instead of per object, so there is
    nothing left to sort. At four metres the dither noise is invisible; the
    wedges were not.
    """
    for mat in materials:
        if mat is None:
            continue
        if hasattr(mat, "surface_render_method"):
            mat.surface_render_method = "DITHERED"
        if hasattr(mat, "blend_method"):
            mat.blend_method = "HASHED"


def import_pictures() -> dict[str, bpy.types.Object]:
    """Import the pack and return its three prints, each standing on its own.

    Every returned object is unparented, has its world transform baked into the
    mesh data and its origin at the centre of its own bounds -- so hanging it
    is ``location`` plus a yaw, with no inherited hierarchy to undo.
    """
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(CAFE_MODEL_PATH))
    imported = [obj for obj in bpy.data.objects if obj not in before]

    kept: dict[str, bpy.types.Object] = {}
    materials = []
    for obj in imported:
        if obj.type != "MESH":
            # The pack's Sketchfab/RootNode empties. They render nothing and
            # keeping them parented would drag the prints along with them.
            continue
        world = obj.matrix_world.copy()
        obj.parent = None
        obj.matrix_world = world
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        obj.scale = (PICTURE_SCALE, PICTURE_SCALE, PICTURE_SCALE)
        bpy.ops.object.transform_apply(scale=True)
        bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
        obj.select_set(False)
        # glTF leaves objects in quaternion mode, where writing rotation_euler
        # is silently ignored. Everything downstream yaws these objects.
        obj.rotation_mode = "XYZ"
        kept[obj.name] = obj
        materials.extend(m for m in obj.data.materials if m is not None)
    _flatten_alpha(materials)
    bpy.context.view_layer.update()
    return kept


def hang(obj: bpy.types.Object, x: float, y: float, z: float,
         yaw: float = 0.0) -> None:
    """Hang one picture at ``(x, y, z)``, turned ``yaw`` about the vertical.

    ``x`` is the centre of the frame; callers that want the back of the frame
    against a wall should subtract half the thickness (``obj.dimensions.x``)
    from the wall plane themselves, because only they know which wall it is.
    """
    obj.rotation_mode = "XYZ"
    obj.rotation_euler = (0.0, 0.0, yaw)
    obj.location = (x, y, z)


def back_offset(obj: bpy.types.Object) -> float:
    """Half the frame's thickness, so it can be set back against a wall."""
    return obj.dimensions.x / 2.0

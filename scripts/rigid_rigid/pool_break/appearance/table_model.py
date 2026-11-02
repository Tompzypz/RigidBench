"""The hall's pool table, imported from its own model.

Why this exists
---------------
The scene used to draw its table out of ``pool_table_animation.glb``, the same
file that supplies the four balls. That file is a low-poly game asset: the cloth
is a single flat sheet, the rails are boxes with the corner pockets cut into
them by hand, and the apron is four boards. It was enough to hold the physics,
but at 1.5 m from the camera the cloth has no nap, the pockets have no throats
and the frame has no joinery -- the table reads as a green tray with cushions.

This module brings in a proper billiard table (felt, cushions, leather pockets,
turned legs, 4k maps) and fits it to the geometry the simulation already uses,
so the ball trajectories stay valid. The physics is not touched: the balls are
still the meshes from ``pool_table_animation.glb`` and still keyed from the same
PyBullet run. Only the table under them changes.

Fitting it to the simulation
----------------------------
Everything the shot cares about is measured off the imported mesh rather than
guessed (see the ``MODEL_*`` constants, probed with vertical ray casts over the
cloth):

* the cloth plane -- the flat sheet the balls rest on -- sits at
  ``MODEL_FELT_Z`` and is moved to world ``z = 0``, which is where the
  simulation puts the felt and every ball centre;
* the cushion noses -- the vertical faces a ball actually bounces off -- are at
  ``+/- MODEL_NOSE_HALF_X`` and ``+/- MODEL_NOSE_HALF_Y``, so they are scaled
  onto the simulation's cushion planes (``play_half_x`` / ``play_half_y``).

The two axes get **different** scale factors (0.922 and 0.943). That is not an
accident: this model's playing surface is 1.96 x 0.99 m, the scene's is
1.81 x 0.93 m, and those are not the same shape, because the scene was scaled so
that the *balls* are regulation rather than the table (see ``scene_config``).
Forcing one uniform factor would leave the cushions 5-10 mm off the planes the
simulation bounces the balls on -- close enough to look like the balls are
sinking into the cushion at the moment of contact. A 2% anisotropy on a piece of
furniture is invisible; a ball 5 mm inside a cushion is not.

What is dropped
---------------
The file ships sixteen balls, a triangle rack, a chalk cube and two cue sticks
arranged on and around the table. None of them belong in this shot: the scene
has its own four balls under physics, and the rack would sit on the cue ball's
path. They are hidden rather than deleted, the same way ``import_table`` hides
the fifteen balls the shot does not use.

Source: https://sketchfab.com/3d-models/pool-table-billiard-table-with-cues-and-balls
(Mark Peters, CC-BY-4.0)
"""

from __future__ import annotations
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)

from pathlib import Path

import bpy

POOL_TABLE_MODEL_PATH = (
    _PCVE_ROOT
    / "assets"
    / "models"
    / "pool_table_-_billiard_table_with_cues_and_balls.glb"
)

# ---------------------------------------------------------- measured off the file
# Cloth plane. The most common vertex height in the bed mesh, and the height every
# downward ray between the cushions returns -- the cloth is a single flat sheet.
MODEL_FELT_Z = 0.795
# Cushion noses, from ray casts across the cloth: the surface steps from the felt
# up onto the cushion at exactly these distances from the table's centre.
MODEL_NOSE_HALF_X = 0.980
MODEL_NOSE_HALF_Y = 0.495

# The two meshes that are the table. Everything else in the file is a prop.
TABLE_MESH_SUFFIXES = {
    "_PoolTable_MTL_0": "pool_table_bed",
    "_PoolTable_MTL_0.001": "pool_table_frame",
}


def _scale_for(play_half_x: float, play_half_y: float) -> tuple[float, float, float]:
    """Per-axis scale that lands this model's cushion noses on the scene's planes.

    ``z`` takes the mean of the two so the cushions keep their profile: the
    difference between the horizontal factors is 2%, and splitting it vertically
    is less visible than picking one axis and squashing the cushion height.
    """
    sx = play_half_x / MODEL_NOSE_HALF_X
    sy = play_half_y / MODEL_NOSE_HALF_Y
    return (sx, sy, (sx + sy) / 2.0)


# The one material the table carries. Cloth, rails, apron and legs share it, and
# it is one 4k atlas, so any adjustment has to be one that suits all of them.
TABLE_MATERIAL = "PoolTable_MTL"

# Grading, applied to the texture rather than baked into it.
#
# The atlas is a pale sage cloth. Under the hall's key lamp -- and through AgX,
# which trades saturation for headroom as a value climbs -- a sample of the cloth
# comes out (183, 206, 179): 23 levels between green and red is a mint, not a
# felt. The wood is a grey-brown at similar brightness, so the table as a whole
# reads as grey plastic while the room around it stays dark and warm.
#
# Saturation is the right operator here because it scales the colour that is
# already there: the cloth gains most of it, the warm wood gains a little and
# reads as varnished rather than painted, and anything neutral in the atlas
# (sights, name plate) does not move at all. A multiply would have dragged the
# wood green, and repainting the atlas is not this scene's business.
GRADE_SATURATION = 1.55
GRADE_VALUE = 0.88

# Floor for the roughness the model ships.
#
# The frame is varnished and the map has it very smooth: under a 26 W bar lamp
# 0.6 m above the cloth, the near rail returns two hard, pure-white patches of
# reflected lamp where a real varnish would return a soft sheen. Clamping the
# floor to 0.40 keeps the finish glossy -- the highlight is still there and still
# moves with the camera -- but stops it clipping to white, and it costs the
# cloth nothing: felt should be matte anyway, and its nap is in the normal map,
# not in this channel.
ROUGHNESS_FLOOR = 0.40


def grade_table(table: list[bpy.types.Object]) -> None:
    """Grade the cloth's colour and the frame's finish, on the node tree.

    Both go between the model's own maps and the Principled node, so the
    original maps are untouched and each adjustment is one node to find.
    """
    done: set[str] = set()
    for obj in table:
        for mat in obj.data.materials:
            if mat is None or not mat.use_nodes or mat.name in done:
                continue
            done.add(mat.name)
            tree = mat.node_tree
            bsdf = next((n for n in tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if bsdf is None:
                continue

            base = bsdf.inputs["Base Color"]
            if base.is_linked:
                source = base.links[0].from_node
                grade = tree.nodes.new("ShaderNodeHueSaturation")
                grade.name = "table_grade"
                grade.inputs["Saturation"].default_value = GRADE_SATURATION
                grade.inputs["Value"].default_value = GRADE_VALUE
                grade.location = (source.location.x + 220.0, source.location.y)
                tree.links.new(source.outputs["Color"], grade.inputs["Color"])
                tree.links.new(grade.outputs["Color"], base)

            rough = bsdf.inputs["Roughness"]
            if rough.is_linked:
                link = rough.links[0]
                clamp = tree.nodes.new("ShaderNodeMath")
                clamp.name = "table_roughness_floor"
                clamp.operation = "MAXIMUM"
                clamp.inputs[1].default_value = ROUGHNESS_FLOOR
                clamp.location = (link.from_node.location.x + 220.0,
                                  link.from_node.location.y - 220.0)
                tree.links.new(link.from_socket, clamp.inputs[0])
                tree.links.new(clamp.outputs[0], rough)


def import_table(play_half_x: float, play_half_y: float) -> list[bpy.types.Object]:
    """Import the table, fitted so its felt is world ``z = 0`` and its noses land
    on ``+/- play_half_x`` / ``+/- play_half_y``.

    Returns the two table meshes, each with its world transform baked into the
    mesh data and the object left at the origin -- so nothing downstream has to
    know about the empty hierarchy the file arrived in.
    """
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(POOL_TABLE_MODEL_PATH))
    imported = [obj for obj in bpy.data.objects if obj not in before]

    table: list[bpy.types.Object] = []
    for obj in imported:
        if obj.type != "MESH":
            continue
        renamed = next(
            (name for suffix, name in TABLE_MESH_SUFFIXES.items()
             if obj.name.endswith(suffix)),
            None,
        )
        if renamed is None:
            # Balls, the rack, the chalk and the cues.
            obj.hide_viewport = True
            obj.hide_render = True
            continue
        obj.name = renamed
        table.append(obj)
    if len(table) != len(TABLE_MESH_SUFFIXES):
        raise RuntimeError(
            f"Expected {len(TABLE_MESH_SUFFIXES)} table meshes in "
            f"{POOL_TABLE_MODEL_PATH.name}, found {len(table)}"
        )

    # Drop the empties: the file nests the table under a centimetre-scaled root
    # and a hundred-scaled group, and every one of those transforms has to end up
    # in the mesh before the fitting scale can be written into ``obj.scale``.
    for obj in table:
        world = obj.matrix_world.copy()
        obj.parent = None
        obj.matrix_world = world
    bpy.ops.object.select_all(action="DESELECT")
    for obj in table:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = table[0]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    scale = _scale_for(play_half_x, play_half_y)
    for obj in table:
        obj.scale = scale
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    # The cloth is the one surface that has to be exact, so the drop is computed
    # from the measured felt height rather than from the model's own floor.
    for obj in table:
        obj.location.z = -MODEL_FELT_Z * scale[2]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=False)
    bpy.ops.object.select_all(action="DESELECT")

    grade_table(table)
    bpy.context.view_layer.update()
    return table

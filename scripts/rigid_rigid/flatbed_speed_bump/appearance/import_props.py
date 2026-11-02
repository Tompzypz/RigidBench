"""Import the downloaded props: containers, lamp posts, speed hump, parcels.

None of these are physics bodies except the parcels, which are the *picture* of
cargo bodies the simulation owns; the rest never appear in the ground truth.
Three are placed at their authored size, **unscaled**:

* the containers are real 12.1 / 6.4 x 2.4 x 2.9 m boxes, turned and shifted
  only, laid out as two rows with their long sides to the road (see
  ``CONTAINER_LAYOUT``);
* the lamp posts are a single uniform 1.172x, because 6.40 m is the height the
  lighting rig was built around and a lamp post is one rigid object.

The speed hump is the one non-uniform placement in the scene, and it is not a
prop: it is the *picture* of a collider that already exists as a sine profile in
``scene_config``. Its three factors map the model's ramp feet onto the
collider's half width, its 0.103 m plateau onto the requested peak, and its
9.92 m span onto the 8 m road. A single factor cannot do all three -- at the
width factor it would be 0.083 m tall, so the truck would visibly ride 87 mm
above the hump it is colliding with; at the height factor it would be 16.4 m
wide, twice the road. Nothing here is animated, so no vertex-level adapter like
``import_truck`` is needed.

Measured from the glbs (glTF units are metres):

* ``container_pack`` -- a whole depot, 29.8 x 43.2 x 8.8 m, 63 meshes, 40 ft
  boxes at 12.06 x 2.42 x 2.92 m stacked up to three high, ground plane at
  z = 0. Long axis along +X, so the boxes present their long sides to the road.
* ``lamppost`` -- one 5.46 m post, arm reaching +X to x = 1.25, base at z = 0.
* ``speed_bump`` -- one hump, 2.0 m along X (the travel direction), 9.92 m
  along Y, plateau at z = +0.103, moulded skirt down to z = -0.208. It goes
  flat at |x| ~ 0.60 and peaks across |x| < 0.15.
* ``carton_box_05_closed`` -- one parcel, 31.5488 x 39.9721 x 25.8244 model
  units, centred on x = y = 0 with its base on z = 0. Unlike the three above it
  is scaled, by the single ``CARGO_SCALE`` factor, because it has to match a
  box collider whose half extents the simulation owns.
"""

from __future__ import annotations
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)

import sys
from pathlib import Path
sys.path.insert(0, str(_PCVE_ROOT / 'scripts'))
from pcve_blender_compat import (shader_socket, set_shader_input, eevee_engine, set_eevee_property, set_color_property)

import math
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

import scene_config as cfg

MODELS = _PCVE_ROOT / "assets" / "models"
CONTAINER_PACK = MODELS / "container_pack.glb"
LAMPPOST = MODELS / "lamppost.glb"
SPEED_HUMP = MODELS / "speed_bump.glb"

# --------------------------------------------------------------- container yard
# A yard is rows, not a wall. The previous layout quarter-turned every box so
# its 2.4 m end faced the road, then set them at a 2.5 m pitch from x = -22 to
# +58: 66 boxes shoulder to shoulder, which from the fixed camera read as a
# corrugated fence -- and because the only face in shot was a narrow end panel,
# every container looked taller than it is. This layout is the other reading of
# the same asset: long sides to the road, two rows 4.75 m apart, real gaps and
# staggered joints. The shot now shows the 12.1 m side the model was built
# with, ~13 boxes instead of 66, and the place reads as a depot with depth
# rather than as a barrier.
CONTAINER_FRONT_Y = 9.20    # road-side row centre; front face lands on y = 8.0
CONTAINER_BACK_Y = 13.95    # second row, one bay behind, joints staggered
# The camera stands on the -Y apron, so everything on that side is seen at a
# grazing angle and swallows the right half of the frame as bare ground. A
# second block fills it: same asset, same orientation, but read as a yard block
# rather than a row -- two staggered lines 4.5 m apart, so the near line hides
# the far one except through its gaps, which is what gives the side its depth.
# The near line starts at x = 8 because below ~x = 5 the block falls outside the
# right edge of the frame: from this camera the apron is only visible from about
# 30 m ahead, and a container 10.5 m off the kerb only enters the frustum at
# x ~ 5.
CONTAINER_APRON_Y = -10.50      # near line, camera side of the road
CONTAINER_APRON_BACK_Y = -15.00  # far line of the apron block
CONTAINER_ROWS = {
    "front": CONTAINER_FRONT_Y,
    "back": CONTAINER_BACK_Y,
    "apron": CONTAINER_APRON_Y,
    "apron_back": CONTAINER_APRON_BACK_Y,
}
CONTAINER_HEIGHT = 2.90     # the pack's boxes are all 2.9 m tall
# The pack ships 22 whole 40 ft boxes (12.1 x 2.4 x 2.9) and 15 whole 20 ft
# ones (6.4 x 2.4 x 2.9); everything else in it is a cut slice. Both lengths
# are used so the yard is not one repeated box.
#
# (x of centre, row, nominal length, base z). A base z of 2.9 means the box is
# stacked on the one below: the yard stacks two high in the back row only, so
# the height reads as depth rather than as a wall next to the road.
CONTAINER_LAYOUT = (
    (-21.0, "front", "40", 0.0),
    (-8.6, "front", "40", 0.0),
    (4.2, "front", "40", 0.0),
    (17.0, "front", "40", 0.0),
    # A 14 m opening instead of a box at x = 29.9: a depot has aisles between
    # blocks, and this one also lets the back row read through it, which is the
    # cheapest depth cue in a shot that is otherwise one long wall.
    (43.2, "front", "40", 0.0),
    (56.3, "front", "40", 0.0),
    (-14.8, "back", "40", 0.0),
    (5.6, "back", "40", 0.0),
    (5.6, "back", "40", CONTAINER_HEIGHT),
    (24.4, "back", "40", 0.0),
    (44.0, "back", "40", 0.0),
    (41.0, "back", "20", CONTAINER_HEIGHT),   # 20 ft on the end of a 40 ft
    # The apron block: two staggered lines, starting close enough to the camera
    # that the right-hand ground has something in the foreground. The pitch
    # wanders between 17 and 21 m on purpose -- an exact bay would read as a
    # generated row, and this is the side of the shot the eye lands on when it
    # has nothing else to do. The far line's boxes land in the near line's gaps.
    (8.0, "apron", "40", 0.0),
    (26.0, "apron", "40", 0.0),
    (26.0, "apron", "40", CONTAINER_HEIGHT),
    (47.0, "apron", "40", 0.0),
    (65.0, "apron", "40", 0.0),
    (85.0, "apron", "40", 0.0),
    (106.0, "apron", "40", 0.0),
    (106.0, "apron", "20", CONTAINER_HEIGHT),
    (127.0, "apron", "40", 0.0),
    (147.0, "apron", "40", 0.0),
    (17.0, "apron_back", "40", 0.0),
    (37.0, "apron_back", "40", 0.0),
    (57.0, "apron_back", "40", 0.0),
    (57.0, "apron_back", "40", CONTAINER_HEIGHT),
    (78.0, "apron_back", "40", 0.0),
    (99.0, "apron_back", "40", 0.0),
    (120.0, "apron_back", "40", 0.0),
    (141.0, "apron_back", "40", 0.0),
)

# How far a box's centre may sit off its row line, in metres. Both yard-side
# rows are true to within 5 cm: they are set against a kerb. The apron block is
# the one that is read almost edge-on, and a dead straight line of boxes 10.5 m
# off the near kerb was the last thing in the shot that still looked generated
# rather than parked, so those two rows are allowed to wander either way.
# 1.5 m proved too polite: the two lines held a constant 4.5 m gap, so the eye
# still read "two rows" with a wobble on them. At 2.2 m the near line sets back
# anywhere from 4.7 m to 8.1 m off the kerb and the far line 9.1 m to 12.7 m,
# so consecutive boxes step in and out by up to 3.4 m and every bay is at a
# visibly different distance from the road. The bands still stop just short of
# each other, so no rear box ever comes forward of a front one.
ROW_DEPTH_JITTER = {
    "front": 0.05,
    "back": 0.05,
    "apron": 2.20,
    "apron_back": 2.20,
}

# ---------------------------------------------------------------------- lamps
LAMP_MODEL_HEIGHT = 5.46
LAMP_TARGET_HEIGHT = 6.40
# Yard lighting is laid out to light the apron, not to line the kerb. This row
# has been thinned twice and the lesson from both passes is that pitch is the
# wrong knob: a 6.4 m mast is still ~34 px tall at 240 m, so the far end of the
# row never shrinks away -- it just piles up around the vanishing point and the
# whole line keeps reading as a fence of posts no matter how far apart they
# stand. At 36 m that pile-up was the complaint, so the row is now *shorter in
# count* instead: 60 m between masts, 4 of them in shot.
# The row still has to reach somewhere, though. An earlier version stopped at
# x = 48 and the masts visibly ran out a third of the way to the horizon, which
# is the same tell as a road that ends, so the last mast sits at x = 200, past
# the point where the markings go sub-pixel.
LAMP_XS = (-40.0, 20.0, 80.0, 140.0, 200.0)
LAMP_Y = 5.00       # yard side of the kerb, same line the old masts stood on
# There is deliberately no mast on the apron kerb: the block on that side is
# read at a grazing angle, so a post in front of it became a foreground stick
# with nothing to light, and the right-hand ground already has the container
# block to carry its scale. `build_lamp_posts(arm_toward=+1)` is still able to
# place one if that side ever needs lighting again.
# The shot is late afternoon with the sun about 30 degrees up, so the posts are
# switched off -- which is also what a working yard does. The asset ships with
# its lens at emission strength 1.0 and the renderer used to hang a 520 W point
# light under every head, which read as "who left the lights on at noon". Set
# this True (and the caller will light them) for a dusk or night pass.
LAMPS_LIT = False

# ------------------------------------------------------------------ speed hump
HUMP_MODEL_HALF_LENGTH = 0.60   # |x| where the model's profile reaches the road
HUMP_MODEL_PEAK = 0.103
HUMP_MODEL_HALF_WIDTH = 4.96
HUMP_MODEL_CENTRE_Y = 3.475


def _import_glb(glb: Path) -> list[bpy.types.Object]:
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(glb))
    return [obj for obj in bpy.data.objects if obj not in before]


def _group(objs: list[bpy.types.Object], name: str) -> bpy.types.Object:
    """Parent the imported roots to a fresh empty without moving anything."""
    root = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(root)
    members = set(objs)
    for obj in objs:
        if obj.parent in members:
            continue
        world = obj.matrix_world.copy()
        obj.parent = root
        obj.matrix_world = world
    return root


def _harvest_containers() -> tuple[list[bpy.types.Object], list[bpy.types.Object]]:
    """Import the pack and keep its intact boxes, in world space, split by length.

    63 meshes, but only 37 of them are whole containers -- the rest are cut
    boxes the pack uses to fill its own scene edges (0.5 x 1.1 x 2.8 m slices).
    Placing those as if they were containers is what left 1 m gaps in the old
    row. Returns ``(40 ft, 20 ft)`` so the layout table can pick a length per
    slot instead of accepting whatever came first.
    """
    objs = _import_glb(CONTAINER_PACK)
    meshes = [obj for obj in objs if obj.type == "MESH"]
    empties = [obj for obj in objs if obj.type != "MESH"]
    forties: list[bpy.types.Object] = []
    twenties: list[bpy.types.Object] = []
    for obj in meshes:
        lo, hi = _bbox_world(obj)
        long_side = max(hi[0] - lo[0], hi[1] - lo[1])
        if (hi[2] - lo[2]) < 2.0:
            continue
        if long_side > 10.0:
            forties.append(obj)
        elif long_side > 5.0:
            twenties.append(obj)
    keep = set(forties) | set(twenties)
    for obj in meshes:
        if obj not in keep:
            bpy.data.objects.remove(obj, do_unlink=True)
    for obj in empties:
        bpy.data.objects.remove(obj, do_unlink=True)
    for obj in keep:
        world = obj.matrix_world.copy()
        obj.parent = None
        obj.matrix_world = world
    return forties, twenties


def _bbox_world(obj: bpy.types.Object) -> tuple[list[float], list[float]]:
    pts = [obj.matrix_world @ v.co for v in obj.data.vertices]
    return (
        [min(p[i] for p in pts) for i in range(3)],
        [max(p[i] for p in pts) for i in range(3)],
    )


def _yaw_about_centre(obj: bpy.types.Object, angle: float) -> None:
    """Turn ``obj`` about the vertical axis through its own bounding-box centre."""
    lo, hi = _bbox_world(obj)
    centre = Vector(((lo[0] + hi[0]) * 0.5, (lo[1] + hi[1]) * 0.5, (lo[2] + hi[2]) * 0.5))
    obj.matrix_world = (
        Matrix.Translation(centre)
        @ Matrix.Rotation(angle, 4, "Z")
        @ Matrix.Translation(-centre)
        @ obj.matrix_world
    )


def _long_axis_is_x(obj: bpy.types.Object) -> bool:
    lo, hi = _bbox_world(obj)
    return (hi[0] - lo[0]) >= (hi[1] - lo[1])


def _place(obj: bpy.types.Object, x: float, y: float, z_base: float) -> tuple[float, float, float]:
    """Sit ``obj`` on ``z_base`` with its bbox centre over ``(x, y)``, long side to the road.

    The layout table is written in road coordinates -- x along the haul road, y
    away from it -- so a box whose long axis is authored along Y is turned a
    quarter first. Returns the box's (length, depth, height) after the turn.
    """
    if not _long_axis_is_x(obj):
        _yaw_about_centre(obj, math.pi / 2.0)
    lo, hi = _bbox_world(obj)
    dims = (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])
    obj.matrix_world = (
        Matrix.Translation(
            (x - (lo[0] + hi[0]) * 0.5, y - (lo[1] + hi[1]) * 0.5, z_base - lo[2])
        )
        @ obj.matrix_world
    )
    return dims


def build_cargo_cartons(count: int = 2) -> list[bpy.types.Object]:
    """Import the parcel glb once and clone it for every cargo body.

    The collider is a box of ``CARGO_HALF_EXTENTS``, so the picture only stays
    honest if the mesh really is that box: the import is scaled by the single
    factor ``CARGO_SCALE``, its bounding-box centre is moved to the origin, and
    the transform is baked into the mesh. After that one object is a parcel
    whose ``location`` is its centre -- the same quantity the simulation reports
    -- and the clones are ``Object.copy()``, so all bodies share one mesh.
    """
    asset = MODELS / cfg.CARGO_ASSET
    imported = _import_glb(asset)
    meshes = [obj for obj in imported if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError(f"{asset.name} imported no mesh")
    for obj in imported:
        if obj.type != "MESH":
            bpy.data.objects.remove(obj, do_unlink=True)

    bpy.ops.object.select_all(action="DESELECT")
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    proto = meshes[0]

    lo, hi = _bbox_world(proto)
    centre = Vector(((lo[i] + hi[i]) * 0.5 for i in range(3)))
    proto.matrix_world = (
        Matrix.Scale(cfg.CARGO_SCALE, 4) @ Matrix.Translation(-centre) @ proto.matrix_world
    )
    bpy.ops.object.select_all(action="DESELECT")
    proto.select_set(True)
    bpy.context.view_layer.objects.active = proto
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    # Cardboard, not the pack's default: the glb ships a mid-grey that reads as
    # moulded plastic next to the truck's paint.
    for slot in proto.material_slots:
        if slot.material and slot.material.use_nodes:
            for node in slot.material.node_tree.nodes:
                if node.type == "BSDF_PRINCIPLED":
                    node.inputs["Roughness"].default_value = 0.82
                    set_shader_input(node, 'Specular IOR Level', 0.28)

    cartons = [proto]
    for index in range(1, count):
        clone = proto.copy()
        bpy.context.scene.collection.objects.link(clone)
        cartons.append(clone)
    for index, obj in enumerate(cartons):
        obj.name = f"cargo_{index + 1}"
    return cartons


def _bay_hash(row: str, x: float) -> float:
    """Deterministic value in ``[-1, 1]`` for one bay of one row.

    Keyed on ``(row, x)`` rather than on the loop index so a stacked box keeps
    the placement and the yaw of the box it stands on: an index-keyed value
    would slide the upper container up to three metres off the lower one.
    """
    seed = int(round(float(x) * 10.0)) * 7919 + sum(ord(c) for c in row) * 104729
    return ((seed * 2654435761) % 2003) / 1001.0 - 1.0


def build_container_yard() -> bpy.types.Object:
    """Lay the pack's intact boxes out as two rows behind the fence.

    ``Object.copy()`` shares the mesh datablock, so a box reused twice costs one
    transform and no geometry; the harvested originals are deleted afterwards so
    the pack's own depot layout cannot leak into the shot.
    """
    forties, twenties = _harvest_containers()
    root = bpy.data.objects.new("container_yard", None)
    bpy.context.scene.collection.objects.link(root)

    sources = {"40": forties, "20": twenties}
    used = {"40": 0, "20": 0}
    for index, (x, row, length, z_base) in enumerate(CONTAINER_LAYOUT):
        pool = sources[length]
        if not pool:
            continue
        source = pool[used[length] % len(pool)]
        used[length] += 1
        obj = source.copy()
        obj.name = f"container_{row}_{index:02d}"
        bpy.context.scene.collection.objects.link(obj)

        # Deterministic jitter: a perfect grid is the loudest generated tell
        # left, and no RNG keeps the render reproducible. Depth is the one that
        # matters here -- how far the box sits from its kerb -- see
        # ``ROW_DEPTH_JITTER``; a degree of yaw is what a box set down by a
        # crane actually has, and the gaps in the table do the rest.
        wobble = _bay_hash(row, x)
        y = CONTAINER_ROWS[row] + wobble * ROW_DEPTH_JITTER[row]
        _yaw_about_centre(obj, math.radians(wobble * 1.1))
        _place(obj, x, y, z_base)
        obj.parent = root

    for obj in forties + twenties:
        bpy.data.objects.remove(obj, do_unlink=True)
    return root


def _unlit_lens(objs: list[bpy.types.Object]) -> None:
    """Drop the glb's emissive lamp lens so an unlit post really is unlit.

    The asset authors the lens as white emission at strength 1.0, which in
    daylight is a glowing panel on every post. Zeroing the strength keeps the
    lens geometry and its base colour -- it reads as a plastic cover.
    """
    for obj in objs:
        if obj.type != "MESH":
            continue
        for slot in obj.material_slots:
            mat = slot.material
            if not mat or not mat.use_nodes:
                continue
            bsdf = next(
                (n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None
            )
            if bsdf is None:
                continue
            strength = bsdf.inputs.get("Emission Strength")
            if strength is not None and not strength.is_linked:
                strength.default_value = 0.0


def build_lamp_posts(
    xs=LAMP_XS,
    y: float = LAMP_Y,
    height: float = LAMP_TARGET_HEIGHT,
    arm_toward: float = -1.0,
) -> list[tuple[float, float, float]]:
    """Place the downloaded post along a kerb line.

    The asset's arm reaches +X, so the post is yawed a quarter turn to point it
    across the road instead of down it. ``arm_toward`` is the *sign of Y* the
    arm should reach: -1 on the yard kerb, where the road lies at y < 5, and +1
    on the apron kerb on the camera side, where the road lies at y > -7.6.
    Yawing both rows the same way is what leaves the apron posts lighting the
    back of their own block, so the sign is carried through to the head offset
    the caller hangs its point light on.
    """
    factor = float(height) / LAMP_MODEL_HEIGHT
    sign = 1.0 if arm_toward >= 0.0 else -1.0
    heads: list[tuple[float, float, float]] = []
    for index, x in enumerate(xs):
        objs = _import_glb(LAMPPOST)
        if not LAMPS_LIT:
            _unlit_lens(objs)
        root = _group(objs, f"lamp_post_{index}")
        root.location = (float(x), float(y), 0.0)
        root.rotation_euler = (0.0, 0.0, sign * math.pi / 2.0)
        root.scale = (factor, factor, factor)
        heads.append((float(x), float(y) + sign * 1.15 * factor, 5.05 * factor))
    return heads


def build_speed_hump(
    height: float, width: float, road_half_width: float
) -> bpy.types.Object:
    """Skin the collider bump with the downloaded hump.

    Three separate factors, each chosen against the collider rather than the
    asset:

    * X maps the model's ramp feet (|x| = 0.60) onto the collider's half width,
      so the hump starts rising exactly where the collision profile does;
    * Z puts the model's 0.103 m plateau on the requested peak height;
    * Y spans the visible road width.

    The model's top is flatter than a sine, so mid-slope it sits up to ~26 mm
    above the collision profile -- the tyre sinks into the hump by that much
    instead of floating over it, which is the error that reads correctly.
    """
    objs = _import_glb(SPEED_HUMP)
    root = _group(objs, "speed_hump")
    root.scale = (
        (float(width) * 0.5) / HUMP_MODEL_HALF_LENGTH,
        (2.0 * float(road_half_width)) / (2.0 * HUMP_MODEL_HALF_WIDTH),
        float(height) / HUMP_MODEL_PEAK,
    )
    root.location = (
        cfg.SPEED_BUMP_CENTER_X,
        -HUMP_MODEL_CENTRE_Y * root.scale[1],
        0.0,
    )
    return root

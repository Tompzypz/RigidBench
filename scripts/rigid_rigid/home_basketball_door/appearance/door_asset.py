"""Swap the room's painted door for a modelled one, frame included.

``cloe_room.glb`` ships a door that is a **zero-thickness sheet**: 18 vertices,
20 triangles, all normals +Y, and no material of its own -- the room paints it
with whatever texture the wall happens to carry. Solidified to the 45 mm the
simulator collides with it renders as a flat card with a ladder of light and
dark rungs down its edge (see the README's *Known limits*). ``old_door.glb`` is
a real door: panels, mouldings, a lever handle, a threshold, and the casing
that goes round it.

The asset is one mesh holding both the fixed frame and the leaf that stands
ajar in it, so this module measures the pair apart and puts each where the
scene's own door used to be:

* the **leaf** is re-posed into the room's convention -- long axis +X, hinge
  line at the object's origin, standing on the floor, centred on the collision
  slab -- so the physics animation keys it exactly as before;
* with ``frame_style: fitted``, the **frame** is built as thin bevelled trim
  on the measured wall plane, with separate reveal liners and shared satin
  paint; the original scaled asset frame remains available as a legacy option.

The renderer fits the leaf to the measured plaster opening and passes that
same hinge slab to the simulator via ``door_leaf.json``. The imported paint
panels and hardware are fitted to it by ``fit_leaf_to_collision``.
"""

from __future__ import annotations
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)

import math
from typing import Any, Iterable

import bmesh
import bpy
from mathutils import Matrix, Vector

# The asset's frame is an axis-aligned hollow box around a leaf that stands
# 60.84 deg open. Anything within this many asset units of the leaf's plane and
# not part of the frame's outer skin is leaf -- the handle sticks out 8.9, so
# the window has to be at least that wide.
LEAF_SLAB_HALF_WIDTH = 12.0
# A component that spans the full frame height and sits entirely inside the
# casing's depth is the frame's jamb liner, however close to the leaf's plane
# its centroid falls: at the hinge the two are coplanar by construction.
FULL_HEIGHT_UNITS = 200.0
CASING_DEPTH_UNITS = 5.6


def _components(mesh: bpy.types.Mesh) -> list[list[int]]:
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    seen: set[int] = set()
    groups: list[list[int]] = []
    for vert in bm.verts:
        if vert.index in seen:
            continue
        stack = [vert]
        seen.add(vert.index)
        group: list[int] = []
        while stack:
            current = stack.pop()
            group.append(current.index)
            for edge in current.link_edges:
                other = edge.other_vert(current)
                if other.index not in seen:
                    seen.add(other.index)
                    stack.append(other)
        groups.append(group)
    bm.free()
    return groups


def _carve(source: bpy.types.Object, keep: set[int], name: str) -> bpy.types.Object:
    """Copy the faces whose vertices are all in ``keep`` into a new object."""
    mesh = source.data.copy()
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    doomed = [v for v in bm.verts if v.index not in keep]
    bmesh.ops.delete(bm, geom=doomed, context='VERTS')
    bm.to_mesh(mesh)
    bm.free()
    part = bpy.data.objects.new(name, mesh)
    part.matrix_world = source.matrix_world
    bpy.context.collection.objects.link(part)
    return part


def _leaf_plane(verts: list[Vector]) -> tuple[float, Vector, Vector, Vector]:
    """Fit the leaf's plane from the vertices that are furthest from the frame.

    The frame stands in the asset's ``y = 0`` plane and the leaf is swung away
    from it, so the far third of the point cloud is leaf and nothing else. A 2x2
    PCA in XY gives the leaf's long axis; the frame is axis-aligned, so the
    difference between the two axes is the angle the artist left the door open.
    """
    lo = min(p.y for p in verts)
    hi = max(p.y for p in verts)
    cut = lo + 0.65 * (hi - lo)
    far = [p for p in verts if p.y < cut]
    cx = sum(p.x for p in far) / len(far)
    cy = sum(p.y for p in far) / len(far)
    sxx = sum((p.x - cx) ** 2 for p in far) / len(far)
    syy = sum((p.y - cy) ** 2 for p in far) / len(far)
    sxy = sum((p.x - cx) * (p.y - cy) for p in far) / len(far)
    angle = 0.5 * math.atan2(2.0 * sxy, sxx - syy)
    u = Vector((math.cos(angle), math.sin(angle), 0.0))
    n = Vector((-math.sin(angle), math.cos(angle), 0.0))
    return angle, Vector((cx, cy, 0.0)), u, n


def _split(source: bpy.types.Object) -> tuple[set[int], set[int], dict[str, Any]]:
    """Separate the swinging leaf from the fixed frame, and measure both.

    Two rules, because one is not enough:

    * **distance to the leaf's plane.** The leaf is a slab standing 60.84 deg
      away from the frame's plane, so everything within 12 units of that plane
      is leaf -- 12 rather than the slab's own 3.7 because both lever handles
      hang 6.5 units off the faces.
    * **the leaf's own height.** Two of the casing's caps -- the top and bottom
      faces of the right post -- land inside that 12-unit window purely because
      the post stands where the hinge does, and one of them sits at the asset's
      z = 264.89, above the leaf's 254.19. Taking the leaf's height from the
      0.5-99.5 percentile of its own vertices rather than from its extremes
      drops both, without needing to know the casing's layout first.

    The frame's jamb liner is excluded a third way: it spans the full casing
    height and stands entirely inside the casing's depth, which at the hinge is
    exactly where the leaf's plane runs.
    """
    matrix = source.matrix_world
    verts = [matrix @ v.co for v in source.data.vertices]
    angle, origin, u, n = _leaf_plane(verts)

    candidates: list[tuple[list[int], list[Vector]]] = []
    frame_ids: set[int] = set()
    for group in _components(source.data):
        points = [verts[i] for i in group]
        centre = sum(points, Vector()) / len(points)
        leaf_distance = abs((centre - origin).dot(n))
        z_span = max(p.z for p in points) - min(p.z for p in points)
        inside_casing = max(abs(p.y) for p in points) <= CASING_DEPTH_UNITS
        is_jamb_liner = z_span > FULL_HEIGHT_UNITS and inside_casing
        if leaf_distance < LEAF_SLAB_HALF_WIDTH and not is_jamb_liner:
            candidates.append((group, points))
        else:
            frame_ids.update(group)

    zs = sorted(p.z for _group, points in candidates for p in points)
    lo = zs[int(0.005 * (len(zs) - 1))]
    hi = zs[int(0.995 * (len(zs) - 1))]
    leaf_ids: set[int] = set()
    for group, points in candidates:
        if max(p.z for p in points) > hi + 2.0 or min(p.z for p in points) < lo - 2.0:
            frame_ids.update(group)
        else:
            leaf_ids.update(group)

    leaf_points = [verts[i] for i in sorted(leaf_ids)]
    along = [(p - origin).dot(u) for p in leaf_points]
    across = [(p - origin).dot(n) for p in leaf_points]
    t_lo, t_hi = min(along), max(along)
    end_lo = origin + u * t_lo
    end_hi = origin + u * t_hi
    # The hinge is the end that stands nearest the frame's own plane.
    hinge = end_lo if abs(end_lo.y) < abs(end_hi.y) else end_hi
    across_mid = (min(across) + max(across)) / 2.0
    measurement = {
        'angle_rad': angle,
        'plane_origin': origin,
        'width_units': t_hi - t_lo,
        'height_units': max(p.z for p in leaf_points) - min(p.z for p in leaf_points),
        'z_bottom': min(p.z for p in leaf_points),
        'thickness_units': max(across) - min(across),
        'hinge_units': Vector((hinge.x, hinge.y, 0.0)) + n * across_mid,
    }
    return leaf_ids, frame_ids, measurement


def _frame_opening(frame: bpy.types.Object) -> dict[str, float]:
    """The frame's own inner opening and outer box, in asset units.

    The casing is a closed hollow box, and only the planes that **span it** are
    its surfaces. Two things inside it are not:

    * the **door stop**, a liner 3.8 units proud of the right reveal that runs
      the casing's full height but only a third of its depth;
    * the **threshold**, a board across the bottom that is deeper and wider than
      the casing and sits entirely below 1 % of its height.

    Measuring from the nearest plane instead of the spanning one takes the stop
    for the reveal and the threshold's top for the head, which makes the
    opening 3.8 units narrow and 252 units short and drops the whole casing two
    metres into the floor. So: drop everything in the bottom 5 %, and keep only
    the planes whose cross-section covers at least 70 % of the widest one.
    """
    matrix = frame.matrix_world
    verts = [matrix @ v.co for v in frame.data.vertices]
    lo = Vector((min(p.x for p in verts), min(p.y for p in verts), min(p.z for p in verts)))
    hi = Vector((max(p.x for p in verts), max(p.y for p in verts), max(p.z for p in verts)))
    body = [p for p in verts if p.z > lo.z + 0.05 * (hi.z - lo.z)]
    middle = 0.5 * (lo.x + hi.x)

    def spanning_planes(axis: int, cross_axis: int, minimum_ratio: float) -> list[float]:
        buckets: dict[float, list[Vector]] = {}
        for point in body:
            buckets.setdefault(round(point[axis], 3), []).append(point)
        extents = {
            value: max(p[cross_axis] for p in points) - min(p[cross_axis] for p in points)
            for value, points in buckets.items()
        }
        widest = max(extents.values()) if extents else 0.0
        return sorted(v for v, e in extents.items() if e >= minimum_ratio * widest)

    xs = spanning_planes(0, 1, 0.7)
    left = [x for x in xs if x < middle]
    right = [x for x in xs if x > middle]
    inner_left = max(left) if left else lo.x
    inner_right = min(right) if right else hi.x

    zs = spanning_planes(2, 0, 0.7)
    head_zs = [z for z in zs if z > lo.z + 0.05 * (hi.z - lo.z)]
    return {
        'outer_lo': lo,
        'outer_hi': hi,
        'inner_left': inner_left,
        'inner_right': inner_right,
        'inner_top': min(head_zs) if head_zs else hi.z,
        'inner_bottom': lo.z,
    }


def _tame_materials(imported: Iterable[bpy.types.Object], emission: float, roughness_floor: float) -> None:
    """Same two fixes the room asset needs: no baked emission, no mirror gloss.

    The door is a painted surface; its atlas also carries the grubby threshold
    and the stone reveal, so the floor is only applied to materials that come in
    below it rather than being forced onto every slot.
    """
    for obj in imported:
        if obj.type != 'MESH':
            continue
        for slot in obj.material_slots:
            material = slot.material
            if material is None or not material.use_nodes:
                continue
            for node in material.node_tree.nodes:
                if node.type != 'BSDF_PRINCIPLED':
                    continue
                strength = node.inputs.get('Emission Strength')
                if strength is not None and not strength.is_linked:
                    strength.default_value = float(emission)
                rough = node.inputs.get('Roughness')
                if rough is not None and not rough.is_linked and rough.default_value < roughness_floor:
                    rough.default_value = float(roughness_floor)
                metallic = node.inputs.get('Metallic')
                if metallic is not None and not metallic.is_linked:
                    metallic.default_value = min(metallic.default_value, 0.05)


def _repose_leaf(
    leaf: bpy.types.Object,
    measurement: dict[str, Any],
    *,
    width_m: float,
    height_m: float,
) -> dict[str, Any]:
    """Put the leaf where the room's own leaf stood: +X, hinge on the origin.

    Order, as everywhere else in this scene: move the hinge to the origin,
    rotate the artist's open angle away, then scale, then drop onto the floor.
    The hinge stays at the object's **local** origin rather than at its world
    position, because the animation keys a single Z rotation and Blender turns an
    object about its own origin -- bake the world hinge into the mesh instead and
    the leaf swings about the room's origin, i.e. through the wall.
    """
    angle = float(measurement['angle_rad'])
    hinge = Vector(measurement['hinge_units'])
    width_units = float(measurement['width_units'])
    height_units = float(measurement['height_units'])
    z_bottom = float(measurement['z_bottom'])

    scale_z = height_m / height_units
    # The asset's own leaf is within a millimetre of the room door's aspect, so
    # the width fit is a 0.4 % nudge, not a stretch. Mirroring X is what turns
    # the leaf round to point +X from its hinge.
    scale_x = -width_m / width_units

    transform = (
        Matrix.Diagonal((scale_x, scale_z, scale_z, 1.0))
        @ Matrix.Rotation(-angle, 4, 'Z')
        @ Matrix.Translation(Vector((-hinge.x, -hinge.y, -z_bottom)))
    )
    leaf.data.transform(transform)
    # A negative X scale inverts the winding, so every face would render inside
    # out -- the leaf would read as a hollow shell with black creases.
    leaf.data.flip_normals()
    leaf.data.update()
    leaf.location = (0.0, 0.0, 0.0)
    leaf.rotation_mode = 'XYZ'

    posed = [leaf.data.vertices[i].co for i in range(len(leaf.data.vertices))]
    xs = [p.x for p in posed]
    ys = [p.y for p in posed]
    zs = [p.z for p in posed]
    # Centre the slab on the collision box rather than on its own mouldings: the
    # handle hangs off one face and would otherwise bias the leaf off the plane
    # the simulator collides with.
    mid = (min(ys) + max(ys)) / 2.0
    shell = [p for p in posed if abs(p.y - mid) < 0.02]
    if shell:
        mid = (min(p.y for p in shell) + max(p.y for p in shell)) / 2.0
    bmesh.ops_hint = None  # keep linters quiet; no-op
    offset = Vector((0.0, -mid, 0.0))
    leaf.data.transform(Matrix.Translation(offset))
    leaf.data.update()
    posed = [v.co for v in leaf.data.vertices]
    xs = [p.x for p in posed]
    ys = [p.y for p in posed]
    zs = [p.z for p in posed]
    leaf_info = {
        'leaf_x_m': [round(min(xs), 4), round(max(xs), 4)],
        'leaf_y_m': [round(min(ys), 4), round(max(ys), 4)],
        'leaf_z_m': [round(min(zs), 4), round(max(zs), 4)],
        'scale_x': round(scale_x, 6),
        'scale_z': round(scale_z, 6),
        'slab_offset_m': round(-mid, 5),
        'asset_open_deg': round(math.degrees(angle), 2),
    }
    return leaf_info


def _place_frame(
    frame: bpy.types.Object,
    opening: dict[str, float],
    measurement: dict[str, Any],
    spec: dict[str, Any],
    *,
    leaf_width_m: float,
    aperture: tuple[Vector, Vector],
    wall: dict[str, Any] | None,
    floor_z: float,
) -> dict[str, Any]:
    """Scale the casing so its architrave frames the aperture, then drop it in.

    Three constraints, in order of hardness:

    * the **inner opening must clear the swinging leaf**, so it is sized from
      ``frame_opening_width_m`` rather than from the aperture, and must stay
      wider than the leaf at its smallest opening angle;
    * the **architrave must cover the aperture's edges** and the thin lip the
      room asset leaves around them, so the outer box is checked against
      ``aperture``;
    * the **front face must sit on the wall**, so the casing reads as trim
      rather than as a box hanging in the hole. The bedroom's doorway is cut
      into a splayed panel, so "on the wall" means on *that panel's* plane: with
      ``wall`` supplied the casing is yawed onto the panel's normal, which is
      what makes its architrave meet the plaster instead of standing off it on
      one side.

    The asset's frame is proportionally taller than the room's doorway -- 264.9
    units of casing around a 254.2 opening against 2.08 m of hole -- so the
    casing is sunk below the floor until its opening head lands on the
    aperture's top. That is invisible: the legs simply continue under the
    floorboards, and it buys a uniform scale, hence a uniform architrave.
    """
    inner_width = opening['inner_right'] - opening['inner_left']
    inner_height = opening['inner_top'] - opening['inner_bottom']
    outer_width = opening['outer_hi'].x - opening['outer_lo'].x
    outer_height = opening['outer_hi'].z - opening['outer_lo'].z

    target_opening = float(spec.get('frame_opening_width_m') or (leaf_width_m + 0.055))
    scale = target_opening / inner_width
    if scale <= 0.0:
        raise RuntimeError('frame inner opening measures zero; the asset has changed')

    aperture_lo, aperture_hi = aperture
    centre_x = 0.5 * (aperture_lo.x + aperture_hi.x)
    opening_centre_asset = 0.5 * (opening['inner_left'] + opening['inner_right'])
    top_z = float(aperture_hi.z)

    depth = spec.get('frame_depth_m')
    if depth is not None:
        depth_units = opening['outer_hi'].y - opening['outer_lo'].y
        scale_y = float(depth) / depth_units
    else:
        scale_y = scale

    yaw = float(spec.get('frame_yaw_deg') or 0.0)
    pivot_asset = Vector((opening_centre_asset, opening['outer_hi'].y, opening['inner_top']))
    proud = float(spec.get('frame_front_proud_m') or 0.0)
    if wall is not None:
        normal = Vector(wall['normal'])
        yaw = float(wall['yaw_deg'])
        # Slide the pivot onto the panel's plane along its own normal, so the
        # architrave's face is coplanar with the plaster however the panel is
        # turned; then back it off by the proudness.
        target = Vector((centre_x, 0.0, top_z))
        target.y = (wall['offset'] - normal.x * target.x) / normal.y
        target += normal * proud
    else:
        front_y = spec.get('frame_front_y_m')
        if front_y is None:
            front_y = aperture_hi.y
        target = Vector((centre_x, float(front_y) + proud, top_z))

    transform = (
        Matrix.Translation(target)
        @ Matrix.Rotation(math.radians(yaw), 4, 'Z')
        @ Matrix.Diagonal((scale, scale_y, scale, 1.0))
        @ Matrix.Translation(-pivot_asset)
    )
    frame.data.transform(transform)
    frame.data.update()
    frame.location = (0.0, 0.0, 0.0)

    verts = [v.co for v in frame.data.vertices]
    lo = Vector((min(p.x for p in verts), min(p.y for p in verts), min(p.z for p in verts)))
    hi = Vector((max(p.x for p in verts), max(p.y for p in verts), max(p.z for p in verts)))
    info = {
        'outer_x_m': [round(lo.x, 4), round(hi.x, 4)],
        'outer_y_m': [round(lo.y, 4), round(hi.y, 4)],
        'outer_z_m': [round(lo.z, 4), round(hi.z, 4)],
        'opening_width_m': round(inner_width * scale, 4),
        'opening_height_m': round(inner_height * scale, 4),
        'architrave_width_m': round((outer_width - inner_width) * scale / 2.0, 4),
        'architrave_head_m': round((outer_height - inner_height) * scale, 4),
        'depth_m': round((opening['outer_hi'].y - opening['outer_lo'].y) * scale_y, 4),
        'yaw_deg': round(yaw, 3),
        'from_wall_plane': wall is not None,
        'scale': [round(scale, 6), round(scale_y, 6)],
        'sunk_below_floor_m': round(floor_z - (top_z - inner_height * scale), 4),
        'leaf_width_m': round(leaf_width_m, 4),
        'asset_open_deg': round(math.degrees(float(measurement['angle_rad'])), 2),
    }
    return info


def _paint_material(spec: dict[str, Any]) -> bpy.types.Material:
    """Satin painted timber, with only a very fine surface grain."""
    material = bpy.data.materials.new('door_satin_paint')
    material.use_nodes = True
    nodes = material.node_tree.nodes
    bsdf = nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (*spec.get('paint_color', [0.64, 0.61, 0.55]), 1.0)
    bsdf.inputs['Roughness'].default_value = 0.48
    noise = nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = 180.0
    noise.inputs['Detail'].default_value = 2.0
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.12
    bump.inputs['Distance'].default_value = 0.00025
    material.node_tree.links.new(noise.outputs['Fac'], bump.inputs['Height'])
    material.node_tree.links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    return material


def _refinish_leaf(leaf: bpy.types.Object, paint: bpy.types.Material, height: float, width: float) -> None:
    """Keep the modelled panels and metalwork; replace the baked dirty paint."""
    paint_index = len(leaf.data.materials)
    leaf.data.materials.append(paint)
    hardware: set[int] = set()
    scraps: set[int] = set()
    for group in _components(leaf.data):
        points = [leaf.data.vertices[i].co for i in group]
        lo = [min(p[k] for p in points) for k in range(3)]
        hi = [max(p[k] for p in points) for k in range(3)]
        # Disconnected casing end caps also intersect the leaf's fitted plane.
        if hi[0] < width * 0.15 and (hi[2] < 0.025 or lo[2] > height - 0.005):
            scraps.update(group)
        is_handle = lo[0] > width * 0.75 and lo[2] > height * 0.46 and hi[2] < height * 0.57
        is_hinge = hi[0] < width * 0.10 and hi[2] - lo[2] < height * 0.04 and lo[2] > 0.1
        if is_handle or is_hinge:
            hardware.update(group)
    for poly in leaf.data.polygons:
        if not all(i in hardware for i in poly.vertices):
            poly.material_index = paint_index
    if scraps:
        bm = bmesh.new()
        bm.from_mesh(leaf.data)
        bm.verts.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=[bm.verts[i] for i in scraps], context='VERTS')
        bm.to_mesh(leaf.data)
        bm.free()
    leaf.data.update()


def fit_leaf_to_collision(leaf, width, height, thickness, bottom):
    """Fit the painted timber, excluding hardware, to the hinge collision slab.

    The imported casing fragments previously biased the fit, leaving 75 mm
    of empty space at the hinge and a small yaw error. The large timber faces
    provide the actual panel axis and bounds. The hinge is on the front edge:
    local timber spans x=[0,width], y=[-thickness,0].
    """
    panel = max(leaf.data.polygons, key=lambda p: p.area)
    normal = panel.normal.copy()
    if normal.y < 0:
        normal.negate()
    yaw = math.atan2(-normal.x, normal.y)
    leaf.data.transform(Matrix.Rotation(-yaw, 4, 'Z'))
    leaf.data.update()
    body_ids = {i for p in leaf.data.polygons if p.area > 0.005 for i in p.vertices}
    points = [leaf.data.vertices[i].co for i in body_ids]
    lo = Vector(tuple(min(p[k] for p in points) for k in range(3)))
    hi = Vector(tuple(max(p[k] for p in points) for k in range(3)))
    scale = Vector((width / (hi.x - lo.x), thickness / (hi.y - lo.y), height / (hi.z - lo.z)))
    transform = (Matrix.Translation((0, -thickness, bottom))
                 @ Matrix.Diagonal((*scale, 1)) @ Matrix.Translation(-lo))
    leaf.data.transform(transform)
    leaf.data.update()
    return {'corrected_panel_yaw_deg': math.degrees(yaw),
            'body_bounds_local': [[0, width], [-thickness, 0], [bottom, bottom + height]]}


def _fitted_frame(spec, aperture, wall, floor_z, paint):
    """Thin architrave on the plaster plane, independently of the reveal depth.

    The opening is measured in world X, while the trim is measured along the
    splayed wall. Projecting its width avoids exposing the carved aperture.
    """
    lo, hi = aperture
    yaw = math.radians(float(wall['yaw_deg'])) if wall else 0.0
    normal = Vector(wall['normal']) if wall else Vector((0, 1, 0))
    centre_x = (lo.x + hi.x) * 0.5
    front_y = ((wall['offset'] - normal.x * centre_x) / normal.y
               if wall else float(spec.get('frame_front_y_m', hi.y)))
    origin = Vector((centre_x, front_y, floor_z))
    rotation = Matrix.Rotation(yaw, 4, 'Z')
    half = (hi.x - lo.x) / (2.0 * math.cos(yaw))
    height = hi.z - floor_z
    trim = float(spec.get('frame_trim_width_m', 0.065))
    proud = float(spec.get('frame_front_proud_m', 0.018))
    parts = []

    def board(name, x0, x1, z0, z1, y0, y1):
        bpy.ops.mesh.primitive_cube_add(size=1)
        obj = bpy.context.object
        obj.name = name
        obj.dimensions = (x1 - x0, y1 - y0, z1 - z0)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        obj.location = origin + rotation @ Vector(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
        obj.rotation_euler.z = yaw
        obj.data.materials.append(paint)
        bevel = obj.modifiers.new('Soft painted edges', 'BEVEL')
        bevel.width = 0.0015
        bevel.segments = 3
        obj.modifiers.new('Corner normals', 'WEIGHTED_NORMAL')
        parts.append(obj)

    # Optional surface architrave; the recessed liners also work on their own.
    architrave = bool(spec.get('frame_architrave', True))
    if architrave:
        for side, a, b in [('left', -half - trim, -half), ('right', half, half + trim)]:
            board(f'door_frame_{side}', a, b, 0, height, -0.006, proud)
            bead_a = b - 0.009 if side == 'left' else a
            board(f'door_frame_{side}_bead', bead_a, bead_a + 0.009, 0, height, proud - 0.002, proud + 0.004)
        board('door_frame_head', -half - trim, half + trim, height, height + trim, -0.006, proud)
        board('door_frame_head_bead', -half, half, height, height + 0.009, proud - 0.002, proud + 0.004)
    # The reveal is a shallow liner behind the trim, never a scaled display box.
    depth = float(spec.get('frame_reveal_depth_m', 0.075))
    if not architrave:
        paint = paint.copy()
        paint.name = 'door_reveal_plaster'
        bsdf = paint.node_tree.nodes.get('Principled BSDF')
        bsdf.inputs['Base Color'].default_value = (*spec.get('reveal_color', [0.52, 0.50, 0.46]), 1.0)
        bsdf.inputs['Roughness'].default_value = 0.78
    liner_front = 0.001 if architrave else -0.004
    for side, a, b in [('left', -half - 0.018, -half), ('right', half, half + 0.018)]:
        board(f'door_frame_{side}_liner', a, b, 0, height, -depth, liner_front)
    board('door_frame_head_liner', -half, half, height, height + 0.018, -depth, liner_front)
    return parts[0], {'construction': 'fitted_trim', 'opening_width_m': round(half * 2, 4),
                      'opening_height_m': round(height, 4), 'architrave_width_m': trim,
                      'front_proud_m': proud if architrave else 0.0, 'reveal_depth_m': depth,
                      'architrave_enabled': architrave,
                      'yaw_deg': round(math.degrees(yaw), 3)}


def strip_room_casing(
    room: Iterable[bpy.types.Object],
    *,
    box_lo: Vector,
    box_hi: Vector,
) -> int:
    """Delete the room asset's own door casing, so the new frame can own the opening.

    ``cloe_room.glb`` builds its doorway as a casing **box**: two architrave
    faces, a 0.56 m reveal and a stop, all standing proud of the wall on the
    splayed panel the door is cut into. Dropping the door asset's frame inside
    that leaves one casing hiding the other -- measured, the room's stands
    1.8 cm proud, so a frame set flush to the plaster is completely invisible
    and one set in front of it reads as a second architrave.

    So the room's casing goes. It is identified component by component -- a
    connected island whose every vertex falls inside the doorway's own box --
    which keeps the window, which shares the same ``do&win`` mesh, and every
    wall panel, whose faces run far past that box, untouched.
    """
    total = 0
    for obj in room:
        if obj.type != 'MESH':
            continue
        matrix = obj.matrix_world
        doomed: set[int] = set()
        for group in _components(obj.data):
            points = [matrix @ obj.data.vertices[i].co for i in group]
            if all(
                box_lo[k] - 1e-4 <= point[k] <= box_hi[k] + 1e-4
                for point in points
                for k in range(3)
            ):
                doomed.update(group)
        if not doomed:
            continue
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.index in doomed], context='VERTS')
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
        total += len(doomed)
        print(f'[door] removed {len(doomed)} casing verts from {obj.name}')
    print(f'[door] room casing stripped: {total} verts')
    return total


def build_door_from_asset(
    path,
    spec: dict[str, Any],
    *,
    leaf_width_m: float,
    leaf_height_m: float,
    hinge_world: Vector,
    floor_z: float,
    aperture: tuple[Vector, Vector],
    wall: dict[str, Any] | None = None,
) -> tuple[bpy.types.Object | None, bpy.types.Object | None, dict[str, Any]]:
    """Import the door asset and return its leaf and frame as scene objects."""
    previous = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    bpy.context.view_layer.update()
    imported = [o for o in bpy.data.objects if o not in previous]
    for obj in imported:
        obj.animation_data_clear()
    _tame_materials(
        imported,
        float(spec.get('emission_scale', 0.0)),
        float(spec.get('roughness_min', 0.35)),
    )

    meshes = [o for o in imported if o.type == 'MESH']
    if len(meshes) != 1:
        raise RuntimeError(f'{path} has {len(meshes)} meshes; this loader expects one')
    source = meshes[0]
    # glTF wraps the mesh in empties that carry the exporter's unit scaling and
    # the Y-up -> Z-up correction. Everything below is written in the asset's
    # own world space, so bake that chain into the mesh and cut the parent: left
    # in place the hinge translation lands in local space and the leaf ends up
    # 2 m below the floor.
    world = source.matrix_world.copy()
    source.parent = None
    source.data.transform(world)
    source.matrix_world = Matrix.Identity(4)
    bpy.context.view_layer.update()

    leaf_ids, frame_ids, measurement = _split(source)
    print(
        f'[door] asset {path.name}: leaf {len(leaf_ids)} verts of {len(source.data.vertices)}, '
        f'frame {len(frame_ids)}, artist left it {math.degrees(measurement["angle_rad"]):.2f} deg open, '
        f'leaf {measurement["width_units"]:.2f} x {measurement["height_units"]:.2f} units '
        f'({measurement["thickness_units"]:.2f} thick), hinge at '
        f'({measurement["hinge_units"].x:.2f}, {measurement["hinge_units"].y:.2f})'
    )

    leaf = _carve(source, leaf_ids, 'door_leaf')
    leaf.data.name = 'door_leaf'
    for slot in source.material_slots:
        if slot.material is not None and slot.material.name not in leaf.data.materials:
            leaf.data.materials.append(slot.material)

    leaf_info = _repose_leaf(
        leaf,
        measurement,
        width_m=leaf_width_m,
        height_m=leaf_height_m,
    )
    print(
        f'[door] leaf -> x{leaf_info["leaf_x_m"]} y{leaf_info["leaf_y_m"]} z{leaf_info["leaf_z_m"]} '
        f'(scale {leaf_info["scale_x"]:.5f} x {leaf_info["scale_z"]:.5f})'
    )

    frame = None
    frame_info: dict[str, Any] = {}
    fitted = spec.get('frame_style') == 'fitted'
    paint = _paint_material(spec) if fitted else None
    if fitted:
        _refinish_leaf(leaf, paint, leaf_height_m, leaf_width_m)
    keep_frame = bool(spec.get('frame_enabled', True))
    if keep_frame and fitted:
        frame, frame_info = _fitted_frame(spec, aperture, wall, floor_z, paint)
        print(f'[door] fitted frame: {frame_info}')
    elif keep_frame and frame_ids:
        frame = _carve(source, frame_ids, 'door_frame')
        frame.data.name = 'door_frame'
        for slot in source.material_slots:
            if slot.material is not None and slot.material.name not in frame.data.materials:
                frame.data.materials.append(slot.material)
        opening = _frame_opening(frame)
        frame_info = _place_frame(
            frame,
            opening,
            measurement,
            spec,
            leaf_width_m=leaf_width_m,
            aperture=aperture,
            wall=wall,
            floor_z=floor_z,
        )
        print(
            f'[door] frame -> x{frame_info["outer_x_m"]} y{frame_info["outer_y_m"]} '
            f'z{frame_info["outer_z_m"]}, opening {frame_info["opening_width_m"]:.3f} x '
            f'{frame_info["opening_height_m"]:.3f} m, architrave {frame_info["architrave_width_m"]:.3f} m '
            f'side / {frame_info["architrave_head_m"]:.3f} m head, yaw {frame_info["yaw_deg"]:+.2f} deg, '
            f'sunk {frame_info["sunk_below_floor_m"]:.3f} m'
        )

    for obj in imported:
        if obj is not leaf and obj is not frame and obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    bpy.context.view_layer.update()
    return leaf, frame, {'leaf': leaf_info, 'frame': frame_info}

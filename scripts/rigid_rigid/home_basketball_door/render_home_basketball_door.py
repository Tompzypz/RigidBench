"""Build the home_basketball_door scene in Blender, solve it in PyBullet, render it.

The renderer owns the geometry. It imports the bedroom, cuts the door leaf out
of the room's own ``do&win`` mesh, measures it, and hands the hinge and the
leaf's dimensions to the simulator, so the door that swings on screen is the
door that was solved. The ball is rescaled to a real 24.2 cm basketball.

The room asset ships the door already ajar by 26.2 deg about its own left
jamb. That is measured, not assumed: the leaf's own vertices give the hinge
line and the leaf plane, and the scene re-poses the leaf from that plane, so
``door_start_angle_deg`` in scenario.json is the real angle from closed rather
than an offset from whatever the asset happened to do.

The ball can only push the leaf towards closed -- it is thrown from inside the
room at the room-facing face -- so the swing is 45 deg down to a hair short of
the jamb, not open.

Run with the repository's render runtime (bpy is installed there):
    .runtime/render/Scripts/python.exe scripts/home_basketball_door/render_home_basketball_door.py --mode keyframes

or through Blender:
    blender -b --python scripts/home_basketball_door/render_home_basketball_door.py -- --mode animation

Modes:
    build      write the .blend, the trajectory and the metadata, render nothing
    preview    frame 1, the impact frame and the last frame
    keyframes  the frames in layout.keyframes (default: 9 frames across the clip)
    frames     every frame as PNG
    animation  the 4 s MP4
"""
# PCVE_UNIFIED_ENTRY_BEGIN

from __future__ import annotations

# Resolve the shared scripts directory, then this scene's module folders.
import sys as _clean_sys
from pathlib import Path as _CleanPath
_clean_scene_dir = _CleanPath(__file__).resolve().parent
_scripts_dir = _clean_scene_dir.parents[1]
_PCVE_PROJECT_ROOT = next(p for p in _clean_scene_dir.parents if (p / "assets").is_dir())
if str(_scripts_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_scripts_dir))
if str(_clean_scene_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_clean_scene_dir))
# Shared modules live in scripts/; scene-local modules live in this directory and
# its physics/, appearance/ and tools/ subdirectories.
for _scene_sub in ("", "physics", "appearance", "tools"):
    _scene_sub_dir = _clean_scene_dir / _scene_sub if _scene_sub else _clean_scene_dir
    if _scene_sub_dir.is_dir() and str(_scene_sub_dir) not in _clean_sys.path:
        _clean_sys.path.insert(1, str(_scene_sub_dir))
# PCVE_UNIFIED_ENTRY_END





import sys
from pathlib import Path
from pcve_blender_compat import (shader_socket, set_shader_input, eevee_engine, set_eevee_property, set_color_property)

import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

import bpy
import bmesh
from mathutils import Matrix, Quaternion, Vector

HERE = Path(__file__).resolve().parent
ROOT = _PCVE_PROJECT_ROOT
import scene_config, door_asset  # noqa: E402

MODEL_DIRS = (ROOT / 'assets' / 'models',)
RESOLVED_NAME = 'resolved_scenario.json'
TRAJECTORY_NAME = 'physics_transforms.json'
GROUND_TRUTH_NAME = 'ground_truth_transforms.json'
METADATA_NAME = 'scenario_metadata.json'
LEAF_NAME = 'door_leaf.json'


from pcve_scene_runtime import parse_render_args, run_renderer

def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        '--mode',
        choices=('build', 'preview', 'keyframes', 'frames', 'animation'),
        default='preview',
    )
    parser.add_argument('--out-dir', type=Path, default=ROOT / 'renders' / 'home_basketball_door')
    parser.add_argument('--models-dir', type=Path, default=None)
    parser.add_argument('--scenario', type=Path, default=None)
    parser.add_argument('--scenario-overrides-json', type=Path, default=None)
    parser.add_argument('--physics-python', type=Path, default=None)
    parser.add_argument('--resolution', nargs=2, type=int, default=[1280, 720])
    parser.add_argument('--fps', type=int, default=None)
    parser.add_argument('--duration-sec', type=float, default=None)
    parser.add_argument('--samples', type=int, default=96)
    parser.add_argument('--device', choices=('auto', 'cpu'), default='auto')
    parser.add_argument('--keyframes', default=None, help='comma-separated frame numbers')
    return parse_render_args(parser, argv)


# ------------------------------------------------------------------- assets


def model_path(name: str, args: argparse.Namespace) -> Path:
    directories = (args.models_dir,) if args.models_dir else MODEL_DIRS
    for directory in directories:
        candidate = Path(directory) / name
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f'{name} not found in {[str(d) for d in directories]}. '
        'Pass --models-dir with the directory that holds the GLBs.'
    )


def import_glb(path: Path) -> list[bpy.types.Object]:
    previous = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    bpy.context.view_layer.update()
    imported = [o for o in bpy.data.objects if o not in previous]
    # Some GLBs carry turntable/NLA animation. Left in place those keys fight
    # the physics keys written further down.
    for obj in imported:
        obj.animation_data_clear()
        if obj.data is not None and hasattr(obj.data, 'animation_data_clear'):
            obj.data.animation_data_clear()
    return imported


def drop_imported_cameras_and_lights(imported: Iterable[bpy.types.Object]) -> list[str]:
    """The room GLB carries FBX lamps with unscaled intensities.

    ``Area``, ``Area.001`` and ``Area.002`` are empty nodes in the asset that
    the original artist used as light placeholders; they come in as empties and
    do nothing, but the cameras and lamps that some exports carry would. They
    are removed before anything is framed.
    """
    removed = []
    for obj in list(imported):
        if obj.type in {'CAMERA', 'LIGHT'}:
            removed.append(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)
    return removed


def tame_glb_emission(imported: Iterable[bpy.types.Object], layout: dict[str, Any]) -> int:
    """Turn off the emission glTF bakes into every material it imports.

    glTF's ``emissiveFactor`` imports as Emission Colour 1,1,1 with Emission
    Strength 1.0. This asset's material names are all ``None.00x`` -- there is
    no name to whitelist a window or a lamp on -- so the scene simply sets the
    whole room to ``glb_emission_scale`` (0) and lights it itself.
    """
    scale = float(layout.get('glb_emission_scale', 0.0))
    seen = 0
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
                if strength is not None:
                    strength.default_value = scale
            seen += 1
    return seen


def tame_glb_gloss(imported: Iterable[bpy.types.Object], layout: dict[str, Any]) -> int:
    """Floor the roughness of the room's flat-shaded stylised materials.

    The asset is low-poly with a painted wood floor and blue lacquered closet
    doors. Under the area lights those come back as broad specular sheens
    brighter than the door leaf. There is no useful material name to filter on,
    so every material gets the same floor.
    """
    floor = float(layout.get('glb_roughness_min', 0.55))
    seen = 0
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
                rough = node.inputs.get('Roughness')
                metallic = node.inputs.get('Metallic')
                if rough is not None and not rough.is_linked and rough.default_value < floor:
                    rough.default_value = floor
                if metallic is not None and not metallic.is_linked:
                    metallic.default_value = min(metallic.default_value, 0.05)
            seen += 1
    return seen


def import_room(path: Path, layout: dict[str, Any]) -> list[bpy.types.Object]:
    imported = import_glb(path)
    removed = drop_imported_cameras_and_lights(imported)
    tamed = tame_glb_emission(imported, layout)
    gloss = tame_glb_gloss(imported, layout)
    print(f'[scene] emission off on {tamed} material slots, roughness floored on {gloss}')
    scale = float(layout['room_scale'])
    offset = Vector([float(v) for v in layout['room_offset']])
    for obj in imported:
        if obj.parent is not None:
            continue
        obj.scale = tuple(component * scale for component in obj.scale)
        obj.location = Vector(obj.location) + offset
    bpy.context.view_layer.update()
    return imported


# -------------------------------------------------------------- door leaf


def connected_components(mesh: bpy.types.Mesh) -> list[set[int]]:
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    seen: set[int] = set()
    components: list[set[int]] = []
    for vert in bm.verts:
        if vert.index in seen:
            continue
        stack = [vert]
        seen.add(vert.index)
        group: set[int] = set()
        while stack:
            current = stack.pop()
            group.add(current.index)
            for edge in current.link_edges:
                other = edge.other_vert(current)
                if other.index not in seen:
                    seen.add(other.index)
                    stack.append(other)
        components.append(group)
    bm.free()
    return components


def bake_vertices(obj: bpy.types.Object, keep: set[int], name: str) -> bpy.types.Object:
    """Copy the faces whose vertices are all in ``keep`` into a world-space object."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    doomed = [v for v in bm.verts if v.index not in keep]
    bmesh.ops.delete(bm, geom=doomed, context='VERTS')
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    mesh.transform(obj.matrix_world)
    part = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(part)
    for slot in obj.material_slots:
        part.data.materials.append(slot.material)
    return part


def strip_vertices(obj: bpy.types.Object, doomed: set[int]) -> None:
    """Delete one connected component from an object, leaving the rest intact."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bmesh.ops.delete(
        bm, geom=[v for v in bm.verts if v.index in doomed], context='VERTS'
    )
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def world_vertices(obj: bpy.types.Object) -> list[Vector]:
    matrix = obj.matrix_world
    return [matrix @ v.co for v in obj.data.vertices]


def principal_axis(points: list[Vector]) -> Vector:
    """Long axis of a flat-ish point cloud, in the XY plane (2x2 PCA)."""
    cx = sum(p.x for p in points) / len(points)
    cy = sum(p.y for p in points) / len(points)
    sxx = sum((p.x - cx) ** 2 for p in points) / len(points)
    syy = sum((p.y - cy) ** 2 for p in points) / len(points)
    sxy = sum((p.x - cx) * (p.y - cy) for p in points) / len(points)
    # Eigenvector of the larger eigenvalue of [[sxx, sxy], [sxy, syy]].
    trace = sxx + syy
    det = sxx * syy - sxy * sxy
    root = math.sqrt(max(trace * trace / 4.0 - det, 0.0))
    major = trace / 2.0 + root
    if abs(sxy) > 1e-9:
        vector = Vector((major - syy, sxy))
    else:
        vector = Vector((1.0, 0.0)) if sxx >= syy else Vector((0.0, 1.0))
    vector.normalize()
    return vector


def extract_door_leaf(room: list[bpy.types.Object], scenario: dict[str, Any]) -> tuple[bpy.types.Object, dict[str, Any]]:
    """Cut the door leaf out of the room's door/window mesh and stand it up closed.

    The room keeps its door and window trim, glass and frames in one mesh named
    ``do&win``; the leaf is one connected component of it, and the rest of that
    mesh is the casing around the aperture. ``door_leaf_bbox_model`` is the
    measured box that leaf lives in (in the asset's own units), so the leaf is
    the component whose every vertex falls inside it -- the casing pieces all
    stick out past it. The leaf's faces are then removed from the room mesh, so
    the room keeps its casing and the moving leaf is not drawn twice.

    The leaf is re-posed: its own long axis becomes +X and the hinge line (the
    end nearest ``door_hinge_model_xyz``) becomes the object's origin. That
    makes the animation one rotation about the object's Z, and it makes
    ``door_start_angle_deg`` mean what it says no matter how the asset had the
    door standing.
    """
    layout = scenario['layout']
    node = str(layout['door_source_node'])
    source = next(
        (o for o in room if o.type == 'MESH' and node in o.name and o.parent and node in o.parent.name),
        None,
    )
    if source is None:
        candidates = [o.name for o in room if o.type == 'MESH']
        raise RuntimeError(f'room GLB has no mesh under node {node!r}; meshes are {candidates}')
    source_name = source.name

    box = layout['door_leaf_bbox_model']
    lo = Vector([float(box[axis][0]) for axis in 'xyz'])
    hi = Vector([float(box[axis][1]) for axis in 'xyz'])
    scale = float(layout['room_scale'])
    offset = Vector([float(v) for v in layout['room_offset']])
    lo = lo * scale + offset
    hi = hi * scale + offset

    best: set[int] | None = None
    for component in connected_components(source.data):
        points = [source.matrix_world @ source.data.vertices[i].co for i in component]
        inside = all(
            lo[k] - 1e-4 <= min(p[k] for p in points) and max(p[k] for p in points) <= hi[k] + 1e-4
            for k in range(3)
        )
        if inside and (best is None or len(component) > len(best)):
            best = component
    if best is None:
        raise RuntimeError(
            f'no connected component of {source_name!r} lies inside door_leaf_bbox_model; '
            'the room asset or that box has changed'
        )
    leaf = bake_vertices(source, best, 'door_leaf')
    print(f'[scene] door leaf: {len(best)} vertices lifted out of {source_name}')
    strip_vertices(source, best)

    points = world_vertices(leaf)
    axis = principal_axis(points)
    centre = Vector((sum(p.x for p in points) / len(points), sum(p.y for p in points) / len(points), 0.0))
    reach = [(p - centre).dot(Vector((axis.x, axis.y, 0.0))) for p in points]
    end_lo = centre + Vector((axis.x, axis.y, 0.0)) * min(reach)
    end_hi = centre + Vector((axis.x, axis.y, 0.0)) * max(reach)
    hint = Vector([float(v) for v in layout['door_hinge_model_xyz']]) * scale + offset
    hinge = end_lo if (end_lo - hint).length < (end_hi - hint).length else end_hi
    free = end_hi if hinge is end_lo else end_lo
    direction = Vector((free.x - hinge.x, free.y - hinge.y, 0.0))
    width = direction.length
    direction.normalize()
    yaw = math.atan2(direction.y, direction.x)
    z_bottom = min(p.z for p in points)

    # Closed pose: long axis along +X, hinge line at the origin, standing on
    # the floor that the room itself was measured against.
    #
    # Order matters. The pose is "rotate about the hinge, then drop to the
    # floor", i.e. R (v - hinge). Writing it as Translation(-hinge) @ Rotation
    # would rotate about the world origin first and then subtract the hinge,
    # which leaves the leaf the right way up but parked 2.5 m down the room --
    # the exact bug this scene shipped with once.
    transform = (
        Matrix.Translation(Vector((0.0, 0.0, -z_bottom)))
        @ Matrix.Rotation(-yaw, 4, 'Z')
        @ Matrix.Translation(Vector((-hinge.x, -hinge.y, 0.0)))
    )
    leaf.data.transform(transform)
    leaf.data.update()
    leaf.location = (0.0, 0.0, 0.0)
    leaf.rotation_mode = 'XYZ'

    posed = world_vertices(leaf)
    local_lo = min(p.x for p in posed)
    if abs(local_lo) > 1e-3:
        raise RuntimeError(
            f'the re-posed leaf starts at x={local_lo:.4f} instead of 0; '
            'the hinge-based re-pose is wrong'
        )
    height = max(p.z for p in posed) - min(p.z for p in posed)
    thicken_leaf(leaf, float(scenario['physics']['door_thickness_m']))
    print(
        f'[scene] door leaf {width:.4f} x {height:.4f} m, asset had it {math.degrees(yaw):.2f} deg from closed, '
        f'hinge at ({hinge.x:.3f}, {hinge.y:.3f}, {z_bottom:.3f})'
    )
    info = {
        'width_m': round(width, 5),
        'height_m': round(height, 5),
        'thickness_m': float(scenario['physics']['door_thickness_m']),
        'hinge_world': [round(v, 5) for v in (hinge.x, hinge.y, z_bottom)],
        'asset_open_angle_deg': round(math.degrees(yaw), 3),
        'vertex_count': len(leaf.data.vertices),
        'source_node': node,
    }
    return leaf, info


def thicken_leaf(leaf: bpy.types.Object, thickness: float) -> None:
    """Give the leaf the thickness its collision box already has.

    The asset's door is a **single zero-thickness sheet**: 18 vertices, every
    one of them within 0.3 mm of y = 0, 20 triangles, all normals +Y. Rendered
    as-is it is a sheet of paper -- it has no edge to catch the light and it
    looks nothing like the 45 mm slab the simulator collides with.

    Two steps, and the first is not cosmetic. The sheet is flattened onto y = 0
    *before* it is solidified: the asset's own 0.3 mm of warp is invisible on the
    sheet but, once solidified, it tilts every rim face by a slightly different
    amount, and the leaf's edge renders as a ladder of alternating light and dark
    rungs instead of one clean band. Measured on the first attempt: 0.28 mm of
    residual warp was enough to see at 640 px. A door is flat; make it flat.
    """
    me = leaf.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.normal_update()
    wobble = [v.co.y for v in bm.verts]
    plane = (min(wobble) + max(wobble)) / 2.0
    bmesh.ops.translate(bm, verts=bm.verts[:], vec=(0.0, -plane, 0.0))
    for vert in bm.verts:
        vert.co.y = 0.0
    bmesh.ops.solidify(bm, geom=bm.faces[:], thickness=float(thickness))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    ys = [v.co.y for v in bm.verts]
    middle = (min(ys) + max(ys)) / 2.0
    if abs(middle) > 1e-9:
        bmesh.ops.translate(bm, verts=bm.verts[:], vec=(0.0, -middle, 0.0))
    bm.to_mesh(me)
    bm.free()
    me.update()
    ys = [v.co.y for v in me.vertices]
    print(
        f'[scene] door leaf thickened: sheet -> {max(ys) - min(ys):.4f} m slab, '
        f'centred at y={((min(ys) + max(ys)) / 2):+.5f} (was {max(wobble) - min(wobble):.4f} m of warp, '
        f'now {len(me.vertices)} verts, {len(me.polygons)} faces)'
    )


# How far past the leaf plane the doorway cut reaches. ``away_m`` is measured
# away from the room, i.e. into the wall; measured on this asset, the room's
# backing sheets sit from 0.10 m to 0.53 m behind the leaf plane, so 0.58 m
# clears all of them without touching the wall past them.
DEFAULT_OPENING = {
    'side_m': 0.05,
    'to_room_m': 0.10,
    'away_m': 0.58,
    'top_m': 0.06,
    'bottom_m': 0.02,
}


def doorway_bounds(leaf_info: dict[str, Any], layout: dict[str, Any]) -> tuple[Vector, Vector]:
    """The world-space slab the door aperture has to be cut through."""
    opening = {**DEFAULT_OPENING, **dict(layout.get('doorway_opening') or {})}
    hx, hy, hz = (float(v) for v in leaf_info['hinge_world'])
    width, height = float(leaf_info['width_m']), float(leaf_info['height_m'])
    lo = Vector((
        hx - float(opening['side_m']),
        hy - float(opening['away_m']),
        hz - float(opening['bottom_m']),
    ))
    hi = Vector((
        hx + width + float(opening['side_m']),
        hy + float(opening['to_room_m']),
        hz + height + float(opening['top_m']),
    ))
    return lo, hi


def carve_doorway(room: list[bpy.types.Object], leaf_info: dict[str, Any], layout: dict[str, Any]) -> None:
    """Cut a real hole where the door is.

    The room asset has **no aperture**: the leaf hangs in front of a solid
    backing sheet. A ray walked into the doorway hits ``do&win_0`` 0.10 m behind
    the leaf plane with a -Y normal -- the underside of a panel facing the
    corridor -- and then the wall core at 0.44 m and 0.53 m. That is why the
    first render filled the opening with a grey card.

    Every face whose four vertices all sit inside the doorway slab goes, jamb
    included. Deleting the jamb is safe *because* the hallway is built flush
    with the room's inner wall face at the same cross-section: the hallway's own
    side walls stand exactly where the jamb was and carry the opening on into
    the distance, so the aperture never loses its depth. Carving the jamb and
    then leaving the hallway back in the wall would expose 0.58 m of wall
    material as a bright, structureless band across the whole opening -- which
    is what the first attempt at this looked like.

    All-vertices, not face-centre: a wall face that merely grazes the slab keeps
    its geometry. Floors and ceilings are skipped by name.
    """
    lo, hi = doorway_bounds(leaf_info, layout)
    print(
        f'[scene] doorway slab x[{lo.x:+.3f},{hi.x:+.3f}] y[{lo.y:+.3f},{hi.y:+.3f}] '
        f'z[{lo.z:+.3f},{hi.z:+.3f}]'
    )
    total = 0
    for obj in room:
        if obj.type != 'MESH':
            continue
        if any(word in obj.name.lower() for word in ('floor', 'roof', 'ground')):
            continue
        matrix = obj.matrix_world
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        doomed = []
        for face in bm.faces:
            inside = True
            for vert in face.verts:
                point = matrix @ vert.co
                if not (lo.x <= point.x <= hi.x and lo.y <= point.y <= hi.y and lo.z <= point.z <= hi.z):
                    inside = False
                    break
            if inside:
                doomed.append(face)
        if doomed:
            area = sum(f.calc_area() for f in doomed)
            bmesh.ops.delete(bm, geom=doomed, context='FACES')
            bm.to_mesh(obj.data)
            obj.data.update()
            total += len(doomed)
            print(f'[scene]   opened {obj.name}: {len(doomed)} faces, {area:.4f} m2 removed')
        bm.free()
    print(f'[scene] doorway opened through {total} faces')
    bpy.context.view_layer.update()


# ---------------------------------------------------------------- hallway

DEFAULT_HALLWAY = {
    'length_m': 2.60,
    'inset_m': -0.002,
    'mouth_back_m': 0.070,
    'headroom_m': 0.012,
    'skirt_height_m': 0.11,
    'skirt_proud_m': 0.008,
    'picture_depth_m': 0.80,
    'picture_size_m': [0.40, 0.52],
    'picture_center_z_m': 1.38,
    'floor_color': [0.23, 0.15, 0.10],
    'wall_color': [0.52, 0.50, 0.46],
    'ceiling_color': [0.58, 0.57, 0.54],
    'skirt_color': [0.17, 0.11, 0.08],
    'door_color': [0.24, 0.15, 0.10],
    'frame_color': [0.13, 0.09, 0.07],
    'canvas_color': [0.62, 0.56, 0.44],
    'roughness': 0.76,
    'lamp_power': 11.0,
    'lamp_size': 0.34,
    'lamp_color': [1.0, 0.84, 0.64],
    'lamp_depth_m': 1.35,
}


def flat_material(name: str, colour: Iterable[float], roughness: float) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    bsdf = material.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (*[float(c) for c in colour], 1.0)
    bsdf.inputs['Roughness'].default_value = float(roughness)
    metallic = bsdf.inputs.get('Metallic')
    if metallic is not None:
        metallic.default_value = 0.0
    return material


def newell_normal(corners: list[Vector]) -> Vector:
    normal = Vector((0.0, 0.0, 0.0))
    for index, point in enumerate(corners):
        following = corners[(index + 1) % len(corners)]
        normal.x += (point.y - following.y) * (point.z + following.z)
        normal.y += (point.z - following.z) * (point.x + following.x)
        normal.z += (point.x - following.x) * (point.y + following.y)
    if normal.length < 1e-9:
        return Vector((0.0, 0.0, 1.0))
    return normal.normalized()


def add_quad(
    name: str,
    corners: list[Vector],
    normal: Vector,
    material: bpy.types.Material,
) -> bpy.types.Object:
    """One flat four-sided face, wound so its normal points where asked."""
    ordered = list(corners)
    if newell_normal(ordered).dot(Vector(normal)) < 0.0:
        ordered.reverse()
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(c) for c in ordered], [], [(0, 1, 2, 3)])
    mesh.validate()
    if mesh.polygons:
        mesh.polygons[0].use_smooth = False
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    return obj


def build_hallway_picture(
    path: Path,
    layout: dict[str, Any],
    spec: dict[str, Any],
    layout_spec: dict[str, Any],
    *,
    wall_x: float,
    centre_y: float,
    centre_z: float,
) -> dict[str, Any]:
    """Hang the asset's framed picture in the corridor instead of a flat canvas.

    The previous stand-in was two quads -- a frame plate and a bare canvas -- so
    the hallway's only scale reference was a blank rectangle. The café pictures
    GLB brings a real moulded frame, a mat and a print, and it arrives already
    in metres with the wall plane on its +X face, which is exactly how the
    corridor's left wall is oriented: no rotation, only a placement.

    Its origin sits inside the frame, so the drop is computed from the asset's
    own bounding box: back plate flush to the wall, then centred on the spec's
    picture position.
    """
    wanted = str(spec.get('picture_object') or 'wall_picture_2')
    previous = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    bpy.context.view_layer.update()
    imported = [o for o in bpy.data.objects if o not in previous]
    for obj in imported:
        obj.animation_data_clear()
    tame_glb_emission(imported, layout_spec)
    tame_glb_gloss(imported, layout_spec)

    meshes = [o for o in imported if o.type == 'MESH' and wanted in o.name]
    if not meshes:
        meshes = [o for o in imported if o.type == 'MESH']
    if not meshes:
        raise RuntimeError(f'{path.name} has no mesh; the picture cannot be hung')
    body = meshes[0]
    for obj in imported:
        if obj is not body:
            obj.hide_render = True

    # The picture hangs off an empty that carries the GLB's own unit scaling.
    # Keep the world matrix, drop the parent, so the drop below is in metres.
    world = body.matrix_world.copy()
    body.parent = None
    body.matrix_world = world
    bpy.context.view_layer.update()

    points = [body.matrix_world @ v.co for v in body.data.vertices]
    lo = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    hi = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    middle_y = (lo.y + hi.y) / 2.0
    middle_z = (lo.z + hi.z) / 2.0

    scale = float(spec.get('picture_scale') or 1.0)
    if abs(scale - 1.0) > 1e-9:
        body.scale = tuple(component * scale for component in body.scale)
        bpy.context.view_layer.update()
        points = [body.matrix_world @ v.co for v in body.data.vertices]
        lo = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
        hi = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
        middle_y = (lo.y + hi.y) / 2.0
        middle_z = (lo.z + hi.z) / 2.0

    body.location = Vector(body.location) + Vector((
        wall_x + float(spec.get('picture_proud_m') or 0.0) - lo.x,
        centre_y - middle_y,
        centre_z - middle_z,
    ))
    for obj in imported:
        obj.animation_data_clear()
    bpy.context.view_layer.update()

    points = [body.matrix_world @ v.co for v in body.data.vertices]
    lo = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    hi = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    info = {
        'object': body.name,
        'asset': path.name,
        'size_m': [round(hi.y - lo.y, 4), round(hi.z - lo.z, 4)],
        'depth_m': round(hi.x - lo.x, 4),
        'centre': [round((lo.y + hi.y) / 2.0, 4), round((lo.z + hi.z) / 2.0, 4)],
    }
    print(
        f'[scene] hallway picture {body.name!r} {info["size_m"][0]:.3f} x {info["size_m"][1]:.3f} m '
        f'at y={info["centre"][0]:.3f} z={info["centre"][1]:.3f}'
    )
    return info


def build_hallway(
    layout: dict[str, Any],
    leaf_info: dict[str, Any],
    floor_z: float,
    picture_path: Path | None = None,
    wall: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Stand a hallway behind the doorway so the opening leads somewhere.

    The room asset is one closed box: nothing at all sits behind the door, so
    the moment the leaf swings ajar the aperture shows the grey backing sheet
    ``carve_doorway`` deletes. Five inward-facing planes fix that.

    Geometry, and why it is this geometry:

    * The hallway's cross-section **is** the aperture's, 2 mm wider so its side
      walls tuck behind the asset's own jamb instead of standing in front of it,
      and its mouth is recessed 70 mm *behind* the room's wall face. Recessing it
      is what makes the doorway's edge a jamb: brought flush, the corridor's side
      wall becomes the doorway's edge, the camera meets it at 88 deg and it
      renders as a striped, badly sampled band rather than a surface. Set back,
      the asset's casing covers it and the eye gets a 70 mm reveal instead -- a
      step, a shadow line, a readable thickness.
    * Because the corridor is only 0.95 m wide, a camera 44 deg off the doorway
      axis never sees the far end -- it sees *one side wall*, 0.6 m of it,
      stretching away. So the depth has to be carried by that one wall: a
      skirting board, a framed picture at 0.8 m whose foreshortened rectangle is
      the only scale reference in shot, a dark floor against light walls, and
      light that falls off with distance. A uniformly lit wall reads as a flat
      cream card no matter how deep it really is; that was the first attempt.

    The far door panel is kept because the PCVE keyframe cameras do look down
    the axis; it costs one quad.
    """
    spec = {**DEFAULT_HALLWAY, **dict(layout.get('hallway') or {})}
    hinge = leaf_info['hinge_world']
    hx, hy = float(hinge[0]), float(hinge[1])
    width = float(leaf_info['width_m'])
    height = float(leaf_info['height_m'])

    existing_objects = set(bpy.data.objects)
    bounds = layout.get('room_bounds') or {}
    room_face = float(bounds['y'][0]) if bounds.get('y') else hy + 0.154
    y_mouth = room_face - float(spec['mouth_back_m'])
    y_back = y_mouth - float(spec['length_m'])

    inset = float(spec['inset_m'])
    x_lo = hx + inset
    x_hi = hx + width - inset
    z_lo = float(floor_z)
    z_hi = float(floor_z) + height + float(spec['headroom_m'])
    roughness = float(spec['roughness'])

    floor_mat = flat_material('hallway_floor', spec['floor_color'], roughness * 0.72)
    wall_mat = flat_material('hallway_wall', spec['wall_color'], roughness)
    ceiling_mat = flat_material('hallway_ceiling', spec['ceiling_color'], min(0.95, roughness + 0.15))
    skirt_mat = flat_material('hallway_skirting', spec['skirt_color'], roughness * 0.8)
    door_mat = flat_material('hallway_door', spec['door_color'], roughness * 0.7)

    def face(name: str, points: list[Vector], normal: Vector, material: bpy.types.Material) -> None:
        add_quad(name, points, normal, material)

    z_up, z_down = Vector((0.0, 0.0, 1.0)), Vector((0.0, 0.0, -1.0))
    x_right, x_left = Vector((1.0, 0.0, 0.0)), Vector((-1.0, 0.0, 0.0))
    y_back_n = Vector((0.0, 1.0, 0.0))

    face('hallway_floor', [Vector((x_lo, y_mouth, z_lo)), Vector((x_hi, y_mouth, z_lo)),
                           Vector((x_hi, y_back, z_lo)), Vector((x_lo, y_back, z_lo))], z_up, floor_mat)
    face('hallway_ceiling', [Vector((x_lo, y_mouth, z_hi)), Vector((x_hi, y_mouth, z_hi)),
                             Vector((x_hi, y_back, z_hi)), Vector((x_lo, y_back, z_hi))], z_down, ceiling_mat)
    face('hallway_wall_left', [Vector((x_lo, y_mouth, z_lo)), Vector((x_lo, y_back, z_lo)),
                               Vector((x_lo, y_back, z_hi)), Vector((x_lo, y_mouth, z_hi))], x_right, wall_mat)
    face('hallway_wall_right', [Vector((x_hi, y_mouth, z_lo)), Vector((x_hi, y_back, z_lo)),
                                Vector((x_hi, y_back, z_hi)), Vector((x_hi, y_mouth, z_hi))], x_left, wall_mat)
    face('hallway_wall_back', [Vector((x_lo, y_back, z_lo)), Vector((x_hi, y_back, z_lo)),
                               Vector((x_hi, y_back, z_hi)), Vector((x_lo, y_back, z_hi))], y_back_n, wall_mat)

    # The mouth collar: the hallway's own jamb, 70 mm deep, carrying the opening
    # from the aperture back to where the hallway's walls start. Without it the
    # doorway's edge is whatever the carve left in the room's wall, and rays can
    # slip through the 2 mm the hallway is wider by into the void between the two.
    # Its inboard edge is pulled 2 mm behind the measured wall plane, so it can
    # never poke out through a wall face that sits 2 mm off its bounding box.
    y_near = room_face - 0.002
    for name, near_x, far_x, normal in (
        ('left', hx, x_lo, Vector((1.0, 0.0, 0.0))),
        ('right', hx + width, x_hi, Vector((-1.0, 0.0, 0.0))),
    ):
        face(f'hallway_jamb_{name}',
             [Vector((near_x, y_near, z_lo)), Vector((far_x, y_mouth, z_lo)),
              Vector((far_x, y_mouth, z_hi)), Vector((near_x, y_near, z_hi))],
             normal, wall_mat)

    # Skirting: the strongest depth cue available on a wall seen this obliquely,
    # and the only thing that tells the eye where the wall meets the floor once
    # the far half has fallen into shadow.
    skirt_h = float(spec['skirt_height_m'])
    proud = float(spec['skirt_proud_m'])
    skirt_top = min(z_lo + skirt_h, z_hi - 0.02)
    for name, wall_x, inward in (('left', x_lo, 1.0), ('right', x_hi, -1.0)):
        offset = wall_x + inward * proud
        face(f'hallway_skirt_{name}',
             [Vector((offset, y_mouth, z_lo)), Vector((offset, y_back, z_lo)),
              Vector((offset, y_back, skirt_top)), Vector((offset, y_mouth, skirt_top))],
             Vector((inward, 0.0, 0.0)), skirt_mat)
        face(f'hallway_skirt_{name}_top',
             [Vector((wall_x, y_mouth, skirt_top)), Vector((offset, y_mouth, skirt_top)),
              Vector((offset, y_back, skirt_top)), Vector((wall_x, y_back, skirt_top))], z_up, skirt_mat)
    face('hallway_skirt_back',
         [Vector((x_lo, y_back + proud, z_lo)), Vector((x_hi, y_back + proud, z_lo)),
          Vector((x_hi, y_back + proud, skirt_top)), Vector((x_lo, y_back + proud, skirt_top))],
         y_back_n, skirt_mat)

    # A framed picture on the left wall. Flat colour and a skirting only tell you
    # the wall is long; a rectangle at a known size, foreshortened by the view,
    # tells you *how far* it recedes -- the only object in the shot whose width
    # is a readable scale reference. When the scene has a picture asset the
    # modelling replaces the two quads; the quads stay as the fallback.
    picture_w, picture_h = (float(v) for v in spec['picture_size_m'])
    picture_y = y_mouth - float(spec['picture_depth_m'])
    picture_z = z_lo + float(spec['picture_center_z_m'])
    picture_info: dict[str, Any] = {}
    if picture_path is not None and bool(spec.get('picture_enabled', True)):
        picture_info = build_hallway_picture(
            picture_path,
            layout,
            spec,
            layout,
            wall_x=x_lo,
            centre_y=picture_y,
            centre_z=picture_z,
        )
    else:
        canvas_mat = flat_material('hallway_canvas', spec['canvas_color'], 0.85)
        frame_mat = flat_material('hallway_frame', spec['frame_color'], roughness * 0.6)
        for name, lift, shrink, material in (
            ('frame', 0.030, 0.000, frame_mat),
            ('canvas', 0.037, 0.030, canvas_mat),
        ):
            half_w = picture_w / 2.0 - shrink
            half_h = picture_h / 2.0 - shrink
            face(f'hallway_picture_{name}',
                 [Vector((x_lo + lift, picture_y - half_w, picture_z - half_h)),
                  Vector((x_lo + lift, picture_y + half_w, picture_z - half_h)),
                  Vector((x_lo + lift, picture_y + half_w, picture_z + half_h)),
                  Vector((x_lo + lift, picture_y - half_w, picture_z + half_h))],
                 x_right, material)

    # The far door, for the on-axis keyframe cameras.
    door_w = min(0.82, (x_hi - x_lo) - 0.18)
    door_h = min(1.98, (z_hi - z_lo) - 0.26)
    centre_x = (hx + hx + width) / 2.0
    face('hallway_door_panel',
         [Vector((centre_x - door_w / 2.0, y_back + 0.012, z_lo + 0.01)),
          Vector((centre_x + door_w / 2.0, y_back + 0.012, z_lo + 0.01)),
          Vector((centre_x + door_w / 2.0, y_back + 0.012, z_lo + 0.01 + door_h)),
          Vector((centre_x - door_w / 2.0, y_back + 0.012, z_lo + 0.01 + door_h))],
         y_back_n, door_mat)

    # A dim lamp deep in the hallway. The hallway is a closed box, so with no
    # source at all it renders as a black hole -- worse than the grey card it
    # replaced -- but a bright source near the mouth flattens it back into a
    # card. Low power, 1.7 m in, gives the falloff that reads as distance.
    lamp_power = float(spec['lamp_power'])
    if lamp_power > 0.0:
        lamp = Vector((centre_x, y_mouth - float(spec['lamp_depth_m']), z_hi - 0.06))
        add_area_light(
            'hallway_lamp',
            lamp,
            Vector((centre_x, lamp.y, z_lo)),
            energy=lamp_power,
            size=float(spec['lamp_size']),
            color=tuple(float(c) for c in spec['lamp_color']),
        )

    # The doorway is in a splayed wall, so the two sides have different mouth
    # depths. A mouth built from room_bounds.y projects through the plaster.
    # Move only the entrance vertices; the picture and far end stay in place.
    if wall is not None:
        normal = Vector(wall['normal'])
        for obj in set(bpy.data.objects) - existing_objects:
            if obj.type != 'MESH' or not obj.name.startswith('hallway_'):
                continue
            inverse = obj.matrix_world.inverted()
            for vertex in obj.data.vertices:
                point = obj.matrix_world @ vertex.co
                if abs(point.y - y_mouth) < 1e-5 or abs(point.y - y_near) < 1e-5:
                    wall_y = (wall['offset'] - normal.x * point.x) / normal.y
                    point.y += wall_y - room_face
                    vertex.co = inverse @ point
            obj.data.update()

    info = {
        'entrance_follows_wall': wall is not None,
        'x': [round(x_lo, 4), round(x_hi, 4)],
        'y': [round(y_back, 4), round(y_mouth, 4)],
        'z': [round(z_lo, 4), round(z_hi, 4)],
        'length_m': round(float(spec['length_m']), 3),
        'picture': picture_info,
    }
    print(
        f'[scene] hallway x[{x_lo:+.3f},{x_hi:+.3f}] y[{y_back:+.3f},{y_mouth:+.3f}] '
        f'z[{z_lo:+.3f},{z_hi:+.3f}] - {spec["length_m"]:.2f} m long, lamp at '
        f'{lamp_power:.0f} W'
    )
    return info


def fitted_door_geometry(room, old_info, wall, floor_z, thickness):
    """Measure the real plaster opening and put the hinge on its front edge."""
    source = next(o for o in room if o.type == 'MESH' and o.name.startswith('door_wall_'))
    normal = Vector(wall['normal'])
    points = [source.matrix_world @ v.co for v in source.data.vertices]
    front = [p for p in points if abs(normal.dot(p) - wall['offset']) < 0.003]
    feet = [p for p in front if p.z < floor_z + 0.03]
    old_x = old_info['hinge_world'][0]
    left = min(feet, key=lambda p: abs(p.x - old_x)).copy()
    right = min(feet, key=lambda p: abs(p.x - old_x - old_info['width_m'])).copy()
    axis = Vector((right.x-left.x, right.y-left.y, 0)).normalized()
    opening_width = Vector((right.x-left.x, right.y-left.y, 0)).length
    heads = [p.z for p in front if abs(p.x-left.x) < .003 and floor_z + 1 < p.z < floor_z + 2.3]
    # The jamb is tessellated vertically, including vertices above the opening.
    # Select its head near the measured source leaf, not a tessellation extreme.
    source_head = old_info['hinge_world'][2] + old_info['height_m']
    head = min(heads, key=lambda z: abs(z-source_head))
    gap, bottom = 0.004, 0.007
    hinge = left + axis * gap + normal * (thickness + 0.003)
    hinge.z = floor_z
    width, height = opening_width - 2*gap, head - floor_z - bottom - gap
    yaw = math.atan2(axis.y, axis.x)
    info = dict(old_info)
    info.update(width_m=width, height_m=height, thickness_m=thickness,
                hinge_world=list(hinge), closed_yaw_deg=math.degrees(yaw),
                bottom_clearance_m=bottom, hinge_front_edge=True,
                opening_width_m=opening_width, opening_top_world_z=head,
                opening_left_world=list(left), opening_right_world=list(right),
                wall_panel_world_x=[min(p.x for p in feet), max(p.x for p in feet)],
                wall_front_offset_from_hinge_m=-(thickness + .003),
                wall_depth_m=0.08, side_clearance_m=gap)
    aperture = (Vector((left.x, min(left.y,right.y), floor_z)),
                Vector((right.x, max(left.y,right.y), head)))
    return info, aperture


def finish_doorway_skirting(room, layout, leaf_info, floor_z, wall):
    """Finish the room's textured timber flush at the plaster opening.

    The room asset has separate, badly UV-mapped end caps at the old casing.
    Replace just those short diagonal runs and match the corridor's skirting
    to the same height, depth and wood atlas strip.
    """
    if wall is None:
        return
    source = next((o for o in room if o.type == 'MESH' and o.name.startswith('blinta_')), None)
    if source is None or not source.data.materials:
        return
    material = source.data.materials[0]
    hx, hy, hz = leaf_info['hinge_world']
    width = float(leaf_info['width_m'])
    aperture_lo, aperture_hi = doorway_bounds(leaf_info, layout)
    normal = Vector(wall['normal'])
    spec = {**DEFAULT_HALLWAY, **dict(layout.get('hallway') or {})}
    thickness = float(spec['skirt_proud_m'])
    top = floor_z + float(spec['skirt_height_m'])
    bottom = floor_z - 0.01
    def wall_y(x):
        return (wall['offset'] - normal.x * x) / normal.y

    # The carving bounds include clearance. The visible plaster edges are
    # slightly inside that box, so terminating timber at the box leaves a gap.
    wall_object = next((o for o in room if o.type == 'MESH' and o.name.startswith('door_wall_')), None)
    edge_candidates = []
    if wall_object:
        for vertex in wall_object.data.vertices:
            point = wall_object.matrix_world @ vertex.co
            if point.z < floor_z + 0.03 and abs(normal.dot(point) - wall['offset']) < 0.003:
                edge_candidates.append(point.x)
    left_edge = min(edge_candidates, key=lambda x: abs(x - hx)) if edge_candidates else aperture_lo.x
    right_edge = min(edge_candidates, key=lambda x: abs(x - hx - width)) if edge_candidates else aperture_hi.x

    # The short slanted runs share the main skirting mesh, but are disconnected
    # islands. Keep the long runs along the rest of the bedroom intact.
    doomed = set()
    for group in door_asset._components(source.data):
        points = [source.matrix_world @ source.data.vertices[i].co for i in group]
        if all(-1.20 < p.x < 0.56 and p.y < -5.30 and p.z < 0.20 for p in points):
            doomed.update(group)
    bm = bmesh.new()
    bm.from_mesh(source.data)
    bm.verts.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.verts[i] for i in doomed], context='VERTS')
    bm.to_mesh(source.data)
    bm.free()
    source.data.update()

    def wood_uv(obj, axis):
        obj.data.materials.clear()
        obj.data.materials.append(material)
        uv = obj.data.uv_layers.active or obj.data.uv_layers.new(name='UVMap')
        for poly in obj.data.polygons:
            for loop_index in poly.loop_indices:
                point = obj.matrix_world @ obj.data.vertices[obj.data.loops[loop_index].vertex_index].co
                # Sample the same narrow horizontal grain strip as the room's
                # original front face, avoiding its broken end-cap UV islands.
                uv.data[loop_index].uv = (0.60 + ((point[axis] * 0.45) % 0.14),
                    0.889 + max(0.0, min(1.0, (point.z - bottom) / (top - bottom))) * 0.0128)

    for side, start_x, edge_x, sign in (
        ('left', -1.19125, left_edge, 1),
        ('right', 0.5281, right_edge, -1),
    ):
        a = Vector((start_x, wall_y(start_x), 0))
        b = Vector((edge_x, wall_y(edge_x), 0))
        d0 = (b - a).normalized()
        n0 = Vector((-d0.y, d0.x, 0)) * sign
        # A closed return-to-wall end stays entirely outside the opening.
        # Extending this board into the shallow reveal looks like a projecting
        # wooden tab from the scene camera; corridor boards start behind it.
        front_b = b + n0 * thickness
        # Cut normal to the slanted wall's tangent, so the end face cannot
        # intrude into the closed leaf's latch clearance.
        ring = [a, b, front_b, a + n0 * thickness]
        verts = [(p.x, p.y, z) for z in (bottom, top) for p in ring]
        count = len(ring)
        faces = [tuple(reversed(range(count))), tuple(range(count, count * 2))]
        faces += [(i, (i + 1) % count, (i + 1) % count + count, i + count) for i in range(count)]
        mesh = bpy.data.meshes.new(f'doorway_skirt_{side}')
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(mesh)
        bm.free()
        obj = bpy.data.objects.new(mesh.name, mesh)
        bpy.context.collection.objects.link(obj)
        wood_uv(obj, 0)
        bevel = obj.modifiers.new('Timber edge', 'BEVEL')
        bevel.width = 0.001
        bevel.segments = 2
        obj.modifiers.new('Corner normals', 'WEIGHTED_NORMAL')
    for obj in bpy.data.objects:
        if obj.type == 'MESH' and obj.name.startswith('hallway_skirt_'):
            wood_uv(obj, 1)
    print('[scene] doorway skirting: closed flush ends, shared room wood atlas')


def door_wall_plane(
    layout: dict[str, Any],
    leaf_info: dict[str, Any],
    floor_z: float,
) -> dict[str, Any] | None:
    """Fit the plane of the wall the doorway is cut into.

    The bedroom's door does **not** stand in the axis-aligned wall: its opening
    is cut into a splayed panel that runs diagonally across the corner, so the
    panel's own normal comes back at 26 deg to +Y. That is why the room asset
    ships its casing already rotated, and why an axis-aligned frame dropped over
    the aperture stands a hand's width proud of the wall on one side and buried
    on the other.

    Two rays, fired at the wall just outside the aperture and at a height the
    leaf never reaches while it is still closed, are enough: both land on the
    same panel, and a plane through two points with the panel's own normal fixes
    both the yaw and the offset.
    """
    opening = {**DEFAULT_OPENING, **dict(layout.get('doorway_opening') or {})}
    hx, hy, hz = (float(v) for v in leaf_info['hinge_world'])
    width = float(leaf_info['width_m'])
    lo_x = hx - float(opening['side_m'])
    hi_x = hx + width + float(opening['side_m'])
    z = hz + 0.6 * float(leaf_info['height_m'])
    depsgraph = bpy.context.evaluated_depsgraph_get()

    hits = []
    for x in (lo_x - 0.08, hi_x + 0.15):
        hit, location, normal, _index, obj, _matrix = bpy.context.scene.ray_cast(
            depsgraph, Vector((x, hy + float(opening['to_room_m']) + 0.9, z)), Vector((0.0, -1.0, 0.0))
        )
        if hit and abs(normal.z) < 0.4:
            hits.append((Vector((location.x, location.y, 0.0)), Vector((normal.x, normal.y, 0.0)).normalized(), obj.name))
    if len(hits) < 2:
        print('[scene] door wall: fewer than two hits, keeping the frame axis-aligned')
        return None

    normal = (hits[0][1] + hits[1][1])
    if normal.length < 1e-6:
        return None
    normal.normalize()
    if normal.y < 0.0:
        normal.negate()
    if normal.dot(hits[0][1]) < 0.85:
        print('[scene] door wall: the two rays disagree, keeping the frame axis-aligned')
        return None
    offset = normal.dot(hits[0][0])
    yaw = math.atan2(-normal.x, normal.y)
    print(
        f'[scene] door wall normal ({normal.x:+.4f},{normal.y:+.4f}) offset {offset:+.4f} '
        f'-> yaw {math.degrees(yaw):+.2f} deg on {hits[0][2]} / {hits[1][2]}'
    )
    return {'normal': normal, 'offset': offset, 'yaw_deg': math.degrees(yaw)}


def import_ball(path: Path, layout: dict[str, Any]) -> bpy.types.Object:
    """Bake the basketball into one mesh, sized to a real ball, origin at its centre."""
    imported = import_glb(path)
    meshes = [o for o in imported if o.type == 'MESH']
    if not meshes:
        raise RuntimeError(f'{path.name} has no mesh')
    bpy.ops.object.select_all(action='DESELECT')
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    ball = bpy.context.view_layer.objects.active

    # glTF exports wrap the mesh in an empty that carries the Y-up -> Z-up
    # correction. Left parented, the pose written further down goes through
    # that rotation and the ball lands outside the room (measured: z = -2.23
    # instead of +1.42). Keep the world position, drop the parent.
    world = ball.matrix_world.copy()
    ball.parent = None
    ball.matrix_world = world
    for obj in imported:
        if obj is not ball and obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)

    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    extent = max(ball.dimensions)
    factor = float(layout['ball_scale_to_diameter_m']) / extent
    ball.scale = (factor, factor, factor)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.ops.object.origin_set(type='ORIGIN_CENTER_OF_VOLUME')
    ball.location = (0.0, 0.0, 0.0)
    ball.name = 'basketball'
    ball.data.name = 'basketball'
    bpy.context.view_layer.update()
    print(f'[scene] ball {extent:.4f} model units -> {max(ball.dimensions):.4f} m (scale {factor:.5f})')
    return ball


def floor_under(layout: dict[str, Any]) -> float:
    """Top of the room's floor directly under the door hinge."""
    hint = Vector([float(v) for v in layout['door_hinge_model_xyz']]) * float(layout['room_scale'])
    depsgraph = bpy.context.evaluated_depsgraph_get()
    hit, location, _normal, _index, obj, _matrix = bpy.context.scene.ray_cast(
        depsgraph, Vector((hint.x, hint.y, 1.5)), Vector((0.0, 0.0, -1.0))
    )
    if hit:
        print(f'[scene] floor under the door at z={location.z:.4f} ({obj.name})')
        return float(location.z)
    print('[scene] no floor under the door, using layout.floor_z')
    return float(layout['floor_z'])


# ---------------------------------------------------------------- physics


def physics_python(explicit: Path | None) -> str:
    candidates = [explicit, ROOT / '.runtime' / 'sim' / 'python.exe', ROOT / '.runtime' / 'sim' / 'bin' / 'python']
    for candidate in candidates:
        if candidate is not None and Path(candidate).exists():
            return str(Path(candidate))
    found = shutil.which('python3') or shutil.which('python')
    if not found:
        raise RuntimeError('No Python with pybullet found; pass --physics-python.')
    return found


def run_simulation(
    args: argparse.Namespace,
    *,
    out_dir: Path,
    scenario_path: Path,
    leaf_path: Path,
    fps: int,
    duration: float,
) -> dict[str, Any]:
    trajectory = out_dir / TRAJECTORY_NAME
    command = [
        physics_python(args.physics_python),
        str(HERE / 'simulate_home_basketball_door.py'),
        '--out', str(trajectory),
        '--scenario', str(scenario_path),
        '--door-leaf-json', str(leaf_path),
        '--fps', str(int(fps)),
        '--duration-sec', str(float(duration)),
    ]
    subprocess.run(command, check=True)
    return scene_config.read_json(trajectory)


def apply_physics_animation(
    leaf: bpy.types.Object,
    ball: bpy.types.Object,
    physics: dict[str, Any],
    origin: Vector,
) -> None:
    """Key the door as a hinge angle and the ball as a rigid pose.

    The leaf's origin is its hinge line and its mesh lies along +X, so the
    simulated opening angle is a single rotation about the object's Z. The
    simulation's axes are the room's axes: +X along the closed leaf, +Y into
    the room. Swinging the leaf from +X towards +Y is a positive Z rotation,
    so the keyed angle is the simulated angle with its sign kept.
    """
    leaf.rotation_mode = 'XYZ'
    ball.rotation_mode = 'QUATERNION'
    for record in physics['frames']:
        frame = int(record['frame_index'])
        leaf.rotation_euler = (0.0, 0.0, float(record['door_angle_rad']) +
                               float(physics['geometry']['leaf'].get('closed_yaw_deg', 0)) * math.pi / 180)
        leaf.keyframe_insert('rotation_euler', frame=frame)
        x, y, z, w = record['ball_quaternion_xyzw']
        ball.location = Vector(record['ball_location']) + origin
        ball.rotation_quaternion = Quaternion((w, x, y, z))
        ball.keyframe_insert('location', frame=frame)
        ball.keyframe_insert('rotation_quaternion', frame=frame)
    for obj in (leaf, ball):
        action = obj.animation_data.action
        for curve in action.fcurves:
            for point in curve.keyframe_points:
                point.interpolation = 'LINEAR'


# ------------------------------------------------------------------- scene


def add_area_light(
    name: str,
    location: Vector,
    target: Vector,
    *,
    energy: float,
    size: float,
    color: tuple[float, float, float],
) -> None:
    bpy.ops.object.light_add(type='AREA', location=location)
    light = bpy.context.object
    light.name = name
    light.data.shape = 'DISK'
    light.data.energy = energy
    light.data.size = size
    light.data.color = color
    light.rotation_euler = (target - location).to_track_quat('-Z', 'Y').to_euler()


def build_camera(layout: dict[str, Any]) -> bpy.types.Object:
    location = Vector([float(v) for v in layout['camera_location']])
    target = Vector([float(v) for v in layout['camera_target']])
    bpy.ops.object.camera_add(location=location)
    camera = bpy.context.object
    camera.name = 'home_basketball_door_camera'
    camera.rotation_euler = (target - location).to_track_quat('-Z', 'Y').to_euler()
    camera.data.lens = float(layout['camera_lens_mm'])
    camera.data.clip_start = 0.05
    camera.data.clip_end = 100.0
    bpy.context.scene.camera = camera
    return camera


DEFAULT_LIGHTING = {
    'world_color': [0.62, 0.70, 0.82],
    'world_strength': 0.6,
    'key_power': 60.0,
    'key_size': 1.6,
    'fill_power': 25.0,
    'fill_size': 2.2,
    'rim_power': 12.0,
    'rim_size': 0.8,
    'sun_energy': 1.5,
    'sun_angle_deg': 6.0,
    'sun_direction': [0.4, 0.7, -1.0],
}

DEFAULT_GRADE = {
    'view_transform': 'AgX',
    'look': 'AgX - Punchy',
    'exposure': -0.2,
}


def clamp_inside_room(point: Vector, layout: dict[str, Any], margin: float = 0.18) -> Vector:
    """Keep a light inside the bedroom.

    The room is 4.6 x 4.4 x 2.58 m, so a camera-relative offset of 2 m easily
    lands in -- or behind -- a wall. A light buried in a wall does not light the
    room at all: measured, the fill and the rim both ended up outside and the
    render came back three stops darker than intended.
    """
    bounds = layout.get('room_bounds')
    if not bounds:
        return point
    lo_x, hi_x = (float(v) for v in bounds['x'])
    lo_y, hi_y = (float(v) for v in bounds['y'])
    ceiling = float(bounds['ceiling_m'])
    return Vector((
        min(max(point.x, lo_x + margin), hi_x - margin),
        min(max(point.y, lo_y + margin), hi_y - margin),
        min(max(point.z, 0.35), ceiling - margin),
    ))


def build_lights(
    layout: dict[str, Any], door_centre: Vector, camera_location: Vector
) -> None:
    """Three soft sources, placed relative to the camera, plus a low sun.

    The bedroom is a closed box, so without a directional source the door leaf
    and the wall behind it sit at almost the same value and the swing is hard
    to read. The leaf's lit face is the one that faces into the room, i.e. the
    camera, so the key is hung on the camera's side of the action and pushed to
    one side of it; a rim near the door catches the leaf's edge against the
    wall. Placing the key by fixed world offsets instead lit the back of the
    leaf and left the visible face flat. The sun rakes across the floor towards
    the door, which gives the ball a contact shadow to land in.
    """
    lighting = {**DEFAULT_LIGHTING, **dict(layout.get('lighting') or {})}
    action = door_centre + Vector((0.0, 0.4, 0.2))
    towards = Vector(camera_location) - action
    towards.z = 0.0
    if towards.length < 0.5:
        towards = Vector((0.0, 2.0, 0.0))
    towards.normalize()
    side = Vector((-towards.y, towards.x, 0.0))
    add_area_light(
        'key',
        clamp_inside_room(action + towards * 2.4 + side * 1.5 + Vector((0.0, 0.0, 1.5)), layout),
        action,
        energy=float(lighting['key_power']), size=float(lighting['key_size']),
        color=(1.0, 0.97, 0.93),
    )
    add_area_light(
        'fill',
        clamp_inside_room(action + towards * 2.0 - side * 2.2 + Vector((0.0, 0.0, 0.9)), layout),
        action,
        energy=float(lighting['fill_power']), size=float(lighting['fill_size']),
        color=(0.86, 0.90, 1.0),
    )
    add_area_light(
        'rim',
        clamp_inside_room(action - towards * 1.2 + Vector((0.0, 0.0, 1.3)), layout),
        action + Vector((0.0, 0.0, 0.1)),
        energy=float(lighting['rim_power']), size=float(lighting['rim_size']),
        color=(1.0, 0.98, 0.94),
    )
    sun_energy = float(lighting['sun_energy'])
    if sun_energy > 0.0:
        sun_data = bpy.data.lights.new('sun', 'SUN')
        sun_data.energy = sun_energy
        sun_data.angle = math.radians(float(lighting['sun_angle_deg']))
        sun = bpy.data.objects.new('sun', sun_data)
        bpy.context.scene.collection.objects.link(sun)
        sun.rotation_euler = Vector(
            [float(c) for c in lighting['sun_direction']]
        ).to_track_quat('-Z', 'Y').to_euler()


def setup_world(scene: bpy.types.Scene, layout: dict[str, Any]) -> None:
    lighting = {**DEFAULT_LIGHTING, **dict(layout.get('lighting') or {})}
    world = bpy.data.worlds.new('Bedroom daylight')
    world.use_nodes = True
    background = world.node_tree.nodes['Background']
    background.inputs[0].default_value = (*[float(c) for c in lighting['world_color']], 1.0)
    background.inputs[1].default_value = float(lighting['world_strength'])
    scene.world = world


def setup_render(
    scene: bpy.types.Scene,
    args: argparse.Namespace,
    layout: dict[str, Any],
    *,
    fps: int,
    frame_end: int,
) -> None:
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = int(args.samples)
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 8
    scene.cycles.transmission_bounces = 6
    scene.cycles.device = 'CPU' if args.device == 'cpu' else 'GPU'
    if args.device != 'cpu':
        prefs = bpy.context.preferences.addons['cycles'].preferences
        try:
            prefs.compute_device_type = 'CUDA'; prefs.get_devices()
            available = [dev for dev in prefs.devices if dev.type == 'CUDA']
            for dev in prefs.devices:
                dev.use = (dev.type == 'CUDA')
            if available:
                scene.cycles.device = 'GPU'
                scene.cycles.denoiser = 'OPTIX' if any(dev.type == 'OPTIX' for dev in prefs.devices) else 'OPENIMAGEDENOISE'
                print('[render] CUDA: ' + ', '.join(dev.name for dev in available), flush=True)
        except Exception as exc:
            scene.cycles.device = 'CPU'
            print('[render] CPU fallback: ' + str(exc), flush=True)
    scene.render.resolution_x, scene.render.resolution_y = (int(v) for v in args.resolution)
    scene.render.resolution_percentage = 100
    scene.render.fps = int(fps)
    scene.frame_start = 1
    scene.frame_end = int(frame_end)
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.film_transparent = False

    grade = {**DEFAULT_GRADE, **dict(layout.get('grade') or {})}
    set_color_property(scene.view_settings, 'view_transform', str(grade['view_transform']))
    set_color_property(scene.view_settings, 'look', str(grade['look']))
    scene.view_settings.exposure = float(grade['exposure'])


def enable_video_output(scene: bpy.types.Scene, path: Path) -> None:
    scene.render.image_settings.file_format = 'FFMPEG'
    scene.render.ffmpeg.format = 'MPEG4'
    scene.render.ffmpeg.codec = 'H264'
    scene.render.ffmpeg.constant_rate_factor = 'MEDIUM'
    scene.render.filepath = str(path)


def export_ground_truth(
    out_dir: Path,
    *,
    leaf: bpy.types.Object,
    ball: bpy.types.Object,
    camera: bpy.types.Object,
    physics: dict[str, Any],
    scenario: dict[str, Any],
    origin: Vector,
    fps: int,
) -> None:
    scene = bpy.context.scene
    records: dict[str, Any] = {
        'schema_version': 1,
        'fps': int(fps),
        'frame_start': 1,
        'frame_end': int(scene.frame_end),
        'resolution': [int(scene.render.resolution_x), int(scene.render.resolution_y)],
        'world_origin': list(origin),
        'coordinate_system': 'Blender world space; quaternions XYZW',
        'physics': {k: v for k, v in physics.items() if k != 'frames'},
        'objects': {
            'door': {
                'object_name': leaf.name,
                'hinge_world': list(origin),
                'width_m': float(physics['geometry']['door_width_m']),
                'height_m': float(physics['geometry']['door_height_m']),
                'note': 'single rigid leaf on a vertical revolute joint; rotation about its own Z',
            },
            'ball': {
                'object_name': ball.name,
                'radius_m': float(physics['geometry']['ball_radius_m']),
                'note': 'single rigid sphere',
            },
        },
        'camera': {
            'object_name': camera.name,
            'lens_mm': float(camera.data.lens),
            'sensor_width_mm': float(camera.data.sensor_width),
            'matrix_world': [[float(v) for v in row] for row in camera.matrix_world],
            'world_to_camera_matrix': [
                [float(v) for v in row] for row in camera.matrix_world.inverted()
            ],
        },
        'scenario': scenario,
        'frames': [],
    }
    for record in physics['frames']:
        scene.frame_set(int(record['frame_index']))
        records['frames'].append(
            {
                'frame_index': int(record['frame_index']),
                'time_sec': float(record['time_sec']),
                'door_angle_deg': math.degrees(float(record['door_angle_rad'])),
                'door_angular_velocity': float(record['door_angular_velocity']),
                'door_matrix_world': [[float(v) for v in row] for row in leaf.matrix_world],
                'ball_matrix_world': [[float(v) for v in row] for row in ball.matrix_world],
                'ball_location': [float(v) for v in ball.location],
                'ball_quaternion_xyzw': [
                    float(ball.rotation_quaternion.x),
                    float(ball.rotation_quaternion.y),
                    float(ball.rotation_quaternion.z),
                    float(ball.rotation_quaternion.w),
                ],
                'ball_linear_velocity': [float(v) for v in record['ball_linear_velocity']],
                'ball_angular_velocity': [float(v) for v in record['ball_angular_velocity']],
                'ball_contacting_door': bool(record['ball_contacting_door']),
            }
        )
    scene_config.write_json(out_dir / GROUND_TRUTH_NAME, records)


def render_still(scene: bpy.types.Scene, frame: int, path: Path) -> None:
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.frame_set(int(frame))
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    print(f'[render] frame {frame} -> {path}')


def keyframe_list(args: argparse.Namespace, layout: dict[str, Any], frame_end: int) -> list[int]:
    if args.keyframes:
        frames = [int(part) for part in args.keyframes.split(',') if part.strip()]
    else:
        frames = [int(f) for f in layout.get('keyframes') or []]
    if not frames:
        frames = [round(1 + (frame_end - 1) * i / 8) for i in range(9)]
    return sorted({min(max(1, f), frame_end) for f in frames})


# -------------------------------------------------------------------- main


def main() -> None:
    args = parse_args()
    scenario = scene_config.load_scenario(args.scenario, args.scenario_overrides_json)
    physics_cfg = scenario['physics']
    layout = scenario['layout']
    assets = scenario['assets']

    fps = int(args.fps if args.fps is not None else physics_cfg['fps'])
    duration = float(
        args.duration_sec if args.duration_sec is not None else physics_cfg['duration_sec']
    )
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    room_path = model_path(assets['room'], args)
    ball_path = model_path(assets['ball'], args)
    print(f'[scene] room={room_path}')
    print(f'[scene] ball={ball_path}')
    door_spec = dict(layout.get('door_asset') or {})
    door_path = None
    if assets.get('door_leaf') and bool(door_spec.get('enabled', True)):
        door_path = model_path(assets['door_leaf'], args)
        print(f'[scene] door leaf={door_path}')
    picture_spec = dict(layout.get('hallway') or {})
    picture_path = None
    if picture_spec.get('picture_glb') and bool(picture_spec.get('picture_enabled', True)):
        picture_path = model_path(picture_spec['picture_glb'], args)
        print(f'[scene] hallway picture={picture_path}')

    scenario_path = out_dir / RESOLVED_NAME
    scene_config.write_json(scenario_path, scenario)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    setup_world(scene, layout)
    room = import_room(room_path, layout)

    leaf, leaf_info = extract_door_leaf(room, scenario)
    room_leaf_info = dict(leaf_info)
    floor_z = floor_under(layout)
    leaf.location = Vector((leaf_info['hinge_world'][0], leaf_info['hinge_world'][1], floor_z))
    origin = Vector(leaf.location)
    bpy.context.view_layer.update()

    # Swapping the leaf, not just skinning it: the room's own leaf is only
    # measured and cut out of the wall mesh, then replaced by the door asset's.
    # Fit to the actual plaster aperture before handing the same dimensions,
    # closed direction and front-edge hinge to the simulator.
    door_info: dict[str, Any] = {}
    wall = door_wall_plane(layout, leaf_info, floor_z)
    if door_path is not None:
        leaf_info, (aperture_lo, aperture_hi) = fitted_door_geometry(
            room, room_leaf_info, wall, floor_z, float(physics_cfg['door_thickness_m']))
        origin = Vector(leaf_info['hinge_world'])
        bpy.data.objects.remove(leaf, do_unlink=True)
        leaf, door_frame, door_info = door_asset.build_door_from_asset(
            door_path,
            door_spec,
            leaf_width_m=float(leaf_info['width_m']),
            leaf_height_m=float(leaf_info['height_m']),
            hinge_world=origin,
            floor_z=floor_z,
            aperture=(aperture_lo, aperture_hi),
            wall=wall,
        )
        leaf.location = origin
        door_info['collision_fit'] = door_asset.fit_leaf_to_collision(
            leaf, leaf_info['width_m'], leaf_info['height_m'],
            leaf_info['thickness_m'], leaf_info['bottom_clearance_m'])

    # The room ships its door hanging in front of a solid backing sheet -- there
    # is no hole in the wall and nothing behind it. Both have to be fixed before
    # anything is framed through the doorway.
    carve_doorway(room, room_leaf_info, layout)
    if door_info and bool(door_spec.get('replace_room_casing', False)):
        hx, hy, hz = (float(v) for v in room_leaf_info['hinge_world'])
        door_asset.strip_room_casing(
            room,
            box_lo=Vector((hx - 0.12, hy - 0.55, hz - 0.02)),
            box_hi=Vector((hx + float(room_leaf_info['width_m']) + 0.12, hy + 0.12,
                           hz + float(room_leaf_info['height_m']) + 0.18)),
        )
    hallway_info = build_hallway(layout, room_leaf_info, floor_z, picture_path, wall=wall)
    finish_doorway_skirting(room, layout, room_leaf_info, floor_z, wall)
    bpy.context.view_layer.update()

    ball = import_ball(ball_path, layout)

    # The simulator needs the leaf's measured dimensions and hinge. Keep this
    # generated input alongside the render outputs, outside the scene package.
    leaf_path = out_dir / LEAF_NAME
    scene_config.write_json(leaf_path, leaf_info)

    physics = run_simulation(
        args,
        out_dir=out_dir,
        scenario_path=scenario_path,
        leaf_path=leaf_path,
        fps=fps,
        duration=duration,
    )
    frame_end = int(physics['frame_end'])
    setup_render(scene, args, layout, fps=fps, frame_end=frame_end)
    apply_physics_animation(leaf, ball, physics, origin)

    camera = build_camera(layout)
    build_lights(
        layout,
        Vector((origin.x + 0.45 * leaf_info['width_m'], origin.y, origin.z + 0.9)),
        camera.location,
    )

    scene.frame_set(1)
    enable_video_output(scene, out_dir / 'basketball_door.mp4')
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(out_dir / 'basketball_door.blend'))

    export_ground_truth(
        out_dir,
        leaf=leaf,
        ball=ball,
        camera=camera,
        physics=physics,
        scenario=scenario,
        origin=origin,
        fps=fps,
    )
    scene_config.write_json(
        out_dir / METADATA_NAME,
        {
            'scene': scenario.get('scene', 'home_basketball_door'),
            'fps': fps,
            'duration_sec': duration,
            'total_frames': frame_end,
            'resolution': [int(v) for v in args.resolution],
            'samples': int(args.samples),
            'assets': {
                'room': str(room_path),
                'ball': str(ball_path),
                'door_leaf': str(door_path) if door_path is not None else None,
                'hallway_picture': str(picture_path) if picture_path is not None else None,
            },
            'door': {
                'width_m': leaf_info['width_m'],
                'height_m': leaf_info['height_m'],
                'thickness_m': leaf_info['thickness_m'],
                'hinge_world': [float(v) for v in origin],
                'asset_open_angle_deg': leaf_info['asset_open_angle_deg'],
                'joint': 'vertical revolute, Coulomb hinge friction as a scripted resisting torque',
                'visual_from_asset': bool(door_info),
                'door_asset': door_info,
            },
            'hallway': hallway_info,
            'ball': {
                'radius_m': float(physics['geometry']['ball_radius_m']),
                'diameter_m': 2.0 * float(physics['geometry']['ball_radius_m']),
            },
            'quality': physics['quality'],
            'scenario': scenario,
        },
    )

    if args.mode == 'build':
        return

    if args.mode == 'preview':
        impact = physics['quality']['impact_frame'] or 1
        for frame in dict.fromkeys([args.preview_frame] if args.preview_frame is not None else [1, int(impact), frame_end]):
            render_still(scene, frame, out_dir / f'preview_frame_{frame:04d}.png')
    elif args.mode == 'keyframes':
        target_dir = out_dir / 'keyframes'
        target_dir.mkdir(parents=True, exist_ok=True)
        for frame in keyframe_list(args, layout, frame_end):
            render_still(scene, frame, target_dir / f'frame_{frame:04d}.png')
    elif args.mode == 'frames':
        target_dir = out_dir / 'frames'
        target_dir.mkdir(parents=True, exist_ok=True)
        scene.render.image_settings.file_format = 'PNG'
        scene.render.image_settings.color_mode = 'RGB'
        scene.render.filepath = str(target_dir / 'frame_')
        bpy.ops.render.render(animation=True)
    else:
        enable_video_output(scene, out_dir / 'basketball_door.mp4')
        bpy.ops.render.render(animation=True)


if __name__ == '__main__':
    run_renderer(main, 'home_basketball_door')

"""Render the loaded-flatbed speed-bump scene with Blender's Python API.

The setting is a freight depot at dusk, deliberately unlike the residential
driveways and indoor tabletops of the other vehicle scenes: a wide asphalt
haul road through a container yard, sodium lamp masts throwing pools of warm
light down the far side, a warehouse facade and a gantry crane behind the
stacks, and a hazard board standing before the bump. None of it participates in
the collision solve; it exists to give the camera something to stream past and
to make the truck's speed legible.

The camera is a fixed vantage on the near-kerb side of the bump, so the truck
drives through the frame and its throw reads as vertical motion rather than as
the background streaming past. A second fixed, wider rig (``--camera-mode
survey``) holds the whole run for first/middle/last reviews; no rig follows the
truck. The truck, the sprung deck, and the cargo crate receive per-frame
transforms from the matching PyBullet simulation.
"""

from __future__ import annotations

# Load this seven-file scene bundle and the reference common scripts.
import sys as _clean_sys
from pathlib import Path as _CleanPath
_clean_scene_dir = _CleanPath(__file__).resolve().parent
_clean_scripts_dir = _clean_scene_dir.parent
_PCVE_PROJECT_ROOT = next(p for p in _clean_scene_dir.parents if (p / "assets").is_dir())
if str(_clean_scripts_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_clean_scripts_dir))
if str(_clean_scene_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_clean_scene_dir))
import edit_vocab as _clean_scene_bundle
_clean_scene_bundle.install_scene_support()





import sys
from pathlib import Path
from pcve_blender_compat import (shader_socket, set_shader_input, eevee_engine, set_eevee_property, set_color_property)

import argparse
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import bpy
from mathutils import Vector

import scene_support.flatbed_speed_bump.scene_config as cfg  # noqa: E402
from scene_support.flatbed_speed_bump.runtime_support import python_for
from scene_support.flatbed_speed_bump.cache_contract import validate_cache


WORKSPACE_DIR = _PCVE_PROJECT_ROOT
PHYSICS_PYTHON = python_for('physics')

# Poly Haven CC0 set, downloaded by ``fetch_visual_assets.py`` into the scene's
# own ``assets/`` folder. Nothing here reads another scene's texture directory.
ASSETS = _PCVE_PROJECT_ROOT / "assets" / "polyhaven" / "flatbed_speed_bump"
HDRI_STEM = "industrial_sunset_02"

OUTPUT_STEM = "flatbed_speed_bump"
GROUND_TRUTH_NAME = "ground_truth_transforms.json"
SCENARIO_METADATA_NAME = "scenario_metadata.json"

# Render-only, and it has to cover the clip: the physics road is 70 m each way
# (``scene_config.ROAD_HALF_LENGTH``) but this box used to stop at 26 m, so at
# t = 4 s the truck had run to x = 28.6 -- four metres past the end of the set
# -- and the last frame played out on bare ground with no kerbs, no lane dashes
# and no hatching. 62 m then put the run on tarmac, but 62 m is also where the
# tarmac visibly *stopped*: from a 2.2 m camera that cut sits barely a degree
# under the horizon and reads as "this road is 80 m long", which is the one
# thing a haul road must never look like. It now runs 300 m each way, and the
# apron under it 300 m in every direction, so the far edge of both lands inside
# the HDRI's haze band instead of cutting a line across the frame. The texture
# is object-coordinate box projection in metres (see ``pbr_material``), so
# stretching the box costs no texel density.
VISUAL_ROAD_HALF_LENGTH = 300.0
VISUAL_ROAD_HALF_WIDTH = 4.0
# Kerbs, lane dashes and hatching are drawn per 1.5-4 m, so they stop at 160 m:
# past that a 0.16 m kerb is under two pixels wide, and the continuous edge
# lines carry the perspective from there to the haze.
MARKING_HALF_LENGTH = 160.0
# The apron under the road, half extent. 300 m puts its own far edge ~0.4 deg
# under the horizon, i.e. behind the haze rather than in front of it.
GROUND_HALF_X = 300.0
GROUND_HALF_Y = 300.0

# Camera rigs, kept here rather than in ``scene_config.py`` on purpose: that
# file is hashed by ``cache_contract.signature()``, so touching it would
# invalidate every cached trajectory. Both are fixed -- there is deliberately no
# rig that follows the truck.
#
# ``static``  tight hero frame for previews: the truck reads as four metres of
#             steel, which the old 26 mm at 3.3 m did not.
# ``survey``  fixed wide that still holds the whole run (x = -9 .. 24). A
#             first/middle/last review is useless if the first and last frames
#             are empty road, and the truck covers 28.5 m between them.
CAMERA_PRESETS = {
    # Pulled back from (2.6, -13.0, 2.45) by the ratio the body grew when the
    # rig started following the glb: 5.41 m / 4.02 m = 1.346, so the apparent
    # size is unchanged and the nose is no longer cut off at the frame edge.
    "static": dict(
        location=(2.95, -17.55, 2.87), target=(1.6, 0.0, 1.25),
        lens_mm=50.0, fstop=2.8, focus_offset=1.6,
    ),
    "survey": dict(
        location=(9.0, -26.0, 2.80), target=(7.0, 0.0, 1.10),
        lens_mm=26.0, fstop=11.0, focus_offset=0.0,
    ),
    # Three-quarter view down the haul road. The 50 mm hero frame cropped the
    # depot down to a wall, so nothing in the shot carried depth or scale; this
    # rig stands back up the road and looks along it, which puts the receding
    # kerbs, the container row and the sky above it all in frame. Move it with
    # the truck, not with the camera rig: at 13 m back the 4 m body fills the
    # frame, and pulling further out leaves an empty apron on the right.
    "wide": dict(
        location=(-10.0, -8.6, 2.55), target=(4.6, 1.0, 1.10),
        lens_mm=44.0, fstop=4.0, focus_offset=-2.4,
    ),
    # The four-second clip, bolted to the ground -- no dolly, no second camera.
    # This is ``wide`` pulled back until the whole run fits: the same three
    # quarter angle down the haul road, the same container wall behind, the same
    # kerbs and hatching streaming past, but from 20.5 m instead of 8 m, with 36
    # mm instead of 44 mm so the 41 m the truck covers stay in the frustum.
    #
    # Scale is what it costs, and it varies: the body is 422 px wide at t = 0
    # (26 % of a 1600 px frame), 205 px at t = 4 as it recedes. That variation
    # is the point -- a fixed camera is there to show the truck moving.
    #
    # The square-on elevation that a "no panning" brief invites was tried and
    # rejected: to hold 41 m it has to stand 26 m off the road, where the frame
    # spans 24.5 m vertically at the truck, so the truck is 1.8 m tall in a
    # 24.5 m high frame and the bottom half is bare apron. Moving closer cannot
    # fix it -- coverage is 36*D/f while the truck is 240*f/D px wide, so a
    # 41 m shot is capped near 210 px at any distance.
    "clip4s": dict(
        location=(-21.0, -6.50, 2.20), target=(6.0, 0.6, 1.10),
        lens_mm=36.0, fstop=8.0, focus_offset=0.0,
    ),
}



from pcve_scene_runtime import parse_render_args, run_renderer, apply_physics_overrides

def parse_args() -> argparse.Namespace:
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
    parser = argparse.ArgumentParser(description="Render a flatbed truck crossing a speed bump.")
    parser.add_argument("--mode", choices=("preview", "animation", "sampled"), default="animation")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--resolution", nargs=2, type=int, default=cfg.BASELINE_RENDER["resolution"])
    parser.add_argument("--fps", type=int)
    parser.add_argument("--duration-sec", type=float)
    parser.add_argument("--samples", type=int, default=cfg.BASELINE_RENDER["samples"])
    # 29, the peak of the strike: the chassis is 0.37 m up, the nose is 7
    # degrees high and the carton is at its maximum 69 mm clear of the planks.
    # Earlier (18) the nose is still diving into the bump, and by 39 the truck
    # has landed and nothing is happening.
    parser.add_argument("--preview-frame", type=int, default=29)
    parser.add_argument(
        "--frame-count", type=int, default=6,
        help="Number of evenly-spaced stills to render in sampled mode.",
    )
    parser.add_argument("--seed", type=int, default=24017)
    parser.add_argument("--device", choices=("auto", "cpu"), default="auto")
    parser.add_argument(
        "--truck-asset", choices=("procedural", "imported"), default="imported",
        help="``imported`` is the CC-BY flatbed glb, which is what the rig in "
             "``scene_config`` is now derived from and therefore what the scene "
             "looks like. ``procedural`` is the old box-built rig, kept for "
             "provenance only: its decorative parts still use the pre-"
             "appearance_version-9 metres and are NOT re-proportioned.",
    )
    parser.add_argument(
        "--truck-glb", type=Path, default=None,
        help="Override the imported truck glb (default: assets/flatbed_unity3d.glb).",
    )
    parser.add_argument(
        "--engine", choices=("eevee", "cycles"), default="eevee",
        help="Distributions and contact shadows only look right in Cycles; "
             "EEVEE stays the default so the existing suite renders reproduce.",
    )
    parser.add_argument(
        "--camera-mode", choices=tuple(CAMERA_PRESETS), default=None,
        help="Defaults to ``wide`` for previews and to the baseline rig "
             "(``clip4s``) for animation. Every rig is bolted to the ground; "
             "there is deliberately no dolly option, see CAMERA_PRESETS.",
    )
    parser.add_argument("--truck-speed", type=float)
    parser.add_argument(
        "--speed-bump-height", type=float
    )
    parser.add_argument("--cargo-friction", type=float)
    parser.add_argument(
        "--physics-json", type=Path, default=None,
        help="Reuse a simulation result instead of running PyBullet (the PCVE "
             "suite simulates once and renders from it).",
    )
    parser.add_argument(
        "--scenario-overrides-json", type=Path, default=None,
        help="Timed-edit schedule forwarded to the simulation.",
    )
    args = parse_render_args(parser, argv)
    if args.camera_mode is None:
        args.camera_mode = "wide" if args.mode == "preview" else cfg.BASELINE_RENDER["camera_mode"]
    return args


# ---------------------------------------------------------------- materials


def material(
    name: str,
    color: tuple[float, float, float, float],
    *,
    metallic: float = 0.0,
    roughness: float = 0.5,
    clearcoat: float = 0.0,
    bump: float = 0.0,
    bump_scale: float = 20.0,
) -> bpy.types.Material:
    """Principled material, optionally with a procedural surface bump.

    ``bump`` drives a soft noise height-map so the large flat faces (asphalt,
    concrete, container walls) stop reading as glossy plastic. The noise is in
    object coordinates, so the mesh must carry its real size -- objects built
    with ``add_box(..., bake=True)`` (or already bevel-baked) -- for
    ``bump_scale`` to mean cycles-per-metre.
    """
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if clearcoat > 0.0:
        set_shader_input(bsdf, 'Coat Weight', clearcoat)
        set_shader_input(bsdf, 'Coat Roughness', 0.1)
    if bump > 0.0:
        texcoord = nodes.new("ShaderNodeTexCoord")
        noise = nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = bump_scale
        noise.inputs["Detail"].default_value = 5.0
        noise.inputs["Roughness"].default_value = 0.5
        bnode = nodes.new("ShaderNodeBump")
        bnode.inputs["Strength"].default_value = bump
        bnode.inputs["Distance"].default_value = 0.5
        links.new(noise.inputs["Vector"], texcoord.outputs["Object"])
        links.new(bnode.inputs["Height"], noise.outputs["Fac"])
        links.new(bsdf.inputs["Normal"], bnode.outputs["Normal"])
    return mat


def _asset_image(filename: str, color_space: str) -> bpy.types.Image:
    path = ASSETS / filename
    if not path.exists():
        raise FileNotFoundError(f"{path}: run fetch_visual_assets.py once")
    image = bpy.data.images.load(str(path), check_existing=True)
    image.colorspace_settings.name = color_space
    return image


def pbr_material(
    name: str,
    stem: str,
    *,
    tint: tuple[float, float, float] = (1.0, 1.0, 1.0),
    tint_mix: float = 0.0,
    metallic: float = 0.0,
    roughness_floor: float = 0.25,
    roughness_gain: float = 0.45,
    normal_strength: float = 0.5,
    tile: float = 3.0,
) -> bpy.types.Material:
    """A Poly Haven 2k set projected triplanar-style onto an unUVmapped box.

    Every box in this scene is built with ``from_pydata``, so there is no UV
    layer to sample. ``BOX`` projection from object coordinates sidesteps the
    unwrap entirely and, because ``add_box(bake=True)`` and every bevelled box
    carry their real size in the mesh, ``tile`` means metres.
    """
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = (*tint, 1.0)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")

    coord = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    inverse = 1.0 / float(tile)
    mapping.inputs["Scale"].default_value = (inverse, inverse, inverse)
    links.new(coord.outputs["Object"], mapping.inputs["Vector"])

    def image_node(channel: str, color_space: str):
        node = nodes.new("ShaderNodeTexImage")
        node.image = _asset_image(f"{stem}_{channel}_2k.jpg", color_space)
        node.projection = "BOX"
        node.projection_blend = 0.25
        links.new(mapping.outputs["Vector"], node.inputs["Vector"])
        return node

    diffuse = image_node("diff", "sRGB")
    if tint_mix > 0.0:
        multiply = nodes.new("ShaderNodeMixRGB")
        multiply.blend_type = "MULTIPLY"
        multiply.inputs[0].default_value = tint_mix
        multiply.inputs[2].default_value = (*tint, 1.0)
        links.new(diffuse.outputs["Color"], multiply.inputs[1])
        links.new(multiply.outputs["Color"], bsdf.inputs["Base Color"])
    else:
        links.new(diffuse.outputs["Color"], bsdf.inputs["Base Color"])

    roughness = image_node("rough", "Non-Color")
    remap = nodes.new("ShaderNodeMapRange")
    remap.inputs["From Min"].default_value = 0.0
    remap.inputs["From Max"].default_value = 1.0
    remap.inputs["To Min"].default_value = roughness_floor
    remap.inputs["To Max"].default_value = min(1.0, roughness_floor + roughness_gain)
    links.new(roughness.outputs["Color"], remap.inputs["Value"])
    links.new(remap.outputs["Result"], bsdf.inputs["Roughness"])

    normal = image_node("nor_gl", "Non-Color")
    normal_map = nodes.new("ShaderNodeNormalMap")
    normal_map.inputs["Strength"].default_value = normal_strength
    links.new(normal.outputs["Color"], normal_map.inputs["Color"])
    links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])

    bsdf.inputs["Metallic"].default_value = metallic
    return mat


def emissive(name: str, color: tuple[float, float, float, float], strength: float) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    set_shader_input(bsdf, 'Emission Color', color)
    bsdf.inputs["Emission Strength"].default_value = strength
    bsdf.inputs["Roughness"].default_value = 0.35
    return mat


MAT: dict[str, bpy.types.Material] = {}


def initialize_materials() -> None:
    """Build materials after Blender's factory reset.

    ``read_factory_settings`` clears all datablocks, so constructing these at
    module-import time leaves dangling ``StructRNA`` references when the scene
    is actually assembled.
    """
    global MAT
    reset_primitive_cache()
    MAT = {
        # --- scanned CC0 PBR: whatever fills most of the frame ---------------
        # These are the surfaces whose flatness was the loudest "this is a toy"
        # tell. Everything below them is still procedural on purpose: the truck
        # and the cargo are single-colour paint and worn cardboard, and a
        # 2k scan on a 0.4 m face would only add visible tiling.
        "concrete": pbr_material(
            "concrete_yard", "concrete_floor_damaged_01",
            roughness_floor=0.58, roughness_gain=0.38, normal_strength=0.55, tile=4.0,
        ),
        "asphalt": pbr_material(
            "asphalt", "asphalt_02",
            roughness_floor=0.55, roughness_gain=0.40, normal_strength=0.60, tile=3.2,
        ),
        "shutter": pbr_material(
            "warehouse_shutter", "painted_metal_shutter",
            metallic=0.35, roughness_floor=0.30, roughness_gain=0.42,
            normal_strength=0.55, tile=2.2,
        ),
        "warehouse": pbr_material(
            "warehouse_wall", "corrugated_iron_02",
            tint=(1.55, 1.56, 1.58), tint_mix=0.90, metallic=0.22,
            roughness_floor=0.42, roughness_gain=0.45, normal_strength=0.65, tile=5.0,
        ),
        "deck": pbr_material(
            "deck_steel", "metal_plate",
            tint=(0.90, 0.94, 1.00), tint_mix=0.90, metallic=0.55,
            roughness_floor=0.34, roughness_gain=0.40, normal_strength=0.45, tile=1.4,
        ),
        "steel_pale": pbr_material(
            "steel_pale", "metal_plate",
            tint=(0.80, 0.82, 0.86), tint_mix=0.85, metallic=0.85,
            roughness_floor=0.24, roughness_gain=0.35, normal_strength=0.35, tile=1.1,
        ),
        "steel_dark": pbr_material(
            "steel_dark", "metal_plate",
            tint=(0.42, 0.44, 0.48), tint_mix=0.90, metallic=0.55,
            roughness_floor=0.36, roughness_gain=0.40, normal_strength=0.40, tile=1.2,
        ),
        # The five container colours keep their identity but ride on the
        # corrugated scan, which is what gives the stacks their ribs and rust.
        "teal": pbr_material(
            "container_teal", "corrugated_iron_02",
            tint=(0.50, 0.92, 0.95), tint_mix=0.88, metallic=0.15,
            roughness_floor=0.42, roughness_gain=0.40, normal_strength=0.70, tile=2.6,
        ),
        "orange": pbr_material(
            "container_orange", "corrugated_iron_02",
            tint=(1.00, 0.55, 0.26), tint_mix=0.88, metallic=0.15,
            roughness_floor=0.42, roughness_gain=0.40, normal_strength=0.70, tile=2.6,
        ),
        "rust": pbr_material(
            "container_rust", "corrugated_iron_02",
            tint=(0.85, 0.50, 0.32), tint_mix=0.90, metallic=0.12,
            roughness_floor=0.45, roughness_gain=0.38, normal_strength=0.70, tile=2.6,
        ),
        "blue": pbr_material(
            "container_blue", "corrugated_iron_02",
            tint=(0.34, 0.50, 0.90), tint_mix=0.88, metallic=0.15,
            roughness_floor=0.42, roughness_gain=0.40, normal_strength=0.70, tile=2.6,
        ),
        "olive": pbr_material(
            "container_olive", "corrugated_iron_02",
            tint=(0.62, 0.66, 0.40), tint_mix=0.88, metallic=0.12,
            roughness_floor=0.44, roughness_gain=0.40, normal_strength=0.70, tile=2.6,
        ),
        # --- procedural: small faces and painted trim ------------------------
        "paint": material("road_paint", (0.34, 0.34, 0.33, 1.0), roughness=0.70),
        "rubber_bump": material("bump_rubber", (0.020, 0.021, 0.026, 1.0), roughness=0.86, bump=0.06, bump_scale=25.0),
        "bump_yellow": material("bump_yellow", (0.66, 0.47, 0.09, 1.0), roughness=0.66, bump=0.06, bump_scale=25.0),
        "kerb": material("kerb_stone", (0.20, 0.198, 0.192, 1.0), roughness=0.86, bump=0.12, bump_scale=8.0),
        # The hoarding reads as a line of white pickets whenever it borrows the
        # reflective steel scan: a real yard fence is dark galvanised mesh that
        # eats light instead of bouncing the sky back at the lens.
        "fence": material("fence_wire", (0.045, 0.047, 0.050, 1.0), metallic=0.30, roughness=0.72),
        "cab_white": material("cab_white", (0.72, 0.73, 0.72, 1.0), metallic=0.15, roughness=0.30, clearcoat=0.65),
        "cab_blue": material("cab_blue", (0.030, 0.115, 0.30, 1.0), metallic=0.20, roughness=0.33, clearcoat=0.65),
        "glass": material("cab_glass", (0.030, 0.085, 0.13, 1.0), metallic=0.35, roughness=0.10),
        "deck_rail": material("deck_rail", (0.78, 0.52, 0.045, 1.0), metallic=0.25, roughness=0.45),
        "rubber": material("tyre_rubber", (0.014, 0.015, 0.018, 1.0), roughness=0.80),
        "hub": material("wheel_hub", (0.52, 0.54, 0.57, 1.0), metallic=0.75, roughness=0.38),
        "cargo_a": material("cargo_amber", (0.40, 0.26, 0.13, 1.0), roughness=0.74, bump=0.04, bump_scale=20.0),
        "cargo_b": material("cargo_olive", (0.21, 0.25, 0.15, 1.0), roughness=0.76, bump=0.04, bump_scale=20.0),
        "cargo_c": material("cargo_red", (0.32, 0.14, 0.11, 1.0), roughness=0.72, bump=0.04, bump_scale=20.0),
        "strap": material("cargo_strap", (0.86, 0.78, 0.20, 1.0), roughness=0.60),
        "crane": material("crane_steel", (0.115, 0.108, 0.098, 1.0), metallic=0.45, roughness=0.55, bump=0.04, bump_scale=30.0),
        "mast": material("lamp_mast", (0.14, 0.15, 0.16, 1.0), metallic=0.55, roughness=0.45),
        "cone": material("traffic_cone", (0.80, 0.24, 0.030, 1.0), roughness=0.52),
        "barrel": material("barrel_blue", (0.020, 0.20, 0.42, 1.0), metallic=0.20, roughness=0.56, bump=0.04, bump_scale=18.0),
        "pallet": material("pallet_wood", (0.36, 0.235, 0.105, 1.0), roughness=0.80, bump=0.10, bump_scale=10.0),
    }
    MAT["lamp_glow"] = emissive("lamp_glow", (1.0, 0.60, 0.24, 1.0), 45.0)
    MAT["headlamp"] = emissive("headlamp_glow", (1.0, 0.88, 0.60, 1.0), 30.0)
    MAT["hazard"] = emissive("hazard_glow", (1.0, 0.62, 0.10, 1.0), 1.4)


# ---------------------------------------------------------------- primitives
#
# Everything here builds meshes with ``from_pydata`` and reuses two unit
# primitives instead of calling ``bpy.ops.mesh.primitive_*``. The depot is a
# few hundred objects and the operator path costs a ``transform_apply`` each,
# which alone was over a minute of scene construction before every render.

_UNIT_CUBE: bpy.types.Mesh | None = None
_UNIT_CYLINDER: bpy.types.Mesh | None = None
# One shared primitive per material. Sharing a *single* primitive across the
# whole scene looked cheaper, but ``_link`` appends the material to the mesh:
# every object after the first therefore appended its own slot to the same
# datablock while its polygons kept ``material_index = 0``, so the fence, the
# lamp masts, every container seam and every hazard chevron all rendered with
# the first material in the file -- road paint. That single bug is what made
# the yard read as flat grey cardboard.
_UNIT_CUBE_BY_MAT: dict[str, bpy.types.Mesh] = {}
_UNIT_CYLINDER_BY_MAT: dict[str, bpy.types.Mesh] = {}


def _unit_cube() -> bpy.types.Mesh:
    global _UNIT_CUBE
    if _UNIT_CUBE is None:
        mesh = bpy.data.meshes.new("unit_cube")
        mesh.from_pydata(
            [
                (-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (0.5, 0.5, -0.5), (-0.5, 0.5, -0.5),
                (-0.5, -0.5, 0.5), (0.5, -0.5, 0.5), (0.5, 0.5, 0.5), (-0.5, 0.5, 0.5),
            ],
            [],
            [
                (0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1),
                (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0),
            ],
        )
        _UNIT_CUBE = mesh
    return _UNIT_CUBE


def _unit_cube_for(mat: bpy.types.Material | None) -> bpy.types.Mesh:
    """Shared unit cube that already carries ``mat`` as its only slot."""
    key = mat.name if mat is not None else "<none>"
    mesh = _UNIT_CUBE_BY_MAT.get(key)
    if mesh is None:
        mesh = _unit_cube().copy()
        mesh.name = f"unit_cube[{key}]"
        if mat is not None:
            mesh.materials.append(mat)
        _UNIT_CUBE_BY_MAT[key] = mesh
    return mesh


def _unit_cylinder() -> bpy.types.Mesh:
    global _UNIT_CYLINDER
    if _UNIT_CYLINDER is None:
        _UNIT_CYLINDER = _cylinder_mesh("unit_cylinder", 1.0, 1.0)
    return _UNIT_CYLINDER


def _unit_cylinder_for(mat: bpy.types.Material | None) -> bpy.types.Mesh:
    key = mat.name if mat is not None else "<none>"
    mesh = _UNIT_CYLINDER_BY_MAT.get(key)
    if mesh is None:
        mesh = _unit_cylinder().copy()
        mesh.name = f"unit_cylinder[{key}]"
        if mat is not None:
            mesh.materials.append(mat)
        _UNIT_CYLINDER_BY_MAT[key] = mesh
    return mesh


def reset_primitive_cache() -> None:
    """Blender's factory reset frees the datablocks; drop the stale handles."""
    global _UNIT_CUBE, _UNIT_CYLINDER
    _UNIT_CUBE = None
    _UNIT_CYLINDER = None
    _UNIT_CUBE_BY_MAT.clear()
    _UNIT_CYLINDER_BY_MAT.clear()


def _box_mesh(name: str, dimensions: tuple[float, float, float]) -> bpy.types.Mesh:
    sx, sy, sz = (d * 0.5 for d in dimensions)
    return _mesh_from(
        name,
        [
            (-sx, -sy, -sz), (sx, -sy, -sz), (sx, sy, -sz), (-sx, sy, -sz),
            (-sx, -sy, sz), (sx, -sy, sz), (sx, sy, sz), (-sx, sy, sz),
        ],
        [
            (0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1),
            (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0),
        ],
    )


def _cylinder_mesh(
    name: str, radius: float, depth: float, segments: int = 28
) -> bpy.types.Mesh:
    vertices: list[tuple[float, float, float]] = []
    half = depth * 0.5
    for i in range(segments):
        angle = 2.0 * math.pi * i / segments
        vertices.append((radius * math.cos(angle), radius * math.sin(angle), -half))
    for i in range(segments):
        angle = 2.0 * math.pi * i / segments
        vertices.append((radius * math.cos(angle), radius * math.sin(angle), half))
    faces: list[tuple[int, ...]] = []
    for i in range(segments):
        a, b = i, (i + 1) % segments
        faces.append((a, b, segments + b, segments + a))
    faces.append(tuple(range(segments - 1, -1, -1)))
    faces.append(tuple(range(segments, 2 * segments)))
    return _mesh_from(name, vertices, faces)


def _mesh_from(name: str, vertices, faces) -> bpy.types.Mesh:
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.validate()
    return mesh


def _link(name: str, mesh, mat, parent) -> bpy.types.Object:
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    if mat is not None:
        obj.data.materials.append(mat)
    if parent is not None:
        obj.parent = parent
    return obj


def add_box(
    name: str,
    center: tuple[float, float, float],
    dimensions: tuple[float, float, float],
    mat: bpy.types.Material | None,
    *,
    bevel: float = 0.0,
    bake: bool = False,
    parent: bpy.types.Object | None = None,
) -> bpy.types.Object:
    """Add a box.

    ``bake`` writes the real size into the mesh (instead of a unit cube scaled
    at object level) so a material's object-space bump texture sees true metres.
    Use it for the large flat surfaces that carry a bump map.
    """
    if bevel > 0.0 or bake:
        obj = _link(name, _box_mesh(f"{name}_mesh", dimensions), mat, parent)
        if bevel > 0.0:
            modifier = obj.modifiers.new("soft_edges", "BEVEL")
            modifier.width = bevel
            modifier.segments = 2
    else:
        obj = _link(name, _unit_cube_for(mat), None, parent)
        obj.scale = dimensions
    obj.location = center
    return obj


def add_cylinder(
    name: str,
    center: tuple[float, float, float],
    radius: float,
    depth: float,
    mat: bpy.types.Material,
    *,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    bake_rotation: bool = False,
    bevel: float = 0.0,
    parent: bpy.types.Object | None = None,
) -> bpy.types.Object:
    """Add a cylinder.

    ``bake_rotation`` writes the placement rotation into the mesh so the
    object's own rotation stays free -- that is what lets a truck wheel be laid
    on its side and still be spun about world Y afterwards.
    """
    if bevel > 0.0:
        mesh = _cylinder_mesh(f"{name}_mesh", radius, depth)
        obj = _link(name, mesh, mat, parent)
        modifier = obj.modifiers.new("edge_round", "BEVEL")
        modifier.width = bevel
        modifier.segments = 2
    elif bake_rotation and any(rotation):
        obj = _link(name, _cylinder_mesh(f"{name}_mesh", radius, depth), mat, parent)
        obj.rotation_euler = rotation
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
        obj.location = center
        return obj
    else:
        obj = _link(name, _unit_cylinder_for(mat), None, parent)
        obj.scale = (radius, radius, depth)
    obj.location = center
    obj.rotation_euler = rotation
    return obj


def look_at(obj: bpy.types.Object, target: tuple[float, float, float]) -> None:
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def add_area_light(
    name: str,
    location: tuple[float, float, float],
    target: tuple[float, float, float],
    *,
    power: float,
    size: float,
    color: tuple[float, float, float],
    shadow: bool = True,
) -> None:
    bpy.ops.object.light_add(type="AREA", location=location)
    light = bpy.context.object
    light.name = name
    light.data.energy = power
    light.data.shape = "DISK"
    light.data.size = size
    light.data.color = color
    # Shadows are charged per light, so only the key casts them.
    light.data.use_shadow = shadow
    look_at(light, target)


def add_sun(
    name: str,
    direction: tuple[float, float, float],
    *,
    energy: float,
    color: tuple[float, float, float],
    angle_deg: float = 1.6,
) -> None:
    """A sun aimed along ``direction`` -- the way the light travels."""
    bpy.ops.object.light_add(type="SUN", location=(0.0, 0.0, 12.0))
    light = bpy.context.object
    light.name = name
    light.data.energy = energy
    light.data.color = color
    light.data.angle = math.radians(angle_deg)
    light.rotation_euler = Vector(direction).to_track_quat("-Z", "Y").to_euler()


def add_point_light(
    name: str, location, *, power: float, color, radius: float, shadow: bool = False
) -> None:
    bpy.ops.object.light_add(type="POINT", location=location)
    light = bpy.context.object
    light.name = name
    light.data.energy = power
    light.data.color = color
    light.data.shadow_soft_size = radius
    # A shadowed point light costs six cube faces; the yard lamps are props and
    # read fine unshadowed.
    light.data.use_shadow = shadow


# ------------------------------------------------------------------ physics


def run_physics(args: argparse.Namespace) -> dict:
    if args.physics_json is not None:
        physics = json.loads(Path(args.physics_json).read_text(encoding="utf-8"))
        validate_cache(physics,{key:getattr(args,key) for key in ('fps','duration_sec','truck_speed','speed_bump_height','cargo_friction')})
        if args.scenario_overrides_json is not None:raise ValueError('Resimulate to change cached timed edits')
        # Reusing a simulation means the geometry has to come from it, not from
        # the command line: the suite renders each edit from its own physics
        # file, and a case that raises the bump would otherwise still draw the
        # baseline one.
        params = physics["physics_parameters"]
        args.truck_speed = float(params["truck_speed"])
        args.speed_bump_height = float(params["speed_bump_height"])
        args.cargo_friction = float(params["cargo_friction"])
        args.fps = int(physics["fps"])
        args.duration_sec = float(physics["duration_sec"])
        return physics
    schedule = apply_physics_overrides(args, cfg.BASELINE_PHYSICS)
    for key in ('fps','duration_sec'):
        if getattr(args,key) is None:setattr(args,key,cfg.BASELINE_RENDER[key])
    for key in cfg.BASELINE_PHYSICS:
        if getattr(args,key) is None:setattr(args,key,cfg.BASELINE_PHYSICS[key])
    if not args.physics_python.exists():
        raise FileNotFoundError(
            "PyBullet runtime is missing. Expected the shared project runtime at "
            f"{PHYSICS_PYTHON}"
        )
    output = args.out_dir / "physics_transforms.json"
    script = Path(__file__).with_name("simulate_flatbed_speed_bump.py")
    command = [
        str(args.physics_python), str(script), "--out", str(output),
        "--fps", str(int(args.fps)),
        "--duration-sec", str(float(args.duration_sec)),
        "--truck-speed", str(float(args.truck_speed)),
        "--speed-bump-height", str(float(args.speed_bump_height)),
        "--cargo-friction", str(float(args.cargo_friction)),
    ]
    if schedule is not None:
        command += ["--timed-edits-json", str(schedule)]
    subprocess.run(command, check=True)
    physics = json.loads(output.read_text(encoding="utf-8"))
    validate_cache(physics)
    return physics


# -------------------------------------------------------------- environment


def add_box_batch(
    name: str,
    boxes: list[tuple[tuple[float, float, float], tuple[float, float, float], float]],
    mat: bpy.types.Material | None,
) -> bpy.types.Object:
    """One mesh holding many boxes: ``[(centre, dimensions, yaw_deg), ...]``.

    Kerbs, lane dashes, hatching and fence posts are hundreds of 0.1-2 m boxes.
    As separate objects each one costs a draw call and a shadow-map page, and
    that is not free: taking the markings out to 160 m sent a 1280x720 still
    from 15 s to 2 min 40 s. Merged into one mesh it is one draw call, and the
    vertices are already in world space, so the object-space texture projection
    the markings use still sees metres. No bevel: at the distance these are read
    at, a 2 cm chamfer is under a pixel.
    """
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    for centre, dimensions, yaw in boxes:
        sx, sy, sz = (d * 0.5 for d in dimensions)
        cos, sin = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        base = len(vertices)
        for dz in (-sz, sz):
            for dx, dy in ((-sx, -sy), (sx, -sy), (sx, sy), (-sx, sy)):
                vertices.append(
                    (
                        centre[0] + dx * cos - dy * sin,
                        centre[1] + dx * sin + dy * cos,
                        centre[2] + dz,
                    )
                )
        faces.extend(
            [
                (base + 0, base + 1, base + 2, base + 3),
                (base + 7, base + 6, base + 5, base + 4),
                (base + 0, base + 4, base + 5, base + 1),
                (base + 1, base + 5, base + 6, base + 2),
                (base + 2, base + 6, base + 7, base + 3),
                (base + 3, base + 7, base + 4, base + 0),
            ]
        )
    return _link(name, _mesh_from(f"{name}_mesh", vertices, faces), mat, None)


def build_roadway() -> None:
    # The apron runs well past the haul road in both directions. With only the
    # road's own length the ground plane ended mid-frame, so a chase rig at the
    # far end of the run looked straight off the edge of the set and into the
    # grass in the HDRI.
    add_box(
        "yard_ground", (0.0, 1.0, -0.24),
        (2.0 * GROUND_HALF_X, 2.0 * GROUND_HALF_Y, 0.40), MAT["concrete"], bake=True,
    ).visible_shadow = False
    add_box(
        "haul_road", (0.0, 0.0, -0.06),
        (2.0 * VISUAL_ROAD_HALF_LENGTH, 2.0 * VISUAL_ROAD_HALF_WIDTH, 0.12), MAT["asphalt"], bake=True,
    ).visible_shadow = False
    # Kerbs: a bright broken line is the main cue that the camera is moving, so
    # they run the whole marked road and stop where they go sub-pixel.
    marking_end = int(MARKING_HALF_LENGTH)
    kerbs = []
    for side in (-1.0, 1.0):
        for x in range(-25, marking_end, 2):
            kerbs.append(((float(x) + 0.5, side * 4.22, 0.02), (1.94, 0.32, 0.16), 0.0))
    add_box_batch("kerbs", kerbs, MAT["kerb"])
    for side in (-1.0, 1.0):
        add_box(
            f"edge_line_{side}", (0.0, side * 3.62, -0.004),
            (2.0 * VISUAL_ROAD_HALF_LENGTH, 0.14, 0.012), MAT["paint"],
        )
    add_box_batch(
        "lane_dashes",
        [((float(x), 0.0, -0.004), (2.0, 0.13, 0.012), 0.0) for x in range(-25, marking_end, 4)],
        MAT["paint"],
    )
    # Chevron hatching on the near shoulder, the usual yard treatment, and a
    # strong motion cue for the chase camera -- it is the only marking the rig
    # passes at 1.5 m intervals, so it has to run the length of the run too.
    add_box_batch(
        "hatching",
        [
            ((-24.0 + i * 1.5, -3.30, -0.004), (0.16, 1.30, 0.012), 30.0)
            for i in range(int((MARKING_HALF_LENGTH + 24.0) / 1.5))
        ],
        MAT["paint"],
    )


def build_hazard_board() -> None:
    """A hazard board before the bump, on the far shoulder."""
    for i, x in enumerate((-9.0, 9.0)):
        add_box(f"hazard_post_{i}", (x, 4.9, 0.72), (0.10, 0.10, 1.44), MAT["steel_dark"])
        add_box(f"hazard_board_{i}", (x, 4.86, 1.52), (1.30, 0.06, 0.60), MAT["hazard"], bevel=0.02)
        for j in range(5):
            lean = add_box(
                f"hazard_chevron_{i}_{j}",
                (x - 0.52 + 0.26 * j, 4.82, 1.52), (0.10, 0.02, 0.58), MAT["rubber_bump"],
            )
            lean.rotation_euler[1] = math.radians(28.0)


# The containers, lamp masts and the speed hump are imported scenery now --
# see import_props.py. The gantry crane and the warehouse facade that used to
# stand behind the boxes are gone: they were the two largest procedural masses
# left in shot, and the yard reads better against the sky than against a wall.


def build_fence() -> None:
    """Roadside hoarding on both kerbs.

    The cones, drums and pallets that used to stand on the near shoulder are
    gone: from a fixed vantage they read as loose toys dropped next to the road
    rather than as yard clutter, and nothing in the shot needed them.

    Both sides are fenced now that both sides hold a container block: a yard
    that stores boxes on one side and leaves the other open does not exist. The
    near fence sits just outside the kerb (y = -4.55) and the sight line to the
    truck crosses it at ~1.9 m, above the 1.24 m posts, so it frames the bottom
    of the shot without ever covering the truck.
    """
    span = range(-60, int(MARKING_HALF_LENGTH), 2)
    for side_y, tag in ((4.55, "f"), (-4.55, "n")):
        add_box_batch(
            f"fence_posts_{tag}",
            [((float(x), side_y, 0.62), (0.09, 0.09, 1.24), 0.0) for x in span],
            MAT["fence"],
        )
        add_box_batch(
            f"fence_rails_{tag}",
            [
                ((float(x) + 1.0, side_y, z), (2.0, 0.045, 0.075 if z > 0.5 else 0.055), 0.0)
                for x in span
                for z in (1.10, 0.24)
            ],
            MAT["fence"],
        )


def build_environment(bump_height: float, bump_width: float) -> None:
    import scene_support.flatbed_speed_bump.import_props as props

    build_roadway()
    props.build_speed_hump(float(bump_height), float(bump_width), VISUAL_ROAD_HALF_WIDTH)
    build_hazard_board()
    props.build_container_yard()
    build_fence()
    # The lamp's glow has to be hung off the post's own head, so the imported
    # geometry reports where that ended up instead of the light being placed
    # from a remembered height. Nothing is hung in daylight: five 520 W warm
    # pools under a sun that is still 30 degrees up is the single most obvious
    # "this was lit by hand" tell in the frame.
    heads = props.build_lamp_posts()
    if props.LAMPS_LIT:
        for index, head in enumerate(heads):
            add_point_light(
                f"lamp_glow_{index}", head,
                power=520.0, color=(1.0, 0.66, 0.36), radius=0.45, shadow=False,
            )


# --------------------------------------------------------------- the truck


def build_chassis() -> tuple[bpy.types.Object, list[bpy.types.Object]]:
    """Rigid chassis: frame, cab, wheels. Returns the root and the wheels."""
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0.0, 0.0, 0.0))
    root = bpy.context.object
    root.name = "truck_chassis"
    v = cfg.CHASSIS_COM_Z  # chassis-local = V-relative minus the centre of mass

    add_box(
        "truck_frame", (0.0, 0.0, cfg.FRAME_Z - v),
        tuple(2.0 * s for s in cfg.FRAME_HALF), MAT["steel_dark"], bevel=0.05, parent=root,
    )
    add_box(
        "truck_frame_top", (0.0, 0.0, cfg.FRAME_Z + cfg.FRAME_HALF[2] - v + 0.02),
        (2.84, 1.18, 0.05), MAT["steel_pale"], bevel=0.02, parent=root,
    )
    # Suspension air bags straddling the deck/frame gap.
    for i, (x, y) in enumerate(((-0.98, -0.5), (-0.98, 0.5), (0.62, -0.5), (0.62, 0.5))):
        add_cylinder(
            f"suspension_bag_{i}", (x, y, cfg.FRAME_Z + 0.06 - v), 0.13, 0.22,
            MAT["rubber"], parent=root,
        )
    # Cab, forward of the deck's front edge so it never presses on the deck.
    add_box(
        "truck_cab", (cfg.CAB_X, 0.0, cfg.CAB_Z - v),
        tuple(2.0 * s for s in cfg.CAB_HALF), MAT["cab_white"], bevel=0.09, parent=root,
    )
    add_box(
        "truck_cab_skirt", (cfg.CAB_X, 0.0, 0.56 - v), (0.86, 1.10, 0.44),
        MAT["cab_blue"], bevel=0.04, parent=root,
    )
    add_box(
        "truck_windshield", (cfg.CAB_X + cfg.CAB_HALF[0] - 0.02, 0.0, cfg.CAB_Z + 0.16 - v),
        (0.03, 0.98, 0.42), MAT["glass"], bevel=0.02, parent=root,
    )
    add_box(
        "truck_side_window_l", (cfg.CAB_X, -cfg.CAB_HALF[1] + 0.01, cfg.CAB_Z + 0.14 - v),
        (0.50, 0.02, 0.34), MAT["glass"], parent=root,
    )
    add_box(
        "truck_side_window_r", (cfg.CAB_X, cfg.CAB_HALF[1] - 0.01, cfg.CAB_Z + 0.14 - v),
        (0.50, 0.02, 0.34), MAT["glass"], parent=root,
    )
    add_box(
        "truck_grille", (cfg.CAB_X + cfg.CAB_HALF[0] - 0.01, 0.0, cfg.CAB_Z - 0.20 - v),
        (0.05, 0.80, 0.26), MAT["steel_dark"], bevel=0.02, parent=root,
    )
    for side, label in ((-1.0, "l"), (1.0, "r")):
        add_box(
            f"truck_headlamp_{label}",
            (cfg.CAB_X + cfg.CAB_HALF[0] - 0.01, side * 0.38, cfg.CAB_Z - 0.05 - v),
            (0.05, 0.24, 0.14), MAT["headlamp"], bevel=0.02, parent=root,
        )
    add_box(
        "truck_bumper", (cfg.CAB_X + cfg.CAB_HALF[0] + 0.03, 0.0, 0.44 - v),
        (0.14, 1.16, 0.26), MAT["steel_pale"], bevel=0.03, parent=root,
    )

    wheels: list[bpy.types.Object] = []
    for x in cfg.WHEEL_XS:
        for y in cfg.WHEEL_YS:
            wheel = add_cylinder(
                f"truck_wheel_{x}_{y}", (x, y, -v), cfg.WHEEL_RADIUS, cfg.WHEEL_WIDTH,
                MAT["rubber"], rotation=(math.pi / 2.0, 0.0, 0.0), bake_rotation=True,
                parent=root,
            )
            wheels.append(wheel)
            hub = add_cylinder(
                f"truck_hub_{x}_{y}", (x, y - (0.118 if y < 0 else -0.118), -v),
                cfg.WHEEL_RADIUS * 0.45, 0.03, MAT["hub"],
                rotation=(math.pi / 2.0, 0.0, 0.0), bake_rotation=True, parent=root,
            )
            hub.parent = wheel
            hub.location = (0.0, 0.118 if y < 0 else -0.118, 0.0)
            for spoke in (0.0, math.pi / 2.0):
                bar = add_box(
                    f"truck_spoke_{x}_{y}_{spoke:.2f}", (0.0, 0.118 if y < 0 else -0.118, 0.0),
                    (2.0 * cfg.WHEEL_RADIUS * 0.42, 0.02, 0.05), MAT["hub"], parent=wheel,
                )
                bar.rotation_euler[1] = spoke
    return root, wheels


def build_deck() -> bpy.types.Object:
    """The sprung flatbed deck and its rails, as one empty."""
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0.0, 0.0, 0.0))
    deck = bpy.context.object
    deck.name = "truck_deck"
    add_box(
        "deck_plate", (0.0, 0.0, 0.0), tuple(2.0 * s for s in cfg.DECK_HALF), MAT["deck"],
        bevel=0.03, parent=deck,
    )
    for i, x in enumerate((-1.15, -0.85, -0.45, -0.05, 0.35, 0.75, 1.05)):
        add_box(
            f"deck_plank_{i}", (cfg.DECK_CENTER_X + x, 0.0, cfg.DECK_HALF[2] + 0.004),
            (0.10, 2.0 * cfg.DECK_HALF[1] - 0.05, 0.012), MAT["steel_dark"], parent=deck,
        )
    for i, x in enumerate((-1.30, -0.65, 0.0, 0.65)):
        add_box(
            f"deck_rib_{i}", (cfg.DECK_CENTER_X + x, 0.0, -cfg.DECK_HALF[2] - 0.03),
            (0.10, 2.0 * cfg.DECK_HALF[1] - 0.08, 0.09), MAT["steel_pale"], parent=deck,
        )
    for side in (-1.0, 1.0):
        add_box(
            f"deck_rail_{side}", (cfg.DECK_CENTER_X, side * (cfg.DECK_HALF[1] - 0.03), 0.13),
            (2.0 * cfg.DECK_HALF[0], 0.06, 0.26), MAT["deck_rail"], bevel=0.02, parent=deck,
        )
    add_box(
        "deck_headboard", (cfg.DECK_FRONT_X - 0.04, 0.0, 0.24),
        (0.08, 2.0 * cfg.DECK_HALF[1] - 0.02, 0.48), MAT["deck_rail"], bevel=0.02, parent=deck,
    )
    return deck


def build_cargo() -> list[bpy.types.Object]:
    """The parcels are the imported carton, cloned once per physics body.

    They used to be bevelled boxes with a strap and a label glued on, which read
    as a crate rather than as the thing the benchmark is about. The import
    arrives with its base on z = 0 and its centre on x = y = 0, so it is
    re-centred on the bounding box and baked to identity -- after that a
    keyframe on ``location`` means "box centre", which is exactly what the
    simulation reports.
    """
    import scene_support.flatbed_speed_bump.import_props as props

    return props.build_cargo_cartons(len(cfg.CARGO_HALF_EXTENTS))


# ------------------------------------------------------------- keyframing


def _linearise(obj: bpy.types.Object) -> None:
    if obj.animation_data and obj.animation_data.action:
        for curve in obj.animation_data.action.fcurves:
            for point in curve.keyframe_points:
                point.interpolation = "LINEAR"


def keyframe_from(records: list[dict], key: str, obj: bpy.types.Object) -> None:
    obj.rotation_mode = "QUATERNION"
    for frame in records:
        state = frame[key]
        obj.location = state["location"]
        x, y, z, w = state["quaternion_xyzw"]
        obj.rotation_quaternion = (w, x, y, z)
        obj.keyframe_insert(data_path="location", frame=int(frame["frame_index"]))
        obj.keyframe_insert(data_path="rotation_quaternion", frame=int(frame["frame_index"]))
    _linearise(obj)


def keyframe_cargo(records: list[dict], index: int, obj: bpy.types.Object) -> None:
    obj.rotation_mode = "QUATERNION"
    for frame in records:
        state = frame["cargo"][index]
        obj.location = state["location"]
        x, y, z, w = state["quaternion_xyzw"]
        obj.rotation_quaternion = (w, x, y, z)
        obj.keyframe_insert(data_path="location", frame=int(frame["frame_index"]))
        obj.keyframe_insert(data_path="rotation_quaternion", frame=int(frame["frame_index"]))
    _linearise(obj)


def keyframe_wheel_spin(
    wheels: list[bpy.types.Object], records: list[dict], radius: float
) -> None:
    """Visual-only wheel rotation: constant omega = v / R, wrapped to one turn.

    The wheel proxies in the simulation have no spinning axle, so without this
    the truck slides along with motionless wheels. An imported rig can bring
    mixed wheel sizes (steer axle vs drive axle), so a wheel that carries its
    own ``rolling_radius`` uses that instead of the shared ``radius``.
    """
    for wheel in wheels:
        wheel.rotation_mode = "XYZ"
    previous_x = None
    travelled = 0.0
    for frame in records:
        x = float(frame["chassis"]["location"][0])
        if previous_x is not None:
            travelled += x - previous_x
        previous_x = x
        for wheel in wheels:
            own_radius = float(wheel.get("rolling_radius", radius) or radius)
            angle = -(travelled / own_radius) % (2.0 * math.pi)
            wheel.rotation_euler = (0.0, angle, 0.0)
            wheel.keyframe_insert(data_path="rotation_euler", frame=int(frame["frame_index"]))
    for wheel in wheels:
        _linearise(wheel)


# ------------------------------------------------------------------- scene


def build_scene(args: argparse.Namespace, physics: dict):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    initialize_materials()
    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = args.resolution
    scene.render.resolution_percentage = 100
    scene.render.fps = int(args.fps)
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    scene.render.film_transparent = False
    set_color_property(scene.view_settings, 'look', 'AgX - Medium High Contrast')
    # The depot is supposed to be at dusk; at 124 deg the HDRI put its grey
    # overcast quarter behind the truck, which is why the sky read as flat
    # slate. 300 deg turns the warm low-sun quarter of the same panorama into
    # frame, so there is a horizon gradient above the warehouse roof.
    scene.view_settings.exposure = -0.15
    if args.engine == "cycles":
        scene.render.engine = "CYCLES"
        scene.cycles.samples = int(args.samples)
        scene.cycles.use_denoising = True
        scene.cycles.max_bounces = 8
        scene.cycles.diffuse_bounces = 3
        scene.cycles.glossy_bounces = 4
        scene.cycles.adaptive_threshold = 0.02
        scene.cycles.seed = int(args.seed)
        scene.render.use_persistent_data = True
        scene.cycles.device = "CPU"
        # ``auto`` deliberately stays on the CPU here. This box has an RTX 5060
        # (sm_120), which Blender 4.3 ships no precompiled CUDA kernels for, so
        # asking for the GPU stalls in PTX JIT for tens of minutes. Opt in with
        # PCVE_CYCLES_GPU=1 once the runtime is Blender 4.5+.
        if args.device == "auto" and os.environ.get("PCVE_CYCLES_GPU") == "1":
            prefs = bpy.context.preferences.addons["cycles"].preferences
            try:
                prefs.compute_device_type = "CUDA"
                prefs.get_devices()
                available = [dev for dev in prefs.devices if dev.type == "CUDA"]
                for dev in prefs.devices:
                    dev.use = dev.type == "CUDA"
                if available:
                    scene.cycles.device = "GPU"
                    scene.cycles.denoiser = "OPTIX" if any(
                        dev.type == "OPTIX" for dev in prefs.devices
                    ) else "OPENIMAGEDENOISE"
                    print("[render] CUDA: " + ", ".join(dev.name for dev in available),
                          flush=True)
            except Exception as exc:  # noqa: BLE001 - any CUDA probe failure is a CPU fallback
                scene.cycles.device = "CPU"
                print(f"[render] CPU fallback: {exc}", flush=True)
        # Say it out loud: a CPU render leaves both GPUs near 0 %, which reads
        # as "the GPU is broken" unless the log states the device.
        print(f"[render] cycles device={scene.cycles.device}"
              + ("" if scene.cycles.device == "GPU" else " (set PCVE_CYCLES_GPU=1 to try CUDA)"),
              flush=True)
    else:
        scene.render.engine = eevee_engine()
        set_eevee_property(scene.eevee, 'taa_render_samples', int(args.samples))
        set_eevee_property(scene.eevee, 'use_raytracing', True)
        # Ground-truth AO at 2 m was smearing every contact shadow into grey
        # fog; at 0.45 m it reads as occlusion instead of dirt.
        set_eevee_property(scene.eevee, 'use_gtao', True)
        set_eevee_property(scene.eevee, 'gtao_distance', 0.45)

    # An actual sky instead of a constant colour. Without an environment there
    # is nothing for the cab paint, the brass and the wet asphalt to reflect,
    # which is the single biggest reason the old render looked like plastic.
    world = bpy.data.worlds.new("industrial_dusk_world")
    scene.world = world
    world.use_nodes = True
    world_nodes = world.node_tree.nodes
    world_links = world.node_tree.links
    environment = world_nodes.new("ShaderNodeTexEnvironment")
    environment.image = _asset_image(f"{HDRI_STEM}_2k.hdr", "Linear Rec.709")
    rotation = world_nodes.new("ShaderNodeMapping")
    rotation.inputs["Rotation"].default_value[2] = math.radians(300.0)
    direction = world_nodes.new("ShaderNodeTexCoord")
    world_links.new(direction.outputs["Generated"], rotation.inputs["Vector"])
    world_links.new(rotation.outputs["Vector"], environment.inputs["Vector"])
    background = world_nodes.get("Background")
    background.inputs["Strength"].default_value = 1.0
    world_links.new(environment.outputs["Color"], background.inputs["Color"])
    # The sky the camera sees and the sky that lights the scene are two
    # different exposures. Feeding the full-strength HDRI into the lighting
    # flattens the frame -- the sun's shadow ratio collapsed and every prop
    # landed on one value. Camera rays keep the bright panorama; diffuse and
    # glossy rays see it at 0.45, which lets the sun key carry the modelling.
    light_background = world_nodes.new("ShaderNodeBackground")
    light_background.inputs["Strength"].default_value = 0.45
    world_links.new(environment.outputs["Color"], light_background.inputs["Color"])
    light_path = world_nodes.new("ShaderNodeLightPath")
    sky_mix = world_nodes.new("ShaderNodeMixShader")
    output = world_nodes.get("World Output")
    world_links.new(light_path.outputs["Is Camera Ray"], sky_mix.inputs["Fac"])
    world_links.new(light_background.outputs["Background"], sky_mix.inputs[1])
    world_links.new(background.outputs["Background"], sky_mix.inputs[2])
    world_links.new(sky_mix.outputs["Shader"], output.inputs["Surface"])

    build_environment(float(args.speed_bump_height),float(physics["geometry"]["speed_bump_width"]))
    if args.truck_asset == "imported":
        # import_truck is a top-level shared module: its virtual path has no
        # scene folder above it, and under `blender -b` sys.argv[0] is the
        # blender binary, so scene_root() cannot locate simulate_/render_.
        # Point argv[0] at this scene script for the duration of the import.
        _argv0_restore = sys.argv[0]
        sys.argv[0] = str(Path(__file__).resolve())
        try:
            import import_truck
        finally:
            sys.argv[0] = _argv0_restore

        chassis, deck, wheels = import_truck.build_truck(args.truck_glb)
    else:
        chassis, wheels = build_chassis()
        deck = build_deck()
    cargo = build_cargo()

    keyframe_from(physics["frames"], "chassis", chassis)
    keyframe_from(physics["frames"], "bed", deck)
    for index, obj in enumerate(cargo):
        keyframe_cargo(physics["frames"], index, obj)
    keyframe_wheel_spin(wheels, physics["frames"], cfg.WHEEL_RADIUS)

    # A low warm sun instead of a big soft box overhead. The area key lit every
    # face from every side, so the truck cast no readable shadow and the whole
    # yard landed on one flat value -- the "toy diorama" read. The sun comes
    # from behind the rig's left shoulder, so the flank and tail the wide camera
    # sees are the lit ones and the shadow runs away across the empty road.
    add_sun("dusk_sun", (0.62, 0.66, -0.42), energy=4.2, color=(1.0, 0.79, 0.56))
    add_area_light("sky_fill", (7.0, -5.0, 5.2), (0.0, 0.0, 1.2),
                   power=170.0, size=14.0, color=(0.55, 0.70, 1.0), shadow=False)

    # Every rig is bolted to the ground and nothing follows the truck.
    # ``static`` is the tight hero frame, ``wide`` the three-quarter still,
    # ``survey`` a fixed wide, and ``clip4s`` the one that holds the 41 m run.
    preset = CAMERA_PRESETS[args.camera_mode]
    bpy.ops.object.camera_add(location=preset["location"])
    camera = bpy.context.object
    camera.name = "camera"
    camera.data.lens = preset["lens_mm"]
    camera.data.sensor_width = 36.0
    # A wide-open aperture is what separates a photograph from a game screenshot:
    # the container wall behind the truck picks up a little falloff, so the eye
    # stops treating every plane as equally sharp. The survey rig stops down
    # instead -- both ends of a 28 m run have to stay legible.
    camera.data.dof.use_dof = True
    camera.data.dof.focus_distance = (
        (Vector(preset["target"]) - Vector(preset["location"])).length
        + preset["focus_offset"]
    )
    camera.data.dof.aperture_fstop = preset["fstop"]
    scene.camera = camera
    target = bpy.data.objects.new("camera_target", None)
    scene.collection.objects.link(target)
    target.location = preset["target"]
    constraint = camera.constraints.new("TRACK_TO")
    constraint.target = target
    constraint.track_axis = "TRACK_NEGATIVE_Z"
    constraint.up_axis = "UP_Y"

    scene.frame_start = 1
    scene.frame_end = int(physics["frame_end"])
    scene.frame_set(1)
    return chassis, deck, cargo, camera


# ----------------------------------------------------------------- outputs


def export_ground_truth(
    out_dir: Path, chassis, deck, cargo, camera, physics: dict, scenario: dict
) -> None:
    scene = bpy.context.scene
    records = {
        "schema_version": 3,
        "fps": int(physics["fps"]),
        "frame_start": 1,
        "frame_end": int(physics["frame_end"]),
        "physics": {key: value for key, value in physics.items() if key != "frames"},
        "objects": {
            "truck_chassis": {"object_name": chassis.name},
            "truck_deck": {"object_name": deck.name},
            "cargo": [{"object_name": obj.name} for obj in cargo],
        },
        "camera": {
            "object_name": camera.name,
            "lens_mm": float(camera.data.lens),
            "resolution": [int(scene.render.resolution_x), int(scene.render.resolution_y)],
        },
        "scenario": scenario,
        "frames": [],
    }
    physics_by_frame = {int(frame["frame_index"]): frame for frame in physics["frames"]}
    for frame_index in range(1, int(physics["frame_end"]) + 1):
        scene.frame_set(frame_index)
        physical = physics_by_frame[frame_index]
        records["frames"].append({
            "frame_index": frame_index,
            "time_sec": (frame_index - 1) / float(physics["fps"]),
            "truck_chassis": {
                "matrix_world": [[float(v) for v in row] for row in chassis.matrix_world],
                "linear_velocity": physical["chassis"]["linear_velocity"],
                "angular_velocity": physical["chassis"]["angular_velocity"],
            },
            "truck_deck": {
                "matrix_world": [[float(v) for v in row] for row in deck.matrix_world],
                "linear_velocity": physical["bed"]["linear_velocity"],
                "angular_velocity": physical["bed"]["angular_velocity"],
                "suspension_travel": physical["bed"]["suspension_travel"],
            },
            "cargo": [
                {
                    "matrix_world": [[float(v) for v in row] for row in obj.matrix_world],
                    "linear_velocity": physical["cargo"][i]["linear_velocity"],
                    "angular_velocity": physical["cargo"][i]["angular_velocity"],
                    "airborne": physical["cargo"][i]["airborne"],
                    "deck_clearance": physical["cargo"][i]["deck_clearance"],
                }
                for i, obj in enumerate(cargo)
            ],
            "camera_matrix_world": [[float(v) for v in row] for row in camera.matrix_world],
        })
    (out_dir / GROUND_TRUTH_NAME).write_text(json.dumps(records, indent=2), encoding="utf-8")


def render_preview(args: argparse.Namespace) -> None:
    """One still at ``--preview-frame``."""
    scene = bpy.context.scene
    scene.render.image_settings.file_format = "PNG"
    scene.frame_set(max(scene.frame_start, min(int(args.preview_frame), scene.frame_end)))
    scene.render.filepath = str(args.out_dir / "preview.png")
    bpy.ops.render.render(write_still=True)


def render_sampled(args: argparse.Namespace) -> None:
    """Evenly-spaced stills, the same ``--mode sampled`` convention as
    ``ball_block_building``: writes ``frame_<N>.png`` plus a JSON of the indices
    so a clip can be inspected without rendering every frame.
    """
    scene = bpy.context.scene
    scene.render.image_settings.file_format = "PNG"
    frame_end = int(scene.frame_end)
    if not 2 <= int(args.frame_count) <= frame_end:
        raise ValueError(f"--frame-count must be between 2 and {frame_end}")
    indices = [
        1 + round(i * (frame_end - 1) / (int(args.frame_count) - 1))
        for i in range(int(args.frame_count))
    ]
    for index in indices:
        scene.frame_set(index)
        scene.render.filepath = str(args.out_dir / f"frame_{index:04d}.png")
        bpy.ops.render.render(write_still=True)
        print(f"[render] frame {index} -> frame_{index:04d}.png", flush=True)
    (args.out_dir / "sampled_frames.json").write_text(
        json.dumps({"frame_indices": indices, "frame_end": frame_end}), encoding="utf-8"
    )


def main() -> None:
    import time

    started = time.perf_counter()
    args = parse_args()
    # Blender resolves relative render paths against its own base directory.
    args.out_dir = args.out_dir.resolve()
    if args.physics_json is not None:args.physics_json=args.physics_json.resolve()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    # Written after the physics is loaded on purpose: a run that reuses a
    # simulation file has its parameters filled in from that file, and the
    # metadata has to report what was actually rendered.
    physics = run_physics(args)
    scenario = {
        "schema_version": 3,
        "seed": int(args.seed),
        "environment": "dusk_container_depot_haul_road",
        "scene": "loaded_flatbed_truck_crosses_rounded_speed_bump",
        "camera_mode": args.camera_mode,
        "render": {
            "mode": args.mode, "fps": int(args.fps), "duration_sec": float(args.duration_sec),
            "resolution": [int(args.resolution[0]), int(args.resolution[1])],
            "samples": int(args.samples),
            "engine": "cycles" if args.engine == "cycles" else "eevee_next",
            "device": str(args.device),
        },
        "physics_params": {
            "truck_speed": float(args.truck_speed),
            "speed_bump_height": float(args.speed_bump_height),
            "cargo_friction": float(args.cargo_friction),
        },
    }
    (args.out_dir / SCENARIO_METADATA_NAME).write_text(
        json.dumps(scenario, indent=2), encoding="utf-8"
    )
    chassis, deck, cargo, camera = build_scene(args, physics)
    print(
        f"[render] scene built in {time.perf_counter() - started:.1f}s "
        f"({len(bpy.data.objects)} objects)",
        flush=True,
    )
    export_ground_truth(args.out_dir, chassis, deck, cargo, camera, physics, scenario)

    if args.mode == "preview":
        render_preview(args)
    elif args.mode == "sampled":
        render_sampled(args)
    else:
        bpy.context.scene.render.filepath = str(args.out_dir / f"{OUTPUT_STEM}.mp4")
        bpy.ops.render.render(animation=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.out_dir / f"{OUTPUT_STEM}.blend"))
    print(f"[render] complete: {args.out_dir}")


if __name__ == "__main__":
    run_renderer(main, 'flatbed_speed_bump')

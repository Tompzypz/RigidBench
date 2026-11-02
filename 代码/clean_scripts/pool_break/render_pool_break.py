"""Render the pool-break scene with Blender's Python API.

The setting is a pool hall after hours: one table lit from above, the hall
around it dim but furnished -- panelled walls, two wooden chairs, a bin, three
prints. The table is its own model (``table_model``), fitted so its cloth is the
simulation's felt plane and its cushion noses are the simulation's cushion
planes. Only the four balls of the shot are in play -- ``pool_table_animation``
ships a full fifteen-ball rack plus two cue sticks, and every ball the shot does
not use, along with that file's own low-poly table, is hidden on import rather
than moved.

The camera is bolted to a fixed rig behind the cue ball, looking down the table.
It does not follow anything: the ball travels through the frame and the rack
opens away from it, which is the motion the scene exists to show. ``--camera-mode
survey`` swaps in a higher three-quarter rig that holds the whole table, for
inspecting where the balls ended up rather than how they got there.

Everything the balls do is keyed from the matching PyBullet run -- locations and
rolling orientations per frame -- so the video and the ground-truth trajectory
file are the same numbers.
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

import scene_support.pool_break.props as prop_lib  # noqa: E402
import scene_support.pool_break.scene_config as cfg  # noqa: E402
import scene_support.pool_break.table_model as table_lib  # noqa: E402
import scene_support.pool_break.wall_decor as wall_decor  # noqa: E402
from scene_support.pool_break.cache_contract import validate_cache  # noqa: E402
from scene_support.pool_break.runtime_support import python_for  # noqa: E402


WORKSPACE_DIR = _PCVE_PROJECT_ROOT
PHYSICS_PYTHON = python_for("physics")

OUTPUT_STEM = "pool_break"
GROUND_TRUTH_NAME = "ground_truth_transforms.json"
SCENARIO_METADATA_NAME = "scenario_metadata.json"

BALL_OBJECTS = {
    "cue_ball": cfg.CUE_BALL_MESH,
    "apex_ball": cfg.APEX_BALL_MESH,
    "left_ball": cfg.LEFT_BALL_MESH,
    "right_ball": cfg.RIGHT_BALL_MESH,
}

# Camera rigs. Kept here rather than in ``scene_config.py`` on purpose: that file
# is hashed by ``cache_contract.signature()``, so touching a camera constant
# would invalidate every cached trajectory.
#
# ``break``   low at the head end, looking down the table. The cue ball sits in
#             the near third of the frame and the rack is away in the middle,
#             so the shot has depth and the ball's run reads as a run rather
#             than as a dot sliding sideways -- which is what the first, 50
#             degree overhead rig made it look like. The rig holds the *whole*
#             table -- playing surface, all four pockets, the near apron's outer
#             edge -- because a break is not over where it starts: the two wings
#             run to the side cushions. That last part is what fixed the numbers
#             twice now: a rig can hold every cushion and still crop the near
#             apron, and then the table reads as a tray sliding off the bottom
#             of the frame.
# ``survey``  the same table from higher and further back with the floor in
#             shot, for first/middle/last reviews and batch thumbnails.
#
# Both were re-fitted when the table model changed. The old table was a low-poly
# asset whose rails stopped 80 mm outside the cushion noses; the imported one
# carries 200 mm of rail and a 60 mm frame all round, so its footprint is 2.18 x
# 1.30 m instead of 1.97 x 1.08 m on the same 1.81 x 0.93 m playing surface. On
# the old 25 mm rig that extra footprint put the two near corners off frame --
# at u = 1.03 and v = -0.13, i.e. cropped by both the right and the bottom edge
# -- so the lens went to 21 mm and the body stepped back to x = 1.90 m, which is
# as far back as the hall's side walls reach. The aim point dropped 60 mm for
# the same reason: it is the cheapest way to buy bottom margin without raising
# the camera, and at this distance it is a 1.7 degree tilt. The cost is the
# honest one -- a 57 mm ball lands about 20 px across at the cue spot and 13-16
# px in the rack, 2-3 px less than before the swap, and no lens choice changes
# the ratio between the ball and the table.
CAMERA_PRESETS = {
    "break": dict(
        location=(1.90, -0.54, 0.88), target=(-0.10, 0.0, -0.04),
        lens_mm=21.0, fstop=5.6, focus_offset=0.0,
    ),
    "survey": dict(
        location=(1.90, -1.00, 1.52), target=(-0.10, 0.0, 0.0),
        lens_mm=18.0, fstop=8.0, focus_offset=0.0,
    ),
}


from pcve_scene_runtime import parse_render_args, run_renderer, apply_physics_overrides

def parse_args() -> argparse.Namespace:
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
    parser = argparse.ArgumentParser(description="Render a three-ball pool break.")
    parser.add_argument("--mode", choices=("preview", "animation", "sampled"), default="animation")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--resolution", nargs=2, type=int, default=cfg.BASELINE_RENDER["resolution"])
    parser.add_argument("--fps", type=int, default=cfg.BASELINE_RENDER["fps"])
    parser.add_argument("--duration-sec", type=float, default=cfg.BASELINE_RENDER["duration_sec"])
    parser.add_argument("--samples", type=int, default=cfg.BASELINE_RENDER["samples"])
    parser.add_argument("--preview-frame", type=int, default=14,
                        help="Frame for preview mode; 14 is just after the contact at the default speed.")
    parser.add_argument("--frame-count", type=int, default=6,
                        help="Number of evenly-spaced stills in sampled mode.")
    parser.add_argument("--seed", type=int, default=3110)
    parser.add_argument("--device", choices=("auto", "cpu"), default="auto")
    parser.add_argument("--engine", choices=("eevee", "cycles"), default="eevee")
    parser.add_argument("--camera-mode", choices=tuple(CAMERA_PRESETS),
                        default=cfg.BASELINE_RENDER["camera_mode"])
    # The three exposed controls. Left at None they fall back to the shared
    # baseline, so a caller that renders an existing physics file need not
    # repeat them.
    parser.add_argument("--cue-speed", type=float)
    parser.add_argument("--cue-contact-offset", type=float)
    parser.add_argument("--cue-mass", type=float)
    parser.add_argument("--scenario-overrides-json", type=Path)
    parser.add_argument("--physics-json", type=Path, default=None,
                        help="Replay a simulation result instead of running PyBullet.")
    parser.add_argument("--timed-edits-json", type=Path, default=None)
    return parse_render_args(parser, argv)


# ------------------------------------------------------------------ physics


def run_physics(args: argparse.Namespace) -> dict:
    """Reuse a trajectory, or simulate one with the same interpreter the suite uses."""
    if args.physics_json is not None:
        if args.scenario_overrides_json is not None:raise ValueError("Resimulate to change cached physics")
        data = json.loads(Path(args.physics_json).resolve().read_text(encoding="utf-8"))
        validate_cache(data)
        params = data["physics_parameters"]
        for name in ("cue_speed", "cue_contact_offset", "cue_mass"):
            requested = getattr(args, name)
            if requested is not None and abs(float(requested) - float(params[name])) > 1e-12:
                raise ValueError(
                    f"--{name.replace('_', '-')} is {requested} but the cached "
                    f"trajectory was solved with {params[name]}; drop the flag or "
                    "resimulate"
                )
        return data

    schedule = apply_physics_overrides(args, cfg.BASELINE_PHYSICS)
    if schedule is not None:
        if args.timed_edits_json is not None:raise ValueError("Use one timed-edit schedule")
        args.timed_edits_json = schedule
    out_path = Path(args.out_dir) / "physics_transforms.json"
    command = [
        str(args.physics_python),
        str(Path(__file__).with_name("simulate_pool_break.py")),
        "--out", str(out_path),
        "--fps", str(int(args.fps)),
        "--duration-sec", str(float(args.duration_sec)),
        "--cue-speed", str(float(args.cue_speed if args.cue_speed is not None
                                  else cfg.BASELINE_PHYSICS["cue_speed"])),
        "--cue-contact-offset", str(float(
            args.cue_contact_offset if args.cue_contact_offset is not None
            else cfg.BASELINE_PHYSICS["cue_contact_offset"])),
        "--cue-mass", str(float(args.cue_mass if args.cue_mass is not None
                                else cfg.BASELINE_PHYSICS["cue_mass"])),
    ]
    if args.timed_edits_json is not None:
        command += ["--timed-edits-json", str(Path(args.timed_edits_json).resolve())]
    subprocess.run(command, check=True)
    return json.loads(out_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- materials


# The flat-colour helper that used to sit here went with the flat colours: the
# walls, the panelling and the rails are procedural now, and the props and the
# pictures bring their own materials.


def _world_position(nodes):
    """World-space position, for texturing geometry that is a scaled unit cube.

    Every wall and moulding in the room is a 1 m cube with a non-uniform
    object scale, so ``Object`` and ``Generated`` coordinates both arrive
    stretched by that scale -- a 0.12 x 4.1 x 2.6 m wall would receive noise
    squashed 34:1 across its face, and two neighbouring walls would not agree
    on where a patch of grain is. ``Geometry > Position`` is world space, so
    one noise field covers the whole room and the walls continue into each
    other at the corner.
    """
    geometry = nodes.new("ShaderNodeNewGeometry")
    return geometry.outputs["Position"]


def _noise(nodes, links, vector_socket, *, scale: float, detail: float,
           roughness: float = 0.5, stretch=None, distortion: float = 0.0):
    socket = vector_socket
    if stretch is not None:
        mapping = nodes.new("ShaderNodeMapping")
        mapping.inputs["Scale"].default_value = stretch
        links.new(socket, mapping.inputs["Vector"])
        socket = mapping.outputs["Vector"]
    tex = nodes.new("ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value = scale
    tex.inputs["Detail"].default_value = detail
    tex.inputs["Roughness"].default_value = roughness
    tex.inputs["Distortion"].default_value = distortion
    links.new(socket, tex.inputs["Vector"])
    return tex


def _mix_color(nodes, links, blend: str, a, b, factor: float = 1.0):
    """Colour mix taking sockets or literal colours on either side."""
    node = nodes.new("ShaderNodeMix")
    node.data_type = "RGBA"
    node.blend_type = blend
    node.inputs["Factor"].default_value = factor
    for socket, value in ((node.inputs[6], a), (node.inputs[7], b)):
        if isinstance(value, (tuple, list)):
            socket.default_value = (*value, 1.0) if len(value) == 3 else tuple(value)
        else:
            links.new(value, socket)
    return node.outputs[2]


def _map_range(nodes, links, source, *, from_min: float, from_max: float,
               to_min: float, to_max: float, interpolation: str = "LINEAR"):
    node = nodes.new("ShaderNodeMapRange")
    node.clamp = True
    node.interpolation_type = interpolation
    node.inputs["From Min"].default_value = from_min
    node.inputs["From Max"].default_value = from_max
    node.inputs["To Min"].default_value = to_min
    node.inputs["To Max"].default_value = to_max
    links.new(source, node.inputs["Value"])
    return node.outputs["Result"]


def _object_tint(nodes, links, *, low: float, high: float):
    """A per-object grey multiplier, so no two boards are the same board.

    The panelling is fifty separate boxes sharing two materials, and sharing a
    material meant they all came out the same value -- a wall of identical
    stiles reads as printed wallpaper no matter how good the grain is. Object
    Info's Random is seeded per object, so each stile, rail and panel field
    picks up its own slight tone difference, which is also what real joinery
    does: boards are cut from different lengths of the same tree and stained in
    different batches.
    """
    info = nodes.new("ShaderNodeObjectInfo")
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (low, low, low, 1.0)
    ramp.color_ramp.elements[1].color = (high, high, high, 1.0)
    links.new(info.outputs["Random"], ramp.inputs["Fac"])
    return ramp.outputs["Color"]


def plaster_material(floor_z: float) -> bpy.types.Material:
    """Lime-washed plaster, mottled at two scales, dirty at the skirting.

    A wall with one albedo is the single loudest CG tell in a room: real paint
    is never one value, and at four metres the eye is not reading detail, it is
    reading *variation*. So there are three fields on top of each other -- a
    broad patchiness about a metre across, a fine tooth at 2 cm, and a grime
    gradient that darkens the bottom 0.6 m of the wall and dies out before the
    rail. The grime is doing the work that ambient occlusion cannot: EEVEE's
    occlusion radius is set to 60 mm for the balls' contact shadows, so the
    wall-to-floor join gets none, and a wall that meets the floor at the same
    value it has at eye height reads as a backdrop rather than a surface.

    Nothing here is a texture map. It is noise on world position, which is
    free to evaluate and needs no UVs on any of the boxes.
    """
    mat = bpy.data.materials.new("hall_plaster")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.92
    if "Specular IOR Level" in bsdf.inputs:
        # Chalky paint, not vinyl: a quarter of the default specular keeps the
        # wall matte while still letting the sconces draw a soft falloff on it.
        # At 0.32 the sheen was reading as a broad satin wash across the whole
        # wall, which is what a painted backdrop looks like, not a painted wall.
        set_shader_input(bsdf, 'Specular IOR Level', 0.24)

    position = _world_position(nodes)

    patch = _noise(nodes, links, position, scale=0.85, detail=5.0, roughness=0.58)
    tone = nodes.new("ShaderNodeValToRGB")
    tone.color_ramp.interpolation = "EASE"
    tone.color_ramp.elements[0].position = 0.30
    tone.color_ramp.elements[0].color = (0.079, 0.076, 0.068, 1.0)
    tone.color_ramp.elements[1].position = 0.74
    tone.color_ramp.elements[1].color = (0.178, 0.173, 0.154, 1.0)
    links.new(patch.outputs["Fac"], tone.inputs["Fac"])

    tooth = _noise(nodes, links, position, scale=46.0, detail=6.0, roughness=0.62)
    tooth_tone = nodes.new("ShaderNodeValToRGB")
    tooth_tone.color_ramp.elements[0].color = (0.92, 0.92, 0.915, 1.0)
    tooth_tone.color_ramp.elements[1].color = (1.05, 1.05, 1.04, 1.0)
    links.new(tooth.outputs["Fac"], tooth_tone.inputs["Fac"])

    color = _mix_color(nodes, links, "MULTIPLY", tone.outputs["Color"],
                       tooth_tone.outputs["Color"])

    split = nodes.new("ShaderNodeSeparateXYZ")
    links.new(position, split.inputs["Vector"])
    grime = _map_range(nodes, links, split.outputs["Z"],
                       from_min=floor_z, from_max=floor_z + 0.60,
                       to_min=0.58, to_max=1.0, interpolation="SMOOTHSTEP")
    color = _mix_color(nodes, links, "MULTIPLY", color, grime)
    # Three wall boxes, three slightly different walls. Kept to +-5%: enough
    # that the far wall and the side wall are not the same paint sample, small
    # enough that nobody reads it as a patch.
    color = _mix_color(nodes, links, "MULTIPLY", color,
                       _object_tint(nodes, links, low=0.95, high=1.05))
    links.new(color, bsdf.inputs["Base Color"])

    roughness = _map_range(nodes, links, tooth.outputs["Fac"],
                           from_min=0.0, from_max=1.0, to_min=0.87, to_max=0.95)
    links.new(roughness, bsdf.inputs["Roughness"])

    bump = nodes.new("ShaderNodeBump")
    # Just enough to break the specular, not enough to read as a fabric. At
    # 1.5 mm of relief the 2 cm noise was printing as a felt tooth on a wall
    # four metres away; plaster is almost smooth and the mottling above is
    # doing the work.
    bump.inputs["Strength"].default_value = 0.07
    bump.inputs["Distance"].default_value = 0.0010
    links.new(tooth.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def panel_wood_material(name: str, *, dark, light, floor_z: float,
                        roughness: tuple[float, float]) -> bpy.types.Material:
    """Stained joinery with the grain running up the panel.

    The grain is the same noise field as the plaster, stretched 15:1 along Z so
    the streaks run vertically on all four walls without any per-object UV
    work. The rails and stiles are separate boxes but share this material, so
    they pick up the grain from the same field instead of each looking like a
    plank of a different tree.
    """
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]

    position = _world_position(nodes)
    # 17 mm across, a third of a metre long: the proportions of a grain band.
    # The first attempt stretched a 3 cm noise 7:1 and produced 10 cm smears,
    # which read as mould rather than as wood.
    grain = _noise(nodes, links, position, scale=60.0, detail=5.0, roughness=0.6,
                   stretch=(1.0, 1.0, 0.06), distortion=0.35)
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "EASE"
    ramp.color_ramp.elements[0].position = 0.34
    ramp.color_ramp.elements[0].color = (*dark, 1.0)
    ramp.color_ramp.elements[1].position = 0.74
    ramp.color_ramp.elements[1].color = (*light, 1.0)
    links.new(grain.outputs["Fac"], ramp.inputs["Fac"])

    # A second, much finer pass, stretched the same way. One noise field alone
    # gives bands but no lines: at four metres a stained board has visible
    # grain lines separated by flat-ish wood, and without them the panelling
    # reads as laminate with a blur printed on it.
    fine = _noise(nodes, links, position, scale=170.0, detail=3.0, roughness=0.5,
                  stretch=(1.0, 1.0, 0.12), distortion=0.9)
    fine_tone = nodes.new("ShaderNodeValToRGB")
    fine_tone.color_ramp.elements[0].position = 0.30
    fine_tone.color_ramp.elements[0].color = (0.80, 0.80, 0.80, 1.0)
    fine_tone.color_ramp.elements[1].position = 0.72
    fine_tone.color_ramp.elements[1].color = (1.08, 1.08, 1.07, 1.0)
    links.new(fine.outputs["Fac"], fine_tone.inputs["Fac"])

    color = _mix_color(nodes, links, "MULTIPLY", ramp.outputs["Color"],
                       fine_tone.outputs["Color"])
    color = _mix_color(nodes, links, "MULTIPLY", color,
                       _object_tint(nodes, links, low=0.84, high=1.12))

    # Feet, chairs and mops take the finish off the bottom of a panelled wall
    # first, and it is the one place on the panelling where a soft gradient
    # does not look like dirt painted on: it is a band that stops where the
    # ankle stops, well below the eye.
    split = nodes.new("ShaderNodeSeparateXYZ")
    links.new(position, split.inputs["Vector"])
    wear = _map_range(nodes, links, split.outputs["Z"],
                      from_min=floor_z, from_max=floor_z + 0.55,
                      to_min=0.72, to_max=1.0, interpolation="SMOOTHSTEP")
    color = _mix_color(nodes, links, "MULTIPLY", color, wear)
    links.new(color, bsdf.inputs["Base Color"])

    rough = _map_range(nodes, links, grain.outputs["Fac"],
                       from_min=0.0, from_max=1.0,
                       to_min=roughness[0], to_max=roughness[1])
    links.new(rough, bsdf.inputs["Roughness"])

    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.14
    bump.inputs["Distance"].default_value = 0.0012
    links.new(grain.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def room_materials() -> dict[str, bpy.types.Material]:
    """The hall itself: stained joinery and warm lime plaster.

    Every value here is deliberately below the cloth's albedo. The table is the
    subject; the room only has to stop being a void, so it sits two or three
    stops down and lets the lamps do the shaping.

    These are procedural materials rather than flat colours because flat
    colours were the problem. The wall, the panelling and the rails were each a
    single value, and a single value is exactly what a backdrop is -- the room
    read as a painted cyclorama the moment you looked at it for a second. See
    ``plaster_material`` and ``panel_wood_material`` for what replaced them.

    The leather, bottle and maple materials that used to sit here went with the
    bench, the side table and the cabinet. The brass, card and print materials
    went with the box-built wall art, which the cafe picture pack replaced.
    """
    return {
        "wood": panel_wood_material("hall_wood", dark=(0.054, 0.038, 0.027),
                                    light=(0.096, 0.070, 0.049),
                                    floor_z=cfg.MODEL_FLOOR_Z,
                                    roughness=(0.40, 0.56)),
        "wood_warm": panel_wood_material("hall_wood_warm",
                                         dark=(0.078, 0.056, 0.038),
                                         light=(0.124, 0.093, 0.061),
                                         floor_z=cfg.MODEL_FLOOR_Z,
                                         roughness=(0.34, 0.48)),
        "plaster": plaster_material(cfg.MODEL_FLOOR_Z),
    }


def wood_floor_material() -> bpy.types.Material:
    """Dark stained boards under the table, procedurally.

    The room is out of focus and mostly out of frame, so this is not a texture
    study: it exists so the table has a surface to sit on and so the bounced
    light off the floor is not a flat grey.
    """
    mat = bpy.data.materials.new("hall_floor")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.56

    coords = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (1.0, 14.0, 1.0)   # planks run along X
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 3.2
    noise.inputs["Detail"].default_value = 6.0
    noise.inputs["Roughness"].default_value = 0.55
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.30
    ramp.color_ramp.elements[0].color = (0.022, 0.013, 0.008, 1.0)
    ramp.color_ramp.elements[1].position = 0.72
    ramp.color_ramp.elements[1].color = (0.078, 0.044, 0.023, 1.0)

    links.new(coords.outputs["Object"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])

    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


# ------------------------------------------------------------------- scene


def clear_imported_animation() -> None:
    """Drop the GLB's own take.

    The file ships a 3.3 s animation of the cue ball, two object balls and a cue
    stick. Left attached, it keys the very objects this script keyframes, and
    the render would show the imported shot fighting the simulated one.
    """
    for obj in bpy.data.objects:
        if obj.animation_data is not None:
            obj.animation_data_clear()
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)


def flatten_ball(obj: bpy.types.Object) -> None:
    """Detach a ball from the model's hierarchy with its world transform baked in.

    The GLB nests every ball under an empty that carries its authored position,
    and the mesh inside that empty is centred on its own origin. After this the
    object *is* the ball: origin at the centre, radius in metres, no parent -- so
    a physics location can be assigned straight onto ``obj.location``.
    """
    world = obj.matrix_world.copy()
    obj.parent = None
    obj.matrix_world = world
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    obj.select_set(False)


def import_table() -> dict[str, bpy.types.Object]:
    """Bring in the balls and the table, then keep only the balls from this file.

    ``pool_table_animation.glb`` is the only file in the repo whose ball meshes
    match the radius the simulation uses, so the four balls still come from it
    and their transforms are baked exactly as before. Its table is a low-poly
    game asset and is now hidden -- ``table_model`` supplies a real one, fitted
    to the same felt plane and the same cushion noses, so the cached trajectories
    stay valid and the balls still bounce exactly where the cushions are.
    """
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(cfg.MODEL_PATH))
    clear_imported_animation()

    scale = cfg.SCENE_SCALE
    shift = cfg.model_z_shift()
    for obj in bpy.data.objects:
        if obj.parent is None:
            obj.scale = (scale, scale, scale)
            obj.location.z -= shift
    bpy.context.view_layer.update()

    balls: dict[str, bpy.types.Object] = {}
    for slot, mesh_name in BALL_OBJECTS.items():
        obj = bpy.data.objects.get(mesh_name)
        if obj is None:
            raise RuntimeError(f"Ball mesh not found in {cfg.MODEL_PATH.name}: {mesh_name}")
        balls[slot] = obj

    for obj in balls.values():
        flatten_ball(obj)

    # Everything else this file brought in: the rest of the rack, both sticks and
    # the table. Hiding (not deleting) keeps the file's own hierarchy intact for
    # anyone who opens the .blend.
    keep = set(balls.values())
    for obj in bpy.data.objects:
        if obj in keep:
            continue
        obj.hide_viewport = True
        obj.hide_render = True

    table_lib.import_table(cfg.PLAY_HALF_X, cfg.PLAY_HALF_Y)
    print(f"[render] table: felt at z=0, noses at +/-{cfg.PLAY_HALF_X:.4f} x "
          f"+/-{cfg.PLAY_HALF_Y:.4f} m", flush=True)
    return balls


def add_box(name: str, size, location, mat: bpy.types.Material,
            rotation_z: float = 0.0) -> bpy.types.Object:
    """Unit cube scaled to ``size``, origin at its centre."""
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = size
    obj.rotation_euler = (0.0, 0.0, rotation_z)
    obj.data.materials.append(mat)
    return obj


def add_cylinder(name: str, radius: float, depth: float, location, mat: bpy.types.Material,
                 rotation=(0.0, 0.0, 0.0), vertices: int = 20) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth, location=location,
                                        vertices=vertices)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler = rotation
    obj.data.materials.append(mat)
    return obj


# The hall as a box around the table. Only the four walls are built and only as
# tall as the frame can see: from a camera 1.4 m off the floor, pitched down 23
# degrees, the top of the frame never rises above ~0.8 m at the far wall, so a
# ceiling and the upper storey of the walls would be geometry nobody renders.
ROOM_FAR_X = -2.35
ROOM_SIDE_Y = 1.95
ROOM_WALL_TOP = 2.10
ROOM_WAINSCOT_TOP = 0.16          # 0.7 m of panelling above the floor
ROOM_BASEBOARD = 0.13

WALL_THICKNESS = 0.12
RAIL_HEIGHT = 0.045
STILE_WIDTH = 0.05
PANEL_PROUD = 0.016               # how far the stiles stand off the panel field
CAP_HEIGHT = 0.014


def _panelled_wall(*, label: str, along: str, face: float, facing: float,
                   start: float, end: float, floor_z: float,
                   mats: dict[str, bpy.types.Material]) -> None:
    """Panelling for one wall: field, stiles, rails, cap and baseboard.

    ``along`` is the horizontal axis the wall runs down ("y" for the far wall,
    "x" for the side walls); ``face`` is the wall's inner surface on the other
    axis and ``facing`` is +1 or -1 for the way that surface looks. Everything
    is emitted at the same depth offsets either way, so the mouldings line up
    all the way round the room instead of stopping at the corner.

    The old version was a slab with battens nailed to the front of it. A
    batten on a slab is one flat plane with a slightly less flat plane on top;
    what makes joinery read as joinery is *recess* -- the panel field sits
    16 mm behind the stiles and rails that frame it, so every bay has a real
    shadow line on two sides and a lit bevel on the other two. That is the
    whole difference, and it costs four boxes per bay instead of one.
    """
    field_depth = 0.028
    trim_depth = 0.040
    base_depth = 0.050
    cap_depth = 0.052

    def depth_centre(front_offset: float, depth: float) -> float:
        return face + facing * (front_offset - depth / 2.0)

    field_centre = depth_centre(field_depth, field_depth)
    trim_centre = depth_centre(field_depth + PANEL_PROUD, trim_depth)
    base_centre = depth_centre(field_depth + PANEL_PROUD + 0.006, base_depth)
    cap_centre = depth_centre(field_depth + PANEL_PROUD + 0.010, cap_depth)

    base_top = floor_z + ROOM_BASEBOARD
    rail_bottom = ROOM_WAINSCOT_TOP - RAIL_HEIGHT
    field_height = rail_bottom - base_top
    field_z = (base_top + rail_bottom) / 2.0
    span = end - start
    centre = (start + end) / 2.0

    def create(name: str, *, depth: float, length: float, height: float,
               centre_depth: float, centre_along: float, centre_z: float,
               mat: bpy.types.Material) -> None:
        if along == "y":
            add_box(name, (depth, length, height),
                    (centre_depth, centre_along, centre_z), mat)
        else:
            add_box(name, (length, depth, height),
                    (centre_along, centre_depth, centre_z), mat)

    create(f"panel_field_{label}", depth=field_depth, length=span,
           height=field_height, centre_depth=field_centre,
           centre_along=centre, centre_z=field_z, mat=mats["wood"])
    create(f"baseboard_{label}", depth=base_depth, length=span,
           height=ROOM_BASEBOARD, centre_depth=base_centre,
           centre_along=centre, centre_z=floor_z + ROOM_BASEBOARD / 2.0,
           mat=mats["wood"])
    create(f"rail_{label}", depth=trim_depth, length=span,
           height=RAIL_HEIGHT, centre_depth=trim_centre,
           centre_along=centre, centre_z=ROOM_WAINSCOT_TOP - RAIL_HEIGHT / 2.0,
           mat=mats["wood_warm"])
    create(f"cap_{label}", depth=cap_depth, length=span,
           height=CAP_HEIGHT, centre_depth=cap_centre,
           centre_along=centre, centre_z=ROOM_WAINSCOT_TOP + CAP_HEIGHT / 2.0,
           mat=mats["wood_warm"])

    # Bays of about 0.36 m, which is a plausible joinery module and keeps the
    # stiles from reading as a stripe pattern at four metres.
    bays = max(2, round(span / 0.358))
    for index in range(bays + 1):
        create(f"stile_{label}_{index}", depth=trim_depth, length=STILE_WIDTH,
               height=field_height, centre_depth=trim_centre,
               centre_along=start + index * span / bays, centre_z=field_z,
               mat=mats["wood_warm"])


def build_walls(mats: dict[str, bpy.types.Material]) -> None:
    """Four walls, panelled to the rail on every side of the room.

    The panelling is not decoration for its own sake: a flat wall at this
    distance is one value, and a wall that is one value is indistinguishable
    from a black backdrop. What the eye needs is a line to follow round the
    corner and something for the wall-wash to model, which is the rail, the
    cap and the recessed bays.

    The side walls used to get a bare slab: no rail, no baseboard, no stiles.
    In frame that is a brown band that stops at a knife edge and meets the
    floor with no skirting, and it was half the reason the room read as a box
    painted to look like a room. They now get exactly the same treatment as
    the far wall.
    """
    floor_z = cfg.MODEL_FLOOR_Z
    height = ROOM_WALL_TOP - floor_z
    centre_z = floor_z + height / 2.0
    near_x = 1.95                      # the hall closes just behind the camera
    side_len = near_x - ROOM_FAR_X
    side_mid = (near_x + ROOM_FAR_X) / 2.0

    add_box("wall_far", (WALL_THICKNESS, 2 * ROOM_SIDE_Y + 0.24, height),
            (ROOM_FAR_X, 0.0, centre_z), mats["plaster"])
    for sign in (-1.0, 1.0):
        add_box(f"wall_side_{'neg' if sign < 0 else 'pos'}",
                (side_len + 0.12, WALL_THICKNESS, height),
                (side_mid, sign * ROOM_SIDE_Y, centre_z), mats["plaster"])

    _panelled_wall(label="far", along="y",
                   face=ROOM_FAR_X + WALL_THICKNESS / 2.0, facing=1.0,
                   start=-ROOM_SIDE_Y, end=ROOM_SIDE_Y,
                   floor_z=floor_z, mats=mats)
    for sign in (-1.0, 1.0):
        _panelled_wall(label="side_pos" if sign > 0 else "side_neg", along="x",
                       face=sign * (ROOM_SIDE_Y - WALL_THICKNESS / 2.0),
                       facing=-sign, start=ROOM_FAR_X, end=near_x,
                       floor_z=floor_z, mats=mats)


# Where the prints hang: which wall, the position along it (y on the far wall,
# x on a side wall) and the height of the frame's *centre*.
#
# Two things decided this. First, the height. The band of plaster this rig can
# see runs from the cap rail at z = 0.196 m to the top of frame at z = 1.00 m --
# 0.75 m to 1.55 m above the floor -- so 0.60 m is its centre. The old row hung
# its bottoms at 0.225-0.30 m, i.e. sitting on the wainscot cap with 0.25 m of
# bare wall above them, which is what made the row read as "placed" rather than
# "hung"; at the centre of the visible band every frame now has air both below
# and above it, and none of them touches the top of frame.
#
# Second, the count. Three frames 0.6 m apart on one wall is a gallery fence;
# two on the far wall and one on the right wall is a room. Centre heights rather
# than bottoms this time: the three frames are different sizes (one is a
# portrait), and hanging them off a shared bottom edge only worked while they
# were in a row.
#
# The left wall gets nothing on purpose. The camera sits at y = -0.54, so that
# wall is seen almost edge-on: it occupies the first 12% of the frame (u = 0.00
# to 0.12, everything left of the far wall's corner) and both chairs stand in
# front of it. A print hung there would be a 20-pixel sliver behind a chair
# back. The right wall, by contrast, is seen from its far end and the print
# lands at u = 0.72 with 0.18 of frame height -- small, but whole.
FAR_PICTURE_WALL = "far"
RIGHT_PICTURE_WALL = "right"

WALL_ART = (
    # mesh, wall, position along the wall, centre height
    (wall_decor.PICTURE_3, FAR_PICTURE_WALL, -1.05, 0.60),
    (wall_decor.PICTURE_1, FAR_PICTURE_WALL, +0.95, 0.62),
    (wall_decor.PICTURE_2, RIGHT_PICTURE_WALL, -1.45, 0.60),
)


def build_wall_art() -> None:
    """The cafe prints, one or two to a wall.

    The old art was a brass box, a card box and a dark box in front of it. At
    four metres that is a rectangle inside a rectangle: no glass, no print, no
    frame moulding, no shadow gap -- two of them hung on the only wall the
    camera looks at, saying "placeholder" in the loudest possible way. These
    are real frames with 2k maps: glass highlights, a moulded frame, a shadow
    gap, and a print whose value can be read.

    Placement is by projection, not by eye (``_probe_final.py``): each frame's
    box was solved against ``world_to_camera_view`` before it was hung. Centres
    sit at 0.60-0.62 m, i.e. in the middle of the plaster band the camera can
    actually see (the cap rail at 0.174 m to the top of frame at about 1.00 m),
    which leaves 0.25 m of wall under the far pair and 0.22 m over it, and lines
    their top edges up within 12 mm. The two far prints clear the top of frame
    by 7%; the portrait on the right wall, which is the only frame on a wall
    seen at that angle, clears it by 4%.
    """
    pictures = wall_decor.import_pictures()
    far_face = ROOM_FAR_X + WALL_THICKNESS / 2.0
    right_face = ROOM_SIDE_Y - WALL_THICKNESS / 2.0
    for name, wall, along, centre_z in WALL_ART:
        obj = pictures[name]
        # Set back against the plaster by half the frame's own thickness, plus a
        # 2 mm gap so the shadow the frame casts lands on the wall and not on
        # its own moulding.
        back = wall_decor.back_offset(obj)
        if wall == FAR_PICTURE_WALL:
            wall_decor.hang(obj, far_face + back + 0.002, along, centre_z)
        else:
            # The frame's moulding faces model +X; a -90 degree yaw turns that
            # to -Y, which is the way the right wall's plaster looks.
            wall_decor.hang(obj, along, right_face - back - 0.002, centre_z,
                            yaw=-math.pi / 2.0)
    bpy.context.view_layer.update()


# Where the props stand.
#
# The chairs used to sit in the far-left corner, one behind the other against
# the far wall, which read as "two chairs in a corner" rather than as seating
# for the table. They are now along the table's left side, both facing it.
#
# Placing them is a projection problem, and the first answer was wrong. The
# camera sits at y = -0.54 -- beside the table's near-left corner, looking down
# its length -- so the left side of the room is seen almost along the line of
# the corridor between table and wall. Staggering the two chairs in depth
# (y = -1.06 and -1.45, x = -0.35 and -1.15) was supposed to separate them; the
# render says otherwise. The far chair landed at u = [0.03, 0.26] against the
# near chair's [0.06, 0.32]: 88% of its width behind the near chair and only
# 0.05 of its top above it, which reads as one chair with a second backrest
# growing out of it. Depth alone does not separate two chairs in a corridor
# that runs the way the camera looks.
#
# What does is giving the pair a difference in *lateral* position as well, which
# means the near chair comes forward and the far one goes back: the pair used to
# stand at (-0.30, -0.95) and (-1.45, -1.60). Now the far chair spans
# u = [0.03, 0.24] and a third of its back is clear to the left of the near
# chair, on top of 0.067 of frame height above it.
#
# The near chair then came under scrutiny for a different reason: at y = -0.95
# the nearest piece of its seat sat 0.10 m from the table's outer rail -- inside
# the rail's overhang, with the chair reading as if it were tucked under the
# table. No chair in a pool hall stands there: it would be in the way of the
# cue, and at this camera distance the front leg disappeared behind the rail. It
# is now 0.40 m off the rail (measured on the mesh, not on the bounding box),
# which reads as a chair pulled up beside the table rather than pushed into it.
#
# Pulling it back has a cost: the corridor between table and wall is seen almost
# end-on, so a chair that moves back also moves left and stacks behind the far
# one. Two answers were rejected on the render -- keep the far chair where it is
# and the near one at 0.45-0.60 m back merges the pair into one silhouette with
# a double back; move the near chair's *depth* to compensate and it leaves the
# frame at u = -0.09. What works is a 0.40 m standoff plus 12 degrees of extra
# yaw: the near chair is turned toward the table's head end rather than squared
# up to its middle, so its rails cross the far chair's back instead of running
# parallel to it, and the pair still reads as two chairs.
#
# Every number here comes out of `scripts/models/_probe_final.py` for the far
# chair and `_probe_chairs.py` / `_chair_look.py` for the near one; both project
# the real meshes rather than trusting a comment.
PROP_CHAIR_NEAR_XY = (-0.60, -1.28)
PROP_CHAIR_FAR_XY = (-1.45, -1.60)
PROP_BIN_XY = (-2.10, 1.68)

# Both chairs look at the table, which is where a chair in a hall looks. The
# near one is aimed a little past the middle, toward the head end -- see above.
TABLE_CENTRE = (0.0, 0.0)
PROP_CHAIR_NEAR_AIM = (0.50, 0.10)


def build_props() -> None:
    """The two chairs and the bin.

    These replaced four pieces of procedural furniture -- a bench, a side
    table, a chair and a cabinet, each one a box or two on legs. They said
    "room" but they said it in the only way a box can: no upholstery, no
    seat, square edges.

    The chairs are the rustic wooden ones (two copies of one model, so the
    room is furnished rather than decorated) standing on the table's left side
    and turned to face it -- see ``PROP_CHAIR_NEAR_XY`` for why they are
    staggered in depth rather than laid out in a row. The bin is still the
    pack's black barrel, the one hard black shape in a frame of warm browns and
    grey green, and it stays in the far corner: beside the seating it landed at
    u = 0.57, right on the table's far cushion, where a black barrel overlapping
    the rail reads as a hole in the table.
    """
    floor_z = cfg.MODEL_FLOOR_Z
    chairs = prop_lib.import_chairs(2)
    layout = (
        (PROP_CHAIR_NEAR_XY, PROP_CHAIR_NEAR_AIM),
        (PROP_CHAIR_FAR_XY, TABLE_CENTRE),
    )
    for chair, ((x, y), (aim_x, aim_y)) in zip(chairs, layout):
        prop_lib.face_towards(chair, x, y, aim_x, aim_y, floor_z)

    # The bin is a barrel, not a chair: it does not face anything.
    bin_objs = prop_lib.import_props()
    prop_lib.place(bin_objs[prop_lib.TRASHBIN_MESH], PROP_BIN_XY[0], PROP_BIN_XY[1],
                   0.0, floor_z)


def build_room() -> None:
    """Floor, four walls and the furniture that makes it a room.

    The first version of this function put a single 14 m plane under the table
    and called it a hall, on the theory that everything off the table should
    fall away into darkness. What it actually produced was a void: no wall, no
    corner, no scale cue, so the frame read as a table floating in black with an
    empty floor in front of it. A room needs a wall the light can land on.
    """
    floor_z = cfg.MODEL_FLOOR_Z
    mats = room_materials()
    bpy.ops.mesh.primitive_plane_add(size=14.0, location=(0.0, 0.0, floor_z))
    floor = bpy.context.object
    floor.name = "hall_floor"
    floor.data.materials.append(wood_floor_material())
    build_walls(mats)
    build_wall_art()
    build_props()


def add_area_light(name: str, location, target, *, power: float, size: float,
                   color, shadow: bool = True, size_y: float | None = None) -> None:
    bpy.ops.object.light_add(type="AREA", location=location)
    light = bpy.context.object
    light.name = name
    light.data.energy = power
    if size_y is None:
        light.data.shape = "SQUARE"
        light.data.size = size
    else:
        light.data.shape = "RECTANGLE"
        light.data.size = size
        light.data.size_y = size_y
    light.data.color = color
    light.data.use_shadow = shadow
    direction = Vector(target) - Vector(location)
    light.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def setup_world() -> None:
    scene = bpy.context.scene
    world = bpy.data.worlds.new("pool_hall")
    scene.world = world
    world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    background = nodes["Background"]
    # Almost black, with a hint of warm dust so the polished balls have
    # something to reflect other than the lamps.
    # The room has to be readable, not just present. At 1.0 it was a pure black
    # void and the frame had no depth beyond the cloth; 4.4 puts enough on the
    # floor and the far wall to see what the table is standing in, while the
    # hanging lamp still owns the cloth.
    background.inputs["Color"].default_value = (0.020, 0.019, 0.022, 1.0)
    background.inputs["Strength"].default_value = 3.6

    # A gradient across the upper hemisphere stands in for the unlit far end of
    # the hall, so reflections in the balls are not a constant colour.
    gradient = nodes.new("ShaderNodeTexGradient")
    gradient.gradient_type = "SPHERICAL"
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Rotation"].default_value = (math.radians(90.0), 0.0, 0.0)
    coords = nodes.new("ShaderNodeTexCoord")
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.016, 0.017, 0.021, 1.0)
    ramp.color_ramp.elements[1].color = (0.180, 0.170, 0.155, 1.0)
    links.new(coords.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], gradient.inputs["Vector"])
    links.new(gradient.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], background.inputs["Color"])


def build_lights() -> None:
    # A hall lamp: one bar hanging over the table, which is how a pool room is
    # actually lit. Hung low (0.60 m over the cloth) and narrow (1.30 x 0.16) so
    # the balls get a real specular highlight and a short contact shadow, and so
    # the cloth falls off toward the rails instead of being lit flat. The
    # earlier version was a 1 m square a metre up and 18 W -- it lit the cloth
    # evenly and gave the balls neither highlight nor shadow, which is what made
    # the shot read as a diagram.
    #
    # Offset 60 mm toward the rack: the event of the scene happens over the foot
    # spot, and a lamp centred on the table left that end in shadow while the
    # cue ball's empty run-up was the brightest part of the frame.
    add_area_light("bar_key", (-0.06, 0.0, 0.60), (0.0, 0.0, 0.0),
                   power=26.0, size=1.30, size_y=0.16, color=(1.0, 0.94, 0.85))
    # Cold bounce off the far wall, no shadow. Keeps the blue and the red from
    # going to silhouette, gives the polished surfaces something to reflect, and
    # puts a little light on the room so the frame is not a black hole.
    add_area_light("hall_bounce", (0.95, 1.20, 0.50), (0.10, 0.0, 0.05),
                   power=8.0, size=3.00, color=(0.55, 0.66, 1.0), shadow=False)
    # Room lighting: sconces high on the back wall plus one broad, dim wash.
    # The sources sit above the top of the frame -- what you see is only where
    # the light lands. Two pools rather than one even bath, because a single
    # 34 W wash at this distance lit the whole wall to one value and the room
    # read as a showroom: no falloff, nothing to look at, and no place for the
    # eye to rest. The pools also put a bright edge on the wainscot rail, which
    # is what makes the wall read as panelled rather than painted.
    for name, y in (("sconce_left", -1.05), ("sconce_right", 0.65)):
        add_area_light(name, (ROOM_FAR_X + 0.45, y, 1.40), (ROOM_FAR_X, y, -0.30),
                       power=26.0, size=0.55, color=(1.0, 0.84, 0.64))
    add_area_light("wall_wash", (ROOM_FAR_X + 0.55, 0.0, 1.55), (ROOM_FAR_X, 0.0, -0.30),
                   power=12.0, size=2.60, size_y=0.55, color=(1.0, 0.86, 0.68))
    # The near corner, where the bench and the chair are, gets its own small
    # source; the back wall's pools leave it in shadow.
    # Aimed at the wall/floor join rather than at the wall: at 13 W aimed high
    # the panelling under the rail stayed black, and in the survey view that
    # corner read as a wedge of shadow lying across the floor.
    for name, y, target_y in (("side_wash", -1.00, -1.95), ("side_wash_pos", 1.00, 1.95)):
        add_area_light(name, (0.45, y, 1.55), (0.30, target_y, -0.70),
                       power=18.0, size=1.50, color=(1.0, 0.88, 0.72), shadow=False)
    # The far corner, where the bin now stands. The bin is black and glossy:
    # without its own source it is a hole in the frame rather than an object,
    # because a black barrel in a dark corner and an absence of light are the
    # same pixel. Aimed at the bin itself, not at the wall behind it, so the
    # light reads as falling on it.
    add_area_light("bin_pool", (ROOM_FAR_X + 0.75, 1.68, 1.30),
                   (PROP_BIN_XY[0], PROP_BIN_XY[1], -0.30),
                   power=9.0, size=0.70, color=(1.0, 0.88, 0.76))


def render_engine(args: argparse.Namespace) -> None:
    scene = bpy.context.scene
    if args.engine == "cycles":
        scene.render.engine = "CYCLES"
        scene.cycles.samples = int(args.samples)
        scene.cycles.use_denoising = True
        scene.cycles.max_bounces = 8
        scene.cycles.device = "CPU"
        if args.device == "auto" and os.environ.get("PCVE_CYCLES_GPU") == "1":
            prefs = bpy.context.preferences.addons["cycles"].preferences
            try:
                prefs.compute_device_type = "CUDA"
                prefs.get_devices()
                for dev in prefs.devices:
                    dev.use = dev.type == "CUDA"
                scene.cycles.device = "GPU"
            except Exception as exc:  # noqa: BLE001 - any CUDA probe failure falls back
                print(f"[render] CPU fallback: {exc}", flush=True)
        print(f"[render] cycles device={scene.cycles.device}", flush=True)
    else:
        scene.render.engine = eevee_engine()
        set_eevee_property(scene.eevee, 'taa_render_samples', int(args.samples))
        set_eevee_property(scene.eevee, 'use_raytracing', True)
        set_eevee_property(scene.eevee, 'use_gtao', True)
        # 2 m smears every contact shadow into grey haze on a table this size;
        # the balls are 57 mm across, so the occlusion radius has to be small.
        set_eevee_property(scene.eevee, 'gtao_distance', 0.06)
        # Screen-space AO at 60 mm covers the balls and nothing else. It cannot
        # darken an inside corner four metres away, so every wall panel, the
        # wall-to-floor join and the wall-to-wall corner arrived at the same
        # value as the middle of the wall -- which is most of why the room read
        # as painted cardboard. Fast GI is a coarse diffuse bounce over a much
        # longer distance: it costs two rays per pixel and it is what puts a
        # gradient into the corners.
        set_eevee_property(scene.eevee, 'use_fast_gi', True)
        set_eevee_property(scene.eevee, 'fast_gi_method', 'GLOBAL_ILLUMINATION')
        set_eevee_property(scene.eevee, 'fast_gi_distance', 0.85)
        set_eevee_property(scene.eevee, 'fast_gi_ray_count', 2)
        set_eevee_property(scene.eevee, 'fast_gi_step_count', 8)
        set_eevee_property(scene.eevee, 'fast_gi_quality', 0.5)


def build_scene(args: argparse.Namespace, physics: dict):
    # ``import_table`` starts from an empty file, so every scene reference below
    # has to be taken *after* it -- holding one across the reset leaves a dead
    # StructRNA behind.
    balls = import_table()

    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = args.resolution
    scene.render.resolution_percentage = 100
    scene.render.fps = int(physics["fps"])
    scene.render.use_persistent_data = True
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    scene.render.film_transparent = False
    set_color_property(scene.view_settings, 'look', 'AgX - Medium High Contrast')
    scene.view_settings.exposure = 0.30
    render_engine(args)

    setup_world()
    build_room()
    build_lights()

    preset = CAMERA_PRESETS[args.camera_mode]
    bpy.ops.object.camera_add(location=preset["location"])
    camera = bpy.context.object
    camera.name = "camera"
    camera.data.lens = preset["lens_mm"]
    camera.data.sensor_width = 36.0
    camera.data.clip_start = 0.005
    camera.data.clip_end = 60.0
    camera.data.dof.use_dof = True
    camera.data.dof.focus_distance = (
        Vector(preset["target"]) - Vector(preset["location"])
    ).length + preset["focus_offset"]
    camera.data.dof.aperture_fstop = preset["fstop"]
    scene.camera = camera
    target = bpy.data.objects.new("camera_target", None)
    scene.collection.objects.link(target)
    target.location = preset["target"]
    constraint = camera.constraints.new("TRACK_TO")
    constraint.target = target
    constraint.track_axis = "TRACK_NEGATIVE_Z"
    constraint.up_axis = "UP_Y"

    keyframe_balls(
        {slot: obj for slot, obj in balls.items()},
        physics["frames"],
    )

    scene.frame_start = 1
    scene.frame_end = int(physics["frame_end"])
    scene.frame_set(1)
    return balls, camera


def keyframe_balls(balls: dict[str, bpy.types.Object], records: list[dict]) -> None:
    for obj in balls.values():
        obj.rotation_mode = "QUATERNION"
    for record in records:
        frame = int(record["frame_index"])
        for slot, obj in balls.items():
            obj.location = record[f"{slot}_location"]
            quat = record[f"{slot}_quaternion_xyzw"]
            # Blender wants w first, the simulator hands it over last.
            obj.rotation_quaternion = (quat[3], quat[0], quat[1], quat[2])
            obj.keyframe_insert(data_path="location", frame=frame)
            obj.keyframe_insert(data_path="rotation_quaternion", frame=frame)
    for obj in balls.values():
        for fcurve in obj.animation_data.action.fcurves:
            for key in fcurve.keyframe_points:
                key.interpolation = "LINEAR"


# ----------------------------------------------------------------- outputs


def export_ground_truth(out_dir: Path, balls, camera, physics: dict, scenario: dict) -> None:
    scene = bpy.context.scene
    records = {
        "schema_version": 3,
        "scene": "pool_break",
        "fps": int(physics["fps"]),
        "frame_start": 1,
        "frame_end": int(physics["frame_end"]),
        "physics": {key: value for key, value in physics.items() if key != "frames"},
        "objects": {
            slot: {
                "object_name": obj.name,
                "radius_m": float(physics["objects"]["cue_ball"]["radius"]),
            }
            for slot, obj in balls.items()
        },
        "camera": {
            "object_name": camera.name,
            "lens_mm": float(camera.data.lens),
            "sensor_width_mm": float(camera.data.sensor_width),
            "resolution": [int(scene.render.resolution_x), int(scene.render.resolution_y)],
        },
        "scenario": scenario,
        "frames": [],
    }
    by_frame = {int(f["frame_index"]): f for f in physics["frames"]}
    for frame_index in range(1, int(physics["frame_end"]) + 1):
        scene.frame_set(frame_index)
        physical = by_frame[frame_index]
        entry = {"frame_index": frame_index, "time_sec": physical["time_sec"]}
        for slot, obj in balls.items():
            entry[slot] = {
                "matrix_world": [[float(v) for v in row] for row in obj.matrix_world],
                "location": [float(v) for v in physical[f"{slot}_location"]],
                "linear_velocity": physical[f"{slot}_linear_velocity"],
                "angular_velocity": physical[f"{slot}_angular_velocity"],
                "table_gap": physical[f"{slot}_table_gap"],
            }
        for pair in ("cue_apex", "apex_left", "apex_right"):
            entry[f"{pair}_gap"] = physical.get(f"{pair}_gap")
        entry["camera_matrix_world"] = [
            [float(v) for v in row] for row in camera.matrix_world
        ]
        entry["camera_world_to_camera_matrix"] = [
            [float(v) for v in row] for row in camera.matrix_world.inverted()
        ]
        records["frames"].append(entry)
    (out_dir / GROUND_TRUTH_NAME).write_text(
        json.dumps(records, indent=2), encoding="utf-8"
    )


def render_preview(args: argparse.Namespace) -> None:
    scene = bpy.context.scene
    scene.render.image_settings.file_format = "PNG"
    scene.frame_set(max(scene.frame_start, min(int(args.preview_frame), scene.frame_end)))
    scene.render.filepath = str(args.out_dir / "preview.png")
    bpy.ops.render.render(write_still=True)


def render_sampled(args: argparse.Namespace) -> None:
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
    args.out_dir.mkdir(parents=True, exist_ok=True)

    physics = run_physics(args)
    params = physics["physics_parameters"]
    scenario = {
        "schema_version": 3,
        "scene": "pool_break",
        "seed": int(args.seed),
        "environment": "pool_hall_single_table_after_hours",
        "description": "Three balls racked in a triangle on the foot spot are struck by "
                       "the white cue ball; the triangle opens and the balls run to the "
                       "cushions. All four balls are PyBullet rigid bodies.",
        "camera_mode": args.camera_mode,
        "render": {
            "mode": args.mode,
            "fps": int(physics["fps"]),
            "duration_sec": float(physics["duration_sec"]),
            "resolution": [int(args.resolution[0]), int(args.resolution[1])],
            "samples": int(args.samples),
            "engine": "cycles" if args.engine == "cycles" else "eevee_next",
            "device": str(args.device),
        },
        "physics_params": {
            "cue_speed": float(params["cue_speed"]),
            "cue_contact_offset": float(params["cue_contact_offset"]),
            "cue_mass": float(params["cue_mass"]),
            "object_mass": float(params["object_mass"]),
        },
        "quality": physics["quality"],
    }
    (args.out_dir / SCENARIO_METADATA_NAME).write_text(
        json.dumps(scenario, indent=2), encoding="utf-8"
    )

    balls, camera = build_scene(args, physics)
    print(f"[render] scene built in {time.perf_counter() - started:.1f}s "
          f"({len(bpy.data.objects)} objects)", flush=True)
    export_ground_truth(args.out_dir, balls, camera, physics, scenario)

    if args.mode == "preview":
        render_preview(args)
    elif args.mode == "sampled":
        render_sampled(args)
    else:
        bpy.context.scene.render.filepath = str(args.out_dir / f"{OUTPUT_STEM}.mp4")
        bpy.ops.render.render(animation=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.out_dir / f"{OUTPUT_STEM}.blend"))
    print(f"[render] complete: {args.out_dir}", flush=True)


if __name__ == "__main__":
    run_renderer(main, 'pool_break')


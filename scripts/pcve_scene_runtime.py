"""Shared command-line and output contracts for PCVE scene entry points.

Both ``blender -b --python render.py -- ...`` and Python with bpy are supported.
This module has no Blender dependency until a renderer finishes.
"""

import argparse
import hashlib
import json
import math
import os
import random
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_render_args = None


def python_for(role: str) -> Path:
    override = os.environ.get("PCVE_PHYSICS_PYTHON" if role == "physics" else "PCVE_RENDER_PYTHON")
    if override:
        return Path(override).expanduser()
    names = ("sim/python.exe", "sim/bin/python") if role == "physics" else (
        "render/Scripts/python.exe", "render/bin/python")
    for base in (ROOT / ".runtime", ROOT.parent / "PCVE-ElasticBench/.runtime"):
        for name in names:
            if (base / name).is_file():
                return base / name
    if role == "physics":
        # The original Linux setup activates a PyBullet conda environment and
        # invokes Blender separately. Blender's sys.executable is not Python.
        candidates = [ROOT.parent / "miniconda/envs/physics/bin/python"]
        if os.environ.get("CONDA_PREFIX"):
            prefix = Path(os.environ["CONDA_PREFIX"])
            candidates += [prefix / "python.exe", prefix / "bin/python"]
        for name in ("python3", "python"):
            if shutil.which(name):
                candidates.append(Path(shutil.which(name)))
        for candidate in candidates:
            if candidate.is_file() and "blender" not in candidate.name.lower():
                return candidate
    return Path(sys.executable)


def _add(parser, flag, **kwargs):
    if flag not in parser._option_string_actions:
        parser.add_argument(flag, **kwargs)


def implementation_hashes(directory):
    files = list(Path(directory).glob("*.py"))
    files += [ROOT / "scripts" / name for name in ("pcve_scene_pipeline.py", "pcve_edit_dsl.py")]
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in files if path.is_file()}


def case_outputs(folder):
    """Semantic output keys used by the original suite manifests."""
    names = dict(video="video.mp4", ground_truth="ground_truth_transforms.json",
                 scenario_metadata="scenario_metadata.json", scenario_overrides="scenario_overrides.json",
                 physics="physics_transforms.json", scenario_input="scenario_input.json", preview="preview.png")
    return {key: str((Path(folder) / name).resolve()) for key, name in names.items()
            if (Path(folder) / name).is_file()}


def add_build_arguments(parser):
    _add(parser, "--blender", type=Path, help="Blender executable; otherwise use render Python with bpy.")
    _add(parser, "--physics-python", type=Path, default=python_for("physics"))
    _add(parser, "--render-python", type=Path, default=python_for("render"))
    _add(parser, "--engine", choices=("cycles", "eevee"), default="cycles")
    _add(parser, "--device", choices=("auto", "cpu"), default="auto")
    _add(parser, "--preview-frame", type=int)
    _add(parser, "--fps", type=int)
    _add(parser, "--duration-sec", type=float)
    return parser


def render_prefix(args, script: Path) -> list[str]:
    blender = getattr(args, "blender", None) or os.environ.get("BLENDER_BIN")
    render_python = Path(getattr(args, "render_python", python_for("render")))
    if not blender and render_python == Path(sys.executable):
        candidates = [ROOT / "tools/blender-3.6.23-linux-x64/blender"]
        if shutil.which("blender"):
            candidates.append(Path(shutil.which("blender")))
        blender = next((path for path in candidates if path.is_file()), None)
    if blender:
        # Blender otherwise returns success even when the Python script raises.
        return [str(Path(blender).expanduser()), "-b", "--python-exit-code", "1",
                "--python", str(script), "--"]
    return [str(render_python), str(script)]


def append_render_options(command, args):
    for name in ("engine", "device", "preview_frame"):
        flag = "--" + name.replace("_", "-")
        value = getattr(args, name, None)
        if value is not None and flag not in command:
            command += [flag, str(value)]
    return command


def parse_render_args(parser, argv=None):
    global _render_args
    _add(parser, "--seed", type=int, default=0)
    _add(parser, "--device", choices=("auto", "cpu"), default="auto")
    _add(parser, "--preview-frame", type=int)
    _add(parser, "--fps", type=int)
    _add(parser, "--duration-sec", type=float)
    _add(parser, "--physics-python", type=Path, default=python_for("physics"))
    # Renderers without an engine switch currently implement Cycles only.
    _add(parser, "--engine", choices=("cycles",), default="cycles")
    if argv is None:
        argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    _render_args = parser.parse_args(argv)
    # In the original CLI duration-sec is the real-time clip length. A scene's
    # optional demo slow-motion preset must not silently multiply that request.
    if "--duration-sec" in argv and "--slow-motion" not in argv and hasattr(_render_args, "slow_motion"):
        _render_args.slow_motion = 1
    random.seed(_render_args.seed)
    return _render_args


def apply_physics_overrides(args, baseline):
    """Read the original {physics: ...} override format for scalar CLI scenes.

    Bare schedule arrays remain accepted by the older timed-edit escape hatch.
    Explicit scalar command-line values take precedence over the JSON defaults.
    """
    path = getattr(args, "scenario_overrides_json", None)
    if path is None:
        return None
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return Path(path)
    physics = payload.get("physics", payload)
    unknown = set(physics) - {*baseline, "timed_edits"}
    if unknown:
        raise ValueError(f"Unknown physics overrides: {sorted(unknown)}")
    for name, value in physics.items():
        if name != "timed_edits" and getattr(args, name, None) is None:
            setattr(args, name, value)
    if physics.get("timed_edits"):
        target = Path(args.out_dir) / "timed_edits.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(physics["timed_edits"], indent=2), encoding="utf-8")
        return target
    return None


def _matrix(position, q):
    x, y, z, w = q
    return [[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w), position[0]],
            [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w), position[1]],
            [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y), position[2]],
            [0, 0, 0, 1]]


def _optional_metrics(value):
    if isinstance(value, dict):
        return {key: _optional_metrics(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_optional_metrics(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def finalize_render_outputs(out: Path, scene_name: str, args, scene=None):
    """Keep scene-specific files and also publish the original PCVE filenames."""
    out = Path(out).resolve()
    gt_path = out / "ground_truth_transforms.json"
    if gt_path.is_file():
        gt = json.loads(gt_path.read_text(encoding="utf-8"))
        gt.setdefault("scene", scene_name)
        gt.setdefault("schema_version", 1)
        camera = gt.setdefault("camera", {})
        camera.setdefault("resolution", list(args.resolution))
        camera.setdefault("sensor_width_mm", 36.0)
        if scene is not None and scene.camera is not None:
            cam = scene.camera
            camera.update(matrix_world=[list(row) for row in cam.matrix_world],
                          sensor_width_mm=float(cam.data.sensor_width),
                          sensor_fit=cam.data.sensor_fit)
            if cam.data.type == "ORTHO":
                camera.update(projection="orthographic", ortho_scale=float(cam.data.ortho_scale))
            else:
                camera.update(projection="perspective", lens_mm=float(cam.data.lens))
        frames = gt.get("frames", [])
        # toy_car_bottle retains its raw simulation and render_frames as well.
        rendered = gt.get("render_frames", [])
        for index, frame in enumerate(frames):
            frame.setdefault("frame_index", frame.get("frame", index + 1))
            frame.setdefault("time_sec", frame.get("time", index / gt.get("fps", 24)))
            if camera.get("matrix_world") is not None:
                frame.setdefault("camera_matrix_world", camera["matrix_world"])
            if index < len(rendered):
                for name, state in rendered[index].get("objects", {}).items():
                    raw = frame.get("objects", {}).get(name, {})
                    frame[name] = dict(raw, present=True, location=state["position"],
                                       quaternion_xyzw=state["quaternion_xyzw"],
                                       matrix_world=_matrix(state["position"], state["quaternion_xyzw"]))
        gt.setdefault("frame_start", 1)
        gt.setdefault("frame_end", len(frames))
        if scene_name == "toy_car_bottle":
            layout = gt["config"]["layout"]
            gt["objects"] = {
                "car": {"object_name": "toy_car", "dimensions": [layout["car_length"], layout["car_width"], layout["car_height"]]},
                "bottle": {"object_name": "plastic_bottle", "radius": layout["bottle_radius"], "height": layout["bottle_height"]},
            }
        # A short diagnostic clip may not contain an impact. Its unavailable
        # post-contact quality measurements are null; poses must stay finite.
        for container in (gt, gt.get("physics", {})):
            if "quality" in container:
                container["quality"] = _optional_metrics(container["quality"])
        for frame in frames:
            matrices = [item["matrix_world"] for item in frame.values()
                        if isinstance(item, dict) and "matrix_world" in item
                        and not (item.get("present") is False and item["matrix_world"] is None)]
            matrices += [item for key, item in frame.items() if key.endswith("_matrix_world")]
            for matrix in matrices:
                if matrix is None:
                    raise ValueError("A present object must have a ground-truth transform")
                if not all(math.isfinite(value) for row in matrix for value in row):
                    raise ValueError("Non-finite ground-truth transform")
        gt_path.write_text(json.dumps(gt, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    mode = getattr(args, "mode", "preview")
    if mode == "animation":
        stem = "basketball_door" if scene_name == "home_basketball_door" else scene_name
        source = out / (stem + ".mp4")
        target = out / "video.mp4"
        if source.is_file() and not (scene_name == "uneven_ground_ball" and getattr(args, "label", False)):
            shutil.copy2(source, target)
        if not target.is_file():
            raise FileNotFoundError(f"Animation did not produce {target}")
    refresh_alias = scene_name in ("home_basketball_door", "pot_lid_drop") or (
        scene_name == "toy_car_bottle" and getattr(args, "preview_frame", None) is None)
    if mode == "preview" and (refresh_alias or not (out / "preview.png").is_file()):
        number = getattr(args, "preview_frame", None) or 1
        candidates = [out / f"preview_frame_{number:04d}.png", out / "first_frame.png"]
        candidates += sorted(out.glob("preview_frame_*.png"))
        source = next((p for p in candidates if p.is_file()), None)
        if source is None:
            raise FileNotFoundError(f"Preview did not produce an image in {out}")
        shutil.copy2(source, out / "preview.png")


def run_renderer(main, scene_name):
    global _render_args
    _render_args = None
    main()
    if _render_args is not None:
        import bpy
        finalize_render_outputs(_render_args.out_dir, scene_name, _render_args, bpy.context.scene)

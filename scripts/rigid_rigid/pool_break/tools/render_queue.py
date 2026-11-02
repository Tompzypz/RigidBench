"""Batch-simulate and render parameterised pool breaks.

Every sample is deterministic from its seed and varies only the three exposed
physical controls: cue speed, contact offset and cue mass.  Physics runs first
so a sample the solver could not resolve is recorded and skipped instead of
being rendered; both runtimes come from the shared local environment rather than
an ambient system Python.
"""
# PCVE_UNIFIED_ENTRY_BEGIN

from __future__ import annotations

# Resolve the shared scripts directory, then this scene's module folders.
import sys as _clean_sys
from pathlib import Path as _CleanPath
_clean_scene_dir = _CleanPath(__file__).resolve().parents[1]
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





import argparse
import json
import random
import subprocess
import sys
from pathlib import Path

from runtime_support import python_for  # noqa: E402
from scene_config import BASELINE_PHYSICS, BASELINE_RENDER, BALL_RADIUS  # noqa: E402

WORKSPACE_DIR = _PCVE_PROJECT_ROOT
PHYSICS_PYTHON = python_for("physics")
RENDER_PYTHON = python_for("render")
SIM_SCRIPT = Path(__file__).with_name("simulate_pool_break.py")
RENDER_SCRIPT = Path(__file__).with_name("render_pool_break.py")

# Ranges chosen so every sample is still a break: below ~2 m/s the cue ball can
# be stopped by cloth drag before it reaches the rack, and past ~5 m/s the whole
# rack is against the cushions inside two frames. The offset stays inside a
# half-ball hit, which is the widest cut that still strikes the apex ball's face
# rather than its edge.
SPEED_RANGE = (2.4, 5.0)
OFFSET_RANGE = (-0.0143, 0.0143)
MASS_RANGE = (0.11, 0.30)


from pcve_scene_runtime import add_build_arguments, render_prefix, append_render_options

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch render three-ball pool breaks.")
    parser.add_argument("--out-root", type=Path, default=WORKSPACE_DIR / "renders" / "batch_pool_break")
    parser.add_argument("--count", type=int, default=4)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--seed-base", type=int, default=31017)
    parser.add_argument("--mode", choices=("preview", "animation"), default="preview")
    parser.add_argument("--resolution", nargs=2, type=int, default=list(BASELINE_RENDER["resolution"]))
    parser.add_argument("--fps", type=int, default=BASELINE_RENDER["fps"])
    parser.add_argument("--duration-sec", type=float, default=BASELINE_RENDER["duration_sec"])
    parser.add_argument("--samples", type=int, default=BASELINE_RENDER["samples"])
    # Frame 14 is the widest the triangle gets before the balls reach a cushion
    # and start folding back, so a single-frame thumbnail taken there shows the
    # most of what the sampled parameters did. The ``break`` rig is used rather
    # than ``survey``: both keep the whole table in frame, but ``break`` is
    # closer, and on this scene a ball is 15-23 px across, so a thumbnail from
    # the far rig would leave the three target balls as specks.
    parser.add_argument("--preview-frame", type=int, default=14)
    parser.add_argument("--camera-mode", choices=("break", "survey"), default="break")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return add_build_arguments(parser).parse_args()


def sample_params(seed: int) -> dict[str, float]:
    """Spread each control over the band where the response is real and the
    solver stays clean: some taps, some full-blooded breaks, some half-ball
    cuts either side."""
    rng = random.Random(seed)
    return {
        "cue_speed": round(rng.uniform(*SPEED_RANGE), 2),
        "cue_contact_offset": round(rng.uniform(*OFFSET_RANGE), 4),
        "cue_mass": round(rng.uniform(*MASS_RANGE), 3),
    }


def expected_output(mode: str) -> str:
    return "preview.png" if mode == "preview" else "pool_break.mp4"


def simulate_command(args: argparse.Namespace, out_dir: Path, params: dict) -> list[str]:
    return [
        str(args.physics_python), str(SIM_SCRIPT),
        "--out", str(out_dir / "physics_transforms.json"),
        "--fps", str(args.fps),
        "--duration-sec", str(args.duration_sec),
        "--cue-speed", str(params["cue_speed"]),
        "--cue-contact-offset", str(params["cue_contact_offset"]),
        "--cue-mass", str(params["cue_mass"]),
    ]


def render_command(args: argparse.Namespace, out_dir: Path, seed: int) -> list[str]:
    return append_render_options(render_prefix(args, RENDER_SCRIPT) + ['--mode', args.mode, '--out-dir', str(out_dir), '--physics-json', str(out_dir / 'physics_transforms.json'), '--resolution', str(args.resolution[0]), str(args.resolution[1]), '--fps', str(args.fps), '--samples', str(args.samples), '--preview-frame', str(args.preview_frame), '--camera-mode', args.camera_mode, '--seed', str(seed)], args)


def write_manifest(path: Path, manifest: dict) -> None:
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    if args.count <= 0:
        raise ValueError("--count must be positive.")
    for role, interpreter in (("physics", args.physics_python), *([] if args.blender else [("render", args.render_python)])):
        if not interpreter.exists():
            raise FileNotFoundError(f"Shared {role} runtime was not found: {interpreter}")
    if args.dry_run:
        for offset in range(args.count):
            index = args.start_index + offset
            seed = args.seed_base + index
            folder = args.out_root / f"sample_{index:04d}"
            print(subprocess.list2cmdline(simulate_command(args, folder, sample_params(seed))))
            print(subprocess.list2cmdline(render_command(args, folder, seed)))
        return

    args.out_root.mkdir(parents=True, exist_ok=True)
    manifest_path = args.out_root / "batch_manifest.json"
    manifest: dict = {
        "schema_version": 2,
        "scene": "pool_break",
        "mode": args.mode,
        "seed_base": args.seed_base,
        "baseline_physics": dict(BASELINE_PHYSICS),
        "ball_radius": BALL_RADIUS,
        "ranges": {
            "cue_speed": list(SPEED_RANGE),
            "cue_contact_offset": list(OFFSET_RANGE),
            "cue_mass": list(MASS_RANGE),
        },
        "samples": [],
    }
    write_manifest(manifest_path, manifest)

    for offset in range(args.count):
        index = args.start_index + offset
        seed = args.seed_base + index
        params = sample_params(seed)
        out_dir = args.out_root / f"sample_{index:04d}"
        output = out_dir / expected_output(args.mode)
        record = {
            "sample_index": index,
            "seed": seed,
            "params": params,
            "out_dir": str(out_dir.resolve()),
            "expected_output": str(output.resolve()),
            "status": "pending",
        }
        manifest["samples"].append(record)
        write_manifest(manifest_path, manifest)

        if args.skip_existing and output.exists():
            record["status"] = "skipped_existing"
            write_manifest(manifest_path, manifest)
            continue

        out_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(simulate_command(args, out_dir, params), check=True)
        physics = json.loads((out_dir / "physics_transforms.json").read_text(encoding="utf-8"))
        record["quality"] = physics["quality"]
        if not physics["quality"]["all_balls_on_table"]:
            # Not a ball leaving the table -- the walls make that impossible --
            # but the collision model failing to hold one in.
            record["status"] = "unstable"
            write_manifest(manifest_path, manifest)
            print(f"[batch] sample {index}: a ball left the cushions, skipped")
            continue
        subprocess.run(render_command(args, out_dir, seed), check=True)
        record["status"] = "completed"
        write_manifest(manifest_path, manifest)
    print(f"[batch] manifest={manifest_path}")


if __name__ == "__main__":
    main()

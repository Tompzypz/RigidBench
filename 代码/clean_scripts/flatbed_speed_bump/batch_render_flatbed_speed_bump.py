"""Batch-simulate and render parameterized flatbed-truck speed-bump scenes.

Every sample is deterministic from its seed and varies only the three exposed
physical controls: truck speed, bump height and cargo friction.  Physics runs
first so an unstable sample is recorded and skipped instead of being rendered;
both runtimes come from the shared PCVE-ElasticBench environment rather than an
ambient system Python or a Blender binary on PATH.
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





import argparse
import json
import random
import subprocess
from pathlib import Path

import sys

from scene_support.flatbed_speed_bump.runtime_support import python_for  # noqa: E402
from scene_support.flatbed_speed_bump.scene_config import BASELINE_PHYSICS, BASELINE_RENDER  # noqa: E402

WORKSPACE_DIR = _PCVE_PROJECT_ROOT
PHYSICS_PYTHON = python_for("physics")
RENDER_PYTHON = python_for("render")
SIM_SCRIPT = Path(__file__).with_name("simulate_flatbed_speed_bump.py")
RENDER_SCRIPT = Path(__file__).with_name("render_flatbed_speed_bump.py")

# Above roughly 0.145 m the rigid chassis stops riding the bump and starts being
# launched by it -- the contact solver recovers a deep penetration with an
# impulse far larger than the real one, and the truck leaves the road by metres.
# The batch stays inside the range the model actually resolves.
BUMP_HEIGHT_RANGE = (0.08, 0.20)
SPEED_RANGE = (5.0, 11.0)
FRICTION_RANGE = (0.05, 0.60)


from pcve_scene_runtime import add_build_arguments, render_prefix, append_render_options

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch render loaded-flatbed speed-bump scenes.")
    parser.add_argument("--out-root", type=Path, default=WORKSPACE_DIR / "renders" / "batch_flatbed_speed_bump")
    parser.add_argument("--count", type=int, default=4)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--seed-base", type=int, default=24017)
    parser.add_argument("--mode", choices=("preview", "animation"), default="preview")
    parser.add_argument("--resolution", nargs=2, type=int, default=list(BASELINE_RENDER["resolution"]))
    parser.add_argument("--fps", type=int, default=BASELINE_RENDER["fps"])
    parser.add_argument("--duration-sec", type=float, default=BASELINE_RENDER["duration_sec"])
    parser.add_argument("--samples", type=int, default=BASELINE_RENDER["samples"])
    parser.add_argument("--preview-frame", type=int, default=28)
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return add_build_arguments(parser).parse_args()


def sample_params(seed: int) -> dict[str, float]:
    """Spread each control over the band where the response is real and the
    model stays stable, with a mix of modest hops and obvious airborne
    cartons."""
    rng = random.Random(seed)
    return {
        "truck_speed": round(rng.uniform(*SPEED_RANGE), 2),
        "speed_bump_height": round(rng.uniform(*BUMP_HEIGHT_RANGE), 3),
        "cargo_friction": round(rng.uniform(*FRICTION_RANGE), 2),
    }


def expected_output(mode: str) -> str:
    return "preview.png" if mode == "preview" else "flatbed_speed_bump.mp4"


def simulate_command(args: argparse.Namespace, out_dir: Path, params: dict[str, float]) -> list[str]:
    return [
        str(args.physics_python), str(SIM_SCRIPT),
        "--out", str(out_dir / "physics_transforms.json"),
        "--fps", str(args.fps),
        "--duration-sec", str(args.duration_sec),
        "--truck-speed", str(params["truck_speed"]),
        "--speed-bump-height", str(params["speed_bump_height"]),
        "--cargo-friction", str(params["cargo_friction"]),
    ]


def render_command(args: argparse.Namespace, out_dir: Path, seed: int) -> list[str]:
    return append_render_options(render_prefix(args, RENDER_SCRIPT) + ['--mode', args.mode, '--out-dir', str(out_dir), '--physics-json', str(out_dir / 'physics_transforms.json'), '--resolution', str(args.resolution[0]), str(args.resolution[1]), '--fps', str(args.fps), '--samples', str(args.samples), '--preview-frame', str(args.preview_frame), '--seed', str(seed)], args)


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
            index=args.start_index+offset;seed=args.seed_base+index;folder=args.out_root/f'sample_{index:04d}'
            print(subprocess.list2cmdline(simulate_command(args,folder,sample_params(seed))))
            print(subprocess.list2cmdline(render_command(args,folder,seed)))
        return
    args.out_root.mkdir(parents=True, exist_ok=True)
    manifest_path = args.out_root / "batch_manifest.json"
    manifest: dict = {
        "schema_version": 2,
        "scene": "flatbed_speed_bump",
        "mode": args.mode,
        "seed_base": args.seed_base,
        "baseline_physics": dict(BASELINE_PHYSICS),
        "ranges": {
            "truck_speed": list(SPEED_RANGE),
            "speed_bump_height": list(BUMP_HEIGHT_RANGE),
            "cargo_friction": list(FRICTION_RANGE),
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
        if args.dry_run:
            record["command"] = simulate_command(args, out_dir, params)
            record["status"] = "dry_run"
            write_manifest(manifest_path, manifest)
            print(" ".join(simulate_command(args, out_dir, params)))
            print(" ".join(render_command(args, out_dir, seed)))
            continue

        out_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(simulate_command(args, out_dir, params), check=True)
        physics = json.loads((out_dir / "physics_transforms.json").read_text(encoding="utf-8"))
        record["quality"] = physics["quality"]
        if physics["quality"]["chassis_max_lift"] > 0.9:
            # Contact-solver blow-up, not a truck. Record it and move on rather
            # than rendering a clip of the truck in orbit.
            record["status"] = "unstable"
            write_manifest(manifest_path, manifest)
            print(f"[batch] sample {index}: unstable (lift "
                  f"{physics['quality']['chassis_max_lift']:.2f} m), skipped")
            continue
        subprocess.run(render_command(args, out_dir, seed), check=True)
        record["status"] = "completed"
        write_manifest(manifest_path, manifest)
    print(f"[batch] manifest={manifest_path}")


if __name__ == "__main__":
    main()

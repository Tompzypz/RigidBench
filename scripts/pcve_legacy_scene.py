"""Original batch/suite workflow for scenes backed by a scenario.json file."""

import argparse
import hashlib
import importlib
import json
import random
import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from pcve_scene_runtime import ROOT, add_build_arguments, append_render_options, render_prefix, implementation_hashes, case_outputs

import pcve_edit_dsl as dsl


SCRIPTS = {
    "home_basketball_door": ("render_home_basketball_door.py", "simulate_home_basketball_door.py"),
    "pot_lid_drop": ("render_pot_lid_drop.py", "simulate_pot_lid_drop.py"),
    "toy_car_bottle": ("render_toy_car_bottle.py", "simulate_toy_car_bottle.py"),
}


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def parser(scene, batch=False):
    p = argparse.ArgumentParser(description=f"Build {'randomized samples' if batch else 'a source/edit suite'} for {scene}.")
    p.add_argument("--out-root", type=Path, default=ROOT / "renders" / (f"batch_{scene}" if batch else f"pcve_{scene}_suite"))
    p.add_argument("--resolution", nargs=2, type=int, default=[1280, 720])
    p.add_argument("--fps", type=int, default=24)
    p.add_argument("--duration-sec", type=float, default=4.0)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--engine", choices=("cycles",), default="cycles")
    p.add_argument("--mode", choices=("preview", "animation"), default="preview" if batch else "animation")
    p.add_argument("--skip-existing", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verbose-render", action="store_true")
    p.add_argument("--simulate-only", action="store_true")
    if batch:
        p.add_argument("--count", type=int, default=4)
        p.add_argument("--start-index", type=int, default=0)
        p.add_argument("--seed-base", type=int, default=7200)
    else:
        p.add_argument("--cases", nargs="+")
        p.add_argument("--clean-stale-cases", action="store_true")
    return add_build_arguments(p)


def scene_directory(scene):
    candidates = (ROOT / "scripts" / "rigid_rigid" / scene, ROOT / "scripts" / scene)
    for directory in candidates:
        if directory.is_dir():
            return directory
    raise FileNotFoundError(f"No scene directory found for {scene}: {candidates}")


def command_for(scene, folder, args, seed, overrides):
    render, simulate = SCRIPTS[scene]
    directory = scene_directory(scene)
    if args.simulate_only:
        command = [str(args.physics_python), str(directory / simulate), "--out", str(folder / "physics_transforms.json")]
    else:
        command = render_prefix(args, directory / render)
        command += ["--out-dir", str(folder), "--mode", args.mode,
                    "--resolution", *map(str, args.resolution), "--samples", str(args.samples),
                    "--physics-python", str(args.physics_python), "--seed", str(seed)]
        append_render_options(command, args)
    command += ["--fps", str(args.fps), "--duration-sec", str(args.duration_sec)]
    if overrides is not None:
        command += ["--scenario-overrides-json", str(overrides)]
    return command


def run_case(scene, folder, args, seed, override):
    folder = folder.resolve()
    overrides = folder / "scenario_overrides.json" if override else None
    command = command_for(scene, folder, args, seed, overrides)
    if args.dry_run:
        print(subprocess.list2cmdline(command))
        return {"status": "dry_run"}
    implementation = implementation_hashes(scene_directory(scene))
    payload = dict(override=override, implementation=implementation, seed=seed, fps=args.fps,
                   duration=args.duration_sec, mode=args.mode, samples=args.samples,
                   resolution=args.resolution, engine=args.engine, device=args.device,
                   preview_frame=args.preview_frame, simulation_only=args.simulate_only)
    fp = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    status_path = folder / "run_status.json"
    required = ["physics_transforms.json"] if args.simulate_only else [
        "ground_truth_transforms.json", "scenario_metadata.json",
        "video.mp4" if args.mode == "animation" else "preview.png"]
    if args.skip_existing and status_path.is_file():
        previous = json.loads(status_path.read_text(encoding="utf-8"))
        if previous.get("fingerprint") == fp and all((folder / p).is_file() for p in required):
            return dict(previous, status="skipped_existing")
    if overrides is not None:
        write_json(overrides, override)
    folder.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    if args.verbose_render:
        subprocess.run(command, check=True)
    else:
        with (folder / "render.log").open("w", encoding="utf-8") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    for name in required:
        if not (folder / name).is_file():
            raise FileNotFoundError(folder / name)
    status = dict(status="completed", valid=True, fingerprint=fp, simulation_only=args.simulate_only,
                  render_mode=args.mode, elapsed_sec=round(time.perf_counter() - start, 3),
                  outputs=case_outputs(folder))
    write_json(status_path, status)
    return status


def batch_main(scene, argv=None):
    args = parser(scene, batch=True).parse_args(argv)
    args.out_root = args.out_root.resolve()
    if args.count < 1 or args.start_index < 0:
        raise ValueError("Count must be positive and start index nonnegative")
    directory = scene_directory(scene)
    import sys
    for entry in (directory, directory.parents[1], directory / "physics", directory / "appearance"):
        if entry.is_dir() and str(entry) not in sys.path:
            sys.path.insert(0, str(entry))
    vocab = importlib.import_module("edit_vocab").VOCAB
    manifest = dict(schema_version=1, scene=scene, mode=args.mode, count=args.count,
                    start_index=args.start_index, seed_base=args.seed_base, samples=[])
    for offset in range(args.count):
        index = args.start_index + offset
        seed = args.seed_base + index
        rng = random.Random(seed)
        params = dict(vocab.baseline_physics)
        for binding in vocab.sim_bindings.values():
            if isinstance(binding, dsl.SimBinding) and isinstance(params[binding.key], (int, float)):
                params[binding.key] *= rng.uniform(.8, 1.2)
        folder = args.out_root / f"sample_{index:04d}"
        result = run_case(scene, folder, args, seed, {"physics": params})
        manifest["samples"].append(dict(sample_index=index, seed=seed, params=params,
                                         out_dir=str(folder), **result))
        if not args.dry_run:
            write_json(args.out_root / "batch_manifest.json", manifest)


def suite_main(scene, argv=None):
    args = parser(scene).parse_args(argv)
    args.out_root = args.out_root.resolve()
    directory = scene_directory(scene)
    import sys
    for entry in (directory, directory.parents[1], directory / "physics", directory / "appearance"):
        if entry.is_dir() and str(entry) not in sys.path:
            sys.path.insert(0, str(entry))
    module = importlib.import_module("edit_vocab")
    vocab = module.VOCAB
    source_id = f"{scene}_baseline"
    cases = list(module.EDIT_CASES)
    if args.cases:
        unknown = set(args.cases) - {source_id, *[name for name, _ in cases]}
        if unknown:
            raise ValueError(f"Unknown cases: {sorted(unknown)}")
        cases = [(name, instruction) for name, instruction in cases if name in args.cases]
    if args.clean_stale_cases and not args.dry_run:
        keep = {source_id, *[name for name, _ in module.EDIT_CASES]}
        for folder in (args.out_root / "cases").glob("*"):
            if folder.is_dir() and folder.name not in keep:
                if not folder.resolve().is_relative_to(args.out_root):
                    raise ValueError(f"Unsafe case directory: {folder}")
                shutil.rmtree(folder)
    manifest = dict(schema_version=3, suite_name=f"pcve_{scene}_suite", scene=scene,
                    baseline_physics=vocab.baseline_physics, total_frames=round(args.fps * args.duration_sec),
                    fps=args.fps, duration_sec=args.duration_sec, physical_duration_sec=args.duration_sec,
                    playback_duration_sec=args.duration_sec, slow_motion=1, sample_fps=args.fps,
                    samples=args.samples, resolution=args.resolution, source=None, edits=[])
    path = args.out_root / "suite_manifest.json"
    for index, (case_id, instruction) in enumerate([(source_id, None), *cases]):
        folder = args.out_root / "cases" / case_id
        record = dict(case_id=case_id, kind="edit" if instruction else "source",
                      case_dir=str(folder), seed=7300 + index, status="pending")
        override = None
        if instruction:
            edit = dsl.parse(instruction, vocab)
            override = {"physics": dsl.to_scenario_override(edit, vocab)}
            record.update(source_case_id=source_id, edit_dsl=instruction,
                          edit_summary="Change the declared physical parameter and simulate the resulting rigid-body interaction.",
                          applies_from_frame=dsl.starts_at_frame(edit), prompts=dsl.make_prompts(edit, vocab),
                          physics_diff={f"{edit.property_name} ({edit.object_id})": {
                              "from": dsl.baseline_value_for(edit, vocab), "to": dsl.resolved_to_value(edit, vocab)},
                              "timing": dsl.timing_diff(edit, vocab)})
            manifest["edits"].append(record)
        else:
            record["description"] = module.DESCRIPTION
            manifest["source"] = record
        if not args.dry_run:
            prompts = dict(schema_version=2 if instruction else 1, **record)
            if not instruction:
                prompts["prompts"] = module.DESCRIPTION
            write_json(folder / "prompts.json", prompts)
            write_json(path, manifest)
        try:
            record.update(run_case(scene, folder, args, record["seed"], override))
        except Exception:
            record["status"] = "failed"
            write_json(path, manifest)
            raise
        if not args.dry_run:
            write_json(path, manifest)

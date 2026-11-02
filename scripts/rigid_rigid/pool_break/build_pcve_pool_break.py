"""PCVE suite builder: one source clip plus single-variable edits on the three controls.

The source is the baseline break. Every edit below moves exactly one of
``cue_speed`` / ``cue_contact_offset`` / ``cue_mass`` and lets PyBullet decide
the outcome; how far the triangle opens is measured, never scripted.

Run from the project root::

    .\\scripts\\pool_break\\run.ps1 build_pcve_pool_break.py --skip-existing
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





import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pcve_edit_dsl as dsl  # noqa: E402

from validate_pool_break import validate_cache  # noqa: E402
from edit_vocab import EDIT_CASES, VOCAB  # noqa: E402
from runtime_support import python_for  # noqa: E402
from scene_config import BASELINE_PHYSICS, BASELINE_RENDER  # noqa: E402

ROOT = _PCVE_PROJECT_ROOT
SCENE_NAME = "pool_break"
SOURCE_CASE_ID = f"{SCENE_NAME}_baseline"

DESCRIPTION = {
    "vague": {
        "zh": "三颗台球在球台摆成三角形，白球从另一侧撞上顶球，三角被撞开，四颗球散向库边。",
        "en": "Three balls sit racked in a triangle; the white cue ball strikes the apex ball and the triangle comes apart across the table.",
    },
    "quantitative": {
        "zh": "三颗直径 57.15 mm、质量 0.17 kg 的目标球摆成等边三角形，顶球位于球台远端的置球点；白球以 3.6 m/s 沿球台长轴出杆，击球点偏离顶球中心 3 mm，台呢对滚球的阻力为 0.8 m/s²，球在片尾全部停稳。",
        "en": "Three 57.15 mm, 0.17 kg object balls are racked in an equilateral triangle with the apex on the foot spot; the cue ball breaks at 3.6 m/s with the contact point 3 mm off the apex ball's centre, cloth drag 0.8 m/s^2, and every ball comes to rest before the clip ends.",
    },
}


from pcve_scene_runtime import add_build_arguments, render_prefix, append_render_options, implementation_hashes, case_outputs

def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8"
    )


def fingerprint(scenario: dict, args: argparse.Namespace) -> str:
    source = implementation_hashes(Path(__file__).parent)
    payload = dict(
        scenario=scenario, implementation=source, engine=args.engine, device=args.device, preview_frame=args.preview_frame,
        mode=args.mode, samples=args.samples, resolution=list(args.resolution),
        fps=args.fps, duration_sec=args.duration_sec,
        simulate_only=args.simulate_only, camera_mode=args.camera_mode,
    )
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def required_outputs(args: argparse.Namespace, is_edit: bool) -> list[str]:
    names = ["physics_transforms.json", "scenario_input.json", "prompts.json"]
    if is_edit:
        names.append("scenario_overrides.json")
    if not args.simulate_only:
        names += ["ground_truth_transforms.json", "scenario_metadata.json",
                  f"{SCENE_NAME}.blend"]
        names += ["video.mp4"] if args.mode == "animation" else ["preview.png"]
    return names


def run_logged(command, log_path: Path, args: argparse.Namespace) -> None:
    """One external step: quiet log by default, console output with --verbose-render."""
    if args.verbose_render:
        subprocess.run(command, check=True)
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)


def clean_stale(out_root: Path, keep_ids: set[str]) -> None:
    cases_dir = out_root / "cases"
    if not cases_dir.exists():
        return
    for path in sorted(cases_dir.iterdir()):
        if path.is_dir() and path.name not in keep_ids:
            print(f"[suite] remove stale case directory {path}")
            shutil.rmtree(path)


def simulate_command(scenario: dict, args: argparse.Namespace, physics_path: Path) -> list[str]:
    physics = scenario["physics"]
    command = [
        str(args.physics_python),
        str(Path(__file__).with_name("simulate_pool_break.py")),
        "--out", str(physics_path),
        "--fps", str(scenario["render"]["fps"]),
        "--duration-sec", str(scenario["render"]["duration_sec"]),
        "--cue-speed", str(physics["cue_speed"]),
        "--cue-contact-offset", str(physics["cue_contact_offset"]),
        "--cue-mass", str(physics["cue_mass"]),
    ]
    # Rack-side bindings, when an edit touches them.
    for key, flag in (("object_mass", "--object-mass"),
                      ("object_friction", "--object-friction"),
                      ("object_restitution", "--object-restitution")):
        if key in physics:
            command += [flag, str(physics[key])]
    # A timed edit reaches the simulator as a schedule file, not as a
    # parameter: the run up to the edit frame is the source clip, and the
    # params are written into the live simulation at the top of that frame.
    timed = physics.get("timed_edits") or []
    if timed and not args.dry_run:
        schedule = physics_path.parent / "timed_edits.json"
        write_json(schedule, timed)
        command += ["--timed-edits-json", str(schedule)]
    return command


def render_command(scenario: dict, args: argparse.Namespace, physics_path: Path,
                   folder: Path) -> list[str]:
    command = append_render_options(render_prefix(args, Path(__file__).with_name('render_pool_break.py')) + ['--physics-json', str(physics_path), '--out-dir', str(folder), '--fps', str(scenario['render']['fps']), '--samples', str(scenario['render']['samples']), '--resolution', *map(str, scenario['render']['resolution']), '--mode', args.mode, '--camera-mode', args.camera_mode], args)
    return command


def run_case(folder: Path, scenario: dict, args: argparse.Namespace, is_edit: bool) -> dict:
    fp = fingerprint(scenario, args)
    status_file = folder / "run_status.json"
    required = required_outputs(args, is_edit)
    if not args.dry_run and args.skip_existing and status_file.exists():
        status = json.loads(status_file.read_text(encoding="utf-8"))
        if (status.get("fingerprint") == fp and status.get("valid")
                and all((folder / name).exists() for name in required)):
            return dict(status, status="skipped_existing")

    physics_path = folder / "physics_transforms.json"
    sim_command = simulate_command(scenario, args, physics_path)
    render = render_command(scenario, args, physics_path, folder)

    if args.dry_run:
        for command in (([] if args.render_only else [sim_command])
                        + ([] if args.simulate_only else [render])):
            print(subprocess.list2cmdline(command))
        return dict(status="dry_run", valid=False, fingerprint=fp, quality=dict(valid=False))

    folder.mkdir(parents=True, exist_ok=True)
    if not args.render_only:
        write_json(folder / "scenario_input.json", scenario)
        run_logged(sim_command, folder / "simulation.log", args)
    data = json.loads(physics_path.read_text(encoding="utf-8"))
    validate_cache(data, {
        **scenario["physics"],
        "fps": scenario["render"]["fps"],
        "duration_sec": scenario["render"]["duration_sec"],
    })
    if args.render_only:
        write_json(folder / "scenario_input.json", scenario)

    # The source has to show a break, otherwise there is nothing to edit. An
    # edit that suppresses it (a soft break) is a legitimate answer, so only the
    # source is held to this.
    if not is_edit and not data["quality"]["rack_struck"]:
        raise ValueError("Baseline cue ball never reaches the rack; nothing to edit")
    if not is_edit and not data["quality"]["visible"]:
        raise ValueError("Baseline rack never visibly opens; nothing to edit")

    if not args.simulate_only:
        run_logged(render, folder / "render.log", args)

    # The benchmark contract (scripts/build_benchmark.py) expects a per-case
    # ``video.mp4``; the renderer writes its clip under the scene stem.
    if not args.simulate_only and args.mode == "animation":
        rendered = folder / f"{SCENE_NAME}.mp4"
        if rendered.exists():
            shutil.copy2(rendered, folder / "video.mp4")

    status = dict(
        status="completed", valid=True, simulation_only=args.simulate_only,
        render_mode=args.mode, fingerprint=fp, quality=data["quality"],
    )
    write_json(status_file, status)
    return status


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out-root", type=Path, default=ROOT / "renders/pcve_pool_break_suite")
    p.add_argument("--physics-python", type=Path, default=python_for("physics"))
    p.add_argument("--render-python", type=Path, default=python_for("render"))
    p.add_argument("--duration-sec", type=float, default=BASELINE_RENDER["duration_sec"])
    p.add_argument("--fps", type=int, default=BASELINE_RENDER["fps"])
    p.add_argument("--samples", type=int, default=BASELINE_RENDER["samples"])
    p.add_argument("--resolution", type=int, nargs=2, default=list(BASELINE_RENDER["resolution"]))
    p.add_argument("--camera-mode", choices=("break", "survey"),
                   default=BASELINE_RENDER["camera_mode"])
    p.add_argument("--mode", choices=("preview", "animation"), default="animation")
    p.add_argument("--simulate-only", action="store_true")
    p.add_argument("--render-only", action="store_true")
    p.add_argument("--skip-existing", action="store_true")
    p.add_argument("--cases", nargs="+")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the commands each case would run and stop.")
    p.add_argument("--verbose-render", action="store_true",
                   help="Stream simulation and render output to the console.")
    p.add_argument("--clean-stale-cases", action="store_true",
                   help="Delete case directories that are no longer part of this suite.")
    return add_build_arguments(p)


def main() -> None:
    args = parser().parse_args()
    args.out_root = args.out_root.resolve()
    if args.render_only and args.simulate_only:
        raise ValueError("Conflicting execution modes")

    cases = EDIT_CASES
    if args.cases:
        unknown = set(args.cases) - {SOURCE_CASE_ID, *[name for name, _ in cases]}
        if unknown:
            raise ValueError(f"Unknown cases: {unknown}")
        cases = [entry for entry in cases if entry[0] in args.cases]

    total_frames = round(args.fps * args.duration_sec)
    source = {
        "schema_version": 3,
        "scene": SCENE_NAME,
        "physics": dict(BASELINE_PHYSICS),
        "render": {
            "fps": args.fps, "duration_sec": args.duration_sec,
            "resolution": list(args.resolution), "samples": args.samples,
        },
    }

    if args.dry_run:
        for case_id, instruction in [(SOURCE_CASE_ID, None), *cases]:
            scenario = source
            if instruction:
                override = dsl.to_scenario_override(dsl.parse(instruction, VOCAB), VOCAB)
                scenario = {**source, "physics": {**source["physics"], **override}}
            print(f"[suite] {case_id}", flush=True)
            run_case(args.out_root / "cases" / case_id, scenario, args, bool(instruction))
        return

    if args.clean_stale_cases:
        clean_stale(args.out_root, {SOURCE_CASE_ID, *[name for name, _ in EDIT_CASES]})

    manifest = dict(
        schema_version=3,
        suite_name="pcve_pool_break_suite",
        description="One source plus single-variable edits on the cue ball and "
                    "the rack, including one timed edit that lands partway "
                    "through; how far the triangle opens is measured by the "
                    "simulation.",
        baseline_physics=dict(source["physics"]),
        total_frames=total_frames,
        resolution=list(args.resolution),
        fps=args.fps,
        duration_sec=args.duration_sec,
        samples=args.samples,
        physical_duration_sec=args.duration_sec,
        playback_duration_sec=args.duration_sec,
        sample_fps=args.fps,
        slow_motion=1,
        source=None,
        edits=[],
    )
    manifest_path = args.out_root / "suite_manifest.json"

    for i, (case_id, instruction) in enumerate([(SOURCE_CASE_ID, None), *cases]):
        folder = args.out_root / "cases" / case_id
        scenario = source
        record = dict(
            case_id=case_id, kind="edit" if instruction else "source",
            seed=3100 + i, case_dir=str(folder.resolve()), status="pending",
        )
        if instruction:
            edit = dsl.parse(instruction, VOCAB)
            override = {"physics": dsl.to_scenario_override(edit, VOCAB)}
            scenario = {**source, "physics": {**source["physics"], **override["physics"]}}
            record.update(
                source_case_id=SOURCE_CASE_ID,
                edit_dsl=instruction,
                edit_summary=(dsl.summarize_set_edit(edit, VOCAB) + " How far the balls spread is measured by the simulation."),
                applies_from_frame=dsl.starts_at_frame(edit),
                physics_diff={
                    f"{edit.property_name} ({edit.object_id})": {
                        "from": dsl.baseline_value_for(edit, VOCAB),
                        "to": dsl.resolved_to_value(edit, VOCAB),
                    },
                    "timing": dsl.timing_diff(edit, VOCAB),
                },
                prompts=dsl.make_prompts(edit, VOCAB),
                scenario_overrides_json=str((folder / "scenario_overrides.json").resolve()),
                prompts_json=str((folder / "prompts.json").resolve()),
            )
            write_json(folder / "scenario_overrides.json", override)
            write_json(folder / "prompts.json", {
                "schema_version": 2,
                **{k: record[k] for k in ("case_id", "source_case_id", "edit_dsl",
                                          "edit_summary", "applies_from_frame",
                                          "physics_diff", "prompts")},
            })
            manifest["edits"].append(record)
        else:
            record["description"] = DESCRIPTION
            manifest["source"] = record
            write_json(folder / "prompts.json", {
                "schema_version": 1, "case_id": case_id, "kind": "source",
                "prompts": DESCRIPTION,
            })

        write_json(manifest_path, manifest)
        print(f"[suite] {case_id}", flush=True)
        start = time.perf_counter()
        try:
            record.update(run_case(folder, scenario, args, bool(instruction)))
            record["outputs"] = case_outputs(folder)
        except Exception:
            record["status"] = "failed"
            write_json(manifest_path, manifest)
            raise
        record["elapsed_sec"] = round(time.perf_counter() - start, 3)
        write_json(manifest_path, manifest)

    print(f"[suite] manifest: {manifest_path}")


if __name__ == "__main__":
    main()

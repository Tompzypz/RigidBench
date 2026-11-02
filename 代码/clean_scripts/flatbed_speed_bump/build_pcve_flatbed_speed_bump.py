"""PCVE suite builder: one source clip plus single-variable edits on the three controls.

The source is the baseline flatbed run. Every edit below changes exactly one of
``truck_speed`` / ``speed_bump_height`` / ``cargo_friction`` and lets PyBullet
decide the outcome; nothing about how high the cartons fly is scripted.

Run from the project root::

    .\\scripts\\flatbed_speed_bump\\run.ps1 build_pcve_flatbed_speed_bump.py --skip-existing
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
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pcve_edit_dsl as dsl  # noqa: E402

from edit_vocab import DESCRIPTION, EDIT_CASES, VOCAB  # noqa: E402
from scene_support.flatbed_speed_bump.runtime_support import python_for  # noqa: E402
from scene_support.flatbed_speed_bump.cache_contract import validate_cache
from scene_support.flatbed_speed_bump.scene_config import BASELINE_PHYSICS, BASELINE_RENDER  # noqa: E402

ROOT = _PCVE_PROJECT_ROOT
SCENE_NAME = "flatbed_speed_bump"
SOURCE_CASE_ID = f"{SCENE_NAME}_baseline"


from pcve_scene_runtime import add_build_arguments, render_prefix, append_render_options, implementation_hashes, case_outputs

def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8"
    )


def timed_schedule(scenario: dict, folder: Path, *, write: bool) -> Path | None:
    """Materialise the scenario's timed-edit schedule for the simulator.

    A whole-clip edit is entirely expressible as command-line parameters; a
    timed one is not, because the same parameter has to hold two different
    values inside one run. The simulator takes the schedule as a file and fires
    each entry at the top of its frame, so the frames before the event are the
    source run and the frames after it are solved from the state it reached.
    """
    schedule = scenario["physics"].get("timed_edits")
    if not schedule:
        return None
    path = folder / "timed_edits.json"
    if write:
        write_json(path, schedule)
    return path


def fingerprint(scenario: dict, args: argparse.Namespace) -> str:
    source = implementation_hashes(Path(__file__).parent)
    payload = dict(
        scenario=scenario, implementation=source, engine=args.engine, device=args.device, preview_frame=args.preview_frame,
        mode=args.mode, samples=args.samples, resolution=list(args.resolution),
        fps=args.fps, duration_sec=args.duration_sec, simulate_only=args.simulate_only, camera_mode=args.camera_mode,
    )
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def required_outputs(args: argparse.Namespace, is_edit: bool) -> list[str]:
    names = ["physics_transforms.json", "scenario_input.json", "prompts.json"]
    if is_edit:names.append("scenario_overrides.json")
    if not args.simulate_only:
        names += ["ground_truth_transforms.json","scenario_metadata.json",f"{SCENE_NAME}.blend"]
        names += ["video.mp4"] if args.mode=="animation" else ["preview.png"]
    return names


def run_logged(command, log_path: Path, args: argparse.Namespace) -> None:
    """Run one external step the way the older scenes do: quiet log by default,
    console output with --verbose-render."""
    if args.verbose_render:
        subprocess.run(command, check=True)
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)


def clean_stale(out_root: Path, keep_ids: set[str]) -> None:
    """Drop case directories that are no longer part of this suite."""
    cases_dir = out_root / "cases"
    if not cases_dir.exists():
        return
    for path in sorted(cases_dir.iterdir()):
        if path.is_dir() and path.name not in keep_ids:
            print(f"[suite] remove stale case directory {path}")
            shutil.rmtree(path)


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
    schedule_path = timed_schedule(scenario, folder, write=not args.dry_run)
    sim_command = [
        str(args.physics_python),
        str(Path(__file__).with_name("simulate_flatbed_speed_bump.py")),
        "--out", str(physics_path),
        "--fps", str(scenario["render"]["fps"]),
        "--duration-sec", str(scenario["render"]["duration_sec"]),
        "--truck-speed", str(scenario["physics"]["truck_speed"]),
        "--speed-bump-height", str(scenario["physics"]["speed_bump_height"]),
        "--cargo-friction", str(scenario["physics"]["cargo_friction"]),
    ]
    if schedule_path is not None:
        sim_command += ["--timed-edits-json", str(schedule_path)]
    script = Path(__file__).with_name("render_flatbed_speed_bump.py")
    render_command = append_render_options(render_prefix(args, script), args)
    render_command += [
        "--physics-json", str(physics_path),
        "--out-dir", str(folder),
        "--fps", str(scenario["render"]["fps"]),
        "--samples", str(scenario["render"]["samples"]),
        "--resolution", *map(str, scenario["render"]["resolution"]),
        "--mode", args.mode,
        "--camera-mode", args.camera_mode,
    ]
    if args.dry_run:
        for command in (([] if args.render_only else [sim_command])
                        + ([] if args.simulate_only else [render_command])):
            print(subprocess.list2cmdline(command))
        return dict(status="dry_run", valid=False, fingerprint=fp, quality=dict(valid=False))

    folder.mkdir(parents=True,exist_ok=True)
    if not args.render_only:
        write_json(folder / "scenario_input.json", scenario)
        run_logged(sim_command, folder / "simulation.log", args)
    data = json.loads(physics_path.read_text(encoding="utf-8"))
    validate_cache(data,{**scenario['physics'],'fps':scenario['render']['fps'],'duration_sec':scenario['render']['duration_sec']})
    if args.render_only:write_json(folder / "scenario_input.json", scenario)
    # The source has to show the effect, otherwise there is nothing to edit. An
    # edit that suppresses it (slow truck, shallow bump) is a legitimate answer,
    # so only the source is held to it.
    if not is_edit and not data["quality"]["visible"]:
        raise ValueError(
            "Baseline cargo never visibly leaves the deck; nothing to edit"
        )
    if not is_edit and not data["quality"]["any_cargo_airborne"]:
        raise ValueError("Baseline cargo never separates from the deck")

    if not args.simulate_only:
        run_logged(render_command, folder / "render.log", args)

    # The renderer writes its clip under the scene stem; the benchmark contract
    # (scripts/build_benchmark.py) expects a per-case ``video.mp4``.
    if not args.simulate_only and args.mode == "animation":
        rendered = folder / f"{SCENE_NAME}.mp4"
        if rendered.exists():
            shutil.copy2(rendered, folder / "video.mp4")

    status = dict(
        status="completed", valid=True, simulation_only=args.simulate_only,
        render_mode=args.mode, fingerprint=fp, quality=data["quality"],
        # Events the simulator fired while it was running, with the parameter
        # and the body state on both sides of each write.
        timed_events=data.get("timed_events", []),
    )
    write_json(status_file, status)
    return status


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out-root", type=Path, default=ROOT / "renders/pcve_flatbed_speed_bump_suite")
    p.add_argument("--physics-python", type=Path, default=python_for("physics"))
    p.add_argument("--render-python", type=Path, default=python_for("render"))
    p.add_argument("--duration-sec", type=float, default=BASELINE_RENDER["duration_sec"])
    p.add_argument("--fps", type=int, default=BASELINE_RENDER["fps"])
    p.add_argument("--samples", type=int, default=BASELINE_RENDER["samples"])
    p.add_argument("--resolution", type=int, nargs=2, default=list(BASELINE_RENDER["resolution"]))
    # Every rig the renderer knows, not just the two that were wired up first:
    # ``clip4s`` is the default, so leaving it out of the choices rejected the
    # value the builder itself ships.
    p.add_argument("--camera-mode", choices=("static", "survey", "wide", "clip4s"),
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
        "scene": "flatbed_speed_bump",
        "physics": dict(BASELINE_PHYSICS),
        "render": {
            "fps": args.fps, "duration_sec": args.duration_sec,
            "resolution": list(args.resolution), "samples": args.samples,
        },
    }

    if args.dry_run:
        for case_id,instruction in [(SOURCE_CASE_ID,None),*cases]:
            scenario=source
            if instruction:
                override=dsl.to_scenario_override(dsl.parse(instruction,VOCAB),VOCAB)
                scenario={**source,'physics':{**source['physics'],**override}}
            print(f'[suite] {case_id}',flush=True)
            run_case(args.out_root/'cases'/case_id,scenario,args,bool(instruction))
        return
    if args.clean_stale_cases:clean_stale(args.out_root,{SOURCE_CASE_ID,*[name for name,_ in EDIT_CASES]})
    manifest = dict(
        schema_version=3,
        suite_name="pcve_flatbed_speed_bump_suite",
        description="One source plus single-variable truck-speed, bump-height and "
                    "cargo-friction edits; outcomes are measured by the simulation.",
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
            seed=3300 + i, case_dir=str(folder.resolve()), status="pending",
        )
        if instruction:
            edit = dsl.parse(instruction, VOCAB)
            override = {"physics": dsl.to_scenario_override(edit, VOCAB)}
            scenario = {**source, "physics": {**source["physics"], **override["physics"]}}
            timed = dsl.is_timed(edit)
            record.update(
                source_case_id=SOURCE_CASE_ID,
                edit_dsl=instruction,
                edit_summary=(
                    f"Only the declared physical parameter changes, from frame "
                    f"{dsl.starts_at_frame(edit)} on: the clip runs on the source "
                    "physics up to that frame and the parameter is written into the "
                    "running simulation there. How far the cartons are thrown is "
                    "then measured by the simulation."
                    if timed else
                    "Only the declared physical parameter changes, from the first "
                    "frame on; how far the cartons are thrown is measured by the "
                    "simulation."
                ),
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

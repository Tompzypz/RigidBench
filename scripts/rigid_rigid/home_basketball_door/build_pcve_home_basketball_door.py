"""Build the home_basketball_door PCVE suite.

One source video (a basketball is thrown across a bedroom at a half-open door,
the leaf is knocked most of the way shut before its hinge friction stops it,
the ball rebounds and rolls across the floor until it settles) plus N edited
variants. Each edit is a single edit-DSL string; the prompts, the scenario
override and the physics diff are all derived from that one string, so a case
cannot describe one video and render another.

    .runtime/render/Scripts/python.exe scripts/home_basketball_door/build_pcve_home_basketball_door.py

Only the four knobs in edit_vocab.py can be edited. What each one does to the
clip was measured, not assumed -- every edit_summary below quotes the numbers
that simulate_home_basketball_door.py produced for that case.

Why the baseline stops short of the jamb matters. The hinge friction is a
Coulomb torque, so the swing is ``I w^2 / (2 tau)`` radians with ``w`` falling
as ``1/I``: travel scales as ``1/I`` against leaf mass and as ``1/tau`` against
hinge friction. That only reads on screen while the leaf has room to stop
before the jamb. With a slack hinge the leaf reaches 0 deg every time and every
edit looks the same -- measured, at tau = 0.45 N m every cases travelled
43-45 deg and the variants were indistinguishable.

At the shipped tau = 1.0 N m the source run still reaches the jamb (45 deg down
to 0.07 deg of travel 44.93 deg), so the knobs are read off what they leave
behind: lightening the ball to 0.186 kg cuts the travel to 9.92 deg and the
leaf hangs 35.08 deg open, making the leaf ten times heavier leaves 10.64 deg of
travel and 34.36 deg of opening, and quadrupling the hinge friction stops it at
19.84 deg. All five numbers come from simulate_home_basketball_door.py, not from
the ideal scaling law.
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
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
import pcve_edit_dsl as dsl  # noqa: E402
import edit_vocab  # noqa: E402
from edit_vocab import DESCRIPTION, EDIT_CASES, EditCase, SOURCE_CASE_ID  # noqa: E402

WORKSPACE_DIR = _PCVE_PROJECT_ROOT
RENDER_SCRIPT = HERE / 'render_home_basketball_door.py'
DEFAULT_RENDER_PYTHON = WORKSPACE_DIR / '.runtime' / 'render' / 'Scripts' / 'python.exe'
VIDEO_NAME = 'basketball_door.mp4'

VOCAB = edit_vocab.VOCAB
BASELINE_PHYSICS = edit_vocab.BASELINE_PHYSICS


# --------------------------------------------------------------- edit cases
#
# The five cases themselves live in edit_vocab.py, next to the vocabulary they
# are written in: one place to read what can be edited and what each edit is.


from pcve_scene_runtime import add_build_arguments, render_prefix, append_render_options


# --------------------------------------------------------------------- CLI


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build the home_basketball_door PCVE suite.')
    parser.add_argument(
        '--out-root', type=Path,
        default=WORKSPACE_DIR / 'renders' / 'pcve_home_basketball_door_suite',
    )
    parser.add_argument('--render-python', type=Path, default=DEFAULT_RENDER_PYTHON)
    parser.add_argument('--resolution', nargs=2, type=int, default=(1280, 720))
    parser.add_argument('--fps', type=int, default=24)
    parser.add_argument('--duration-sec', type=float, default=4.0)
    parser.add_argument('--samples', type=int, default=96)
    parser.add_argument('--device', choices=('auto', 'cpu'), default='auto')
    parser.add_argument('--only', default=None, help='comma-separated case ids')
    parser.add_argument('--mode', choices=('preview', 'animation'), default='animation',
                        help="preview renders the tail frame only (cheap visual check)")
    parser.add_argument('--skip-existing', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--verbose-render', action='store_true')
    parser.add_argument('--clean-stale-cases', action='store_true')
    return add_build_arguments(parser).parse_args()


# --------------------------------------------------------------- render glue


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')


def render_command(
    args: argparse.Namespace,
    *,
    case_dir: Path,
    overrides_path: Path | None,
) -> list[str]:
    python = Path(args.render_python).expanduser()
    if not python.exists():
        python = Path(shutil.which('python') or 'python')
    cmd = append_render_options(render_prefix(args, RENDER_SCRIPT) + ['--mode', str(args.mode), '--out-dir', str(case_dir), '--resolution', str(int(args.resolution[0])), str(int(args.resolution[1])), '--fps', str(int(args.fps)), '--duration-sec', str(float(args.duration_sec)), '--samples', str(int(args.samples)), '--device', str(args.device)], args)
    cmd += ['--physics-python', str(args.physics_python)]
    if overrides_path is not None:
        cmd += ['--scenario-overrides-json', str(overrides_path)]
    return cmd


def standardize_render_outputs(case_dir: Path, *, has_overrides: bool, mode: str = 'animation') -> dict[str, str]:
    if mode == 'preview':
        # --mode preview writes one still per requested frame and no clip, so the
        # contract is the still(s) plus the trajectory the renderer recorded.
        stills = sorted(case_dir.glob('preview_frame_*.png'))
        if not stills:
            raise FileNotFoundError(f'No preview still found in {case_dir}')
        outputs: dict[str, Path] = {
            'preview': stills[-1],
            'ground_truth': case_dir / 'ground_truth_transforms.json',
            'scenario_metadata': case_dir / 'scenario_metadata.json',
        }
        if has_overrides:
            outputs['scenario_overrides'] = case_dir / 'scenario_overrides.json'
        for key, path in outputs.items():
            if not path.exists():
                raise FileNotFoundError(f'Missing rendered {key}: {path}')
        resolved = {key: str(path.resolve()) for key, path in outputs.items()}
        resolved['preview_frames'] = [str(p.resolve()) for p in stills]
        return resolved

    video_source = case_dir / VIDEO_NAME
    if not video_source.exists():
        candidates = sorted(case_dir.glob('*.mp4'))
        if not candidates:
            raise FileNotFoundError(f'No mp4 found in {case_dir}')
        video_source = candidates[0]
    video_target = case_dir / 'video.mp4'
    if video_source.resolve() != video_target.resolve():
        shutil.copy2(video_source, video_target)

    outputs: dict[str, Path] = {
        'video': video_target,
        'ground_truth': case_dir / 'ground_truth_transforms.json',
        'scenario_metadata': case_dir / 'scenario_metadata.json',
    }
    if has_overrides:
        outputs['scenario_overrides'] = case_dir / 'scenario_overrides.json'
    for key, path in outputs.items():
        if not path.exists():
            raise FileNotFoundError(f'Missing rendered {key}: {path}')
    return {key: str(path.resolve()) for key, path in outputs.items()}


def render_case(
    args: argparse.Namespace,
    *,
    case_dir: Path,
    overrides_path: Path | None,
) -> None:
    cmd = render_command(args, case_dir=case_dir, overrides_path=overrides_path)
    if args.dry_run:
        print(' '.join(cmd))
        return
    case_dir.mkdir(parents=True, exist_ok=True)
    if args.verbose_render:
        subprocess.run(cmd, check=True)
        return
    result = subprocess.run(cmd, text=True, encoding='utf-8', errors='replace', capture_output=True)
    if result.returncode != 0:
        tail = '\n'.join((result.stderr or '').splitlines()[-40:])
        print(f'[suite] render failed; stderr tail:\n{tail}')
        raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)


def build_edit_record(case: EditCase) -> dict[str, Any]:
    parsed = dsl.parse(case.dsl, VOCAB)
    physics = dsl.to_scenario_override(parsed, VOCAB)
    if isinstance(parsed, dsl.SetEdit):
        diff = {
            f'{parsed.property_name} ({parsed.object_id})': {
                'from': dsl.baseline_value_for(parsed, VOCAB),
                'to': parsed.to_value,
            }
        }
    else:
        diff = {parsed.object_id: {'from': 'present', 'to': 'removed'}}
    diff['timing'] = dsl.timing_diff(parsed, VOCAB)
    return {
        'edit_dsl': case.dsl,
        'edit_summary': case.edit_summary,
        'applies_from_frame': dsl.starts_at_frame(parsed),
        'prompts': dsl.make_prompts(parsed, VOCAB),
        'physics_diff': diff,
        'physics_override': physics,
    }


def write_prompt_file(case_dir: Path, case: EditCase, edit_info: dict[str, Any]) -> Path:
    path = case_dir / 'prompts.json'
    write_json(
        path,
        {
            'schema_version': 2,
            'case_id': case.case_id,
            'source_case_id': SOURCE_CASE_ID,
            'edit_dsl': edit_info['edit_dsl'],
            'edit_summary': edit_info['edit_summary'],
            'applies_from_frame': edit_info['applies_from_frame'],
            'physics_diff': edit_info['physics_diff'],
            'prompts': edit_info['prompts'],
        },
    )
    return path


def clean_stale(out_root: Path, keep_ids: set[str]) -> None:
    cases_dir = out_root / 'cases'
    if not cases_dir.exists():
        return
    for path in sorted(cases_dir.iterdir()):
        if not path.is_dir() or path.name in keep_ids:
            continue
        print(f'[suite] remove stale case directory {path}')
        shutil.rmtree(path)


def read_run_evidence(case_dir: Path) -> dict[str, Any]:
    """What the simulator reported for this case, straight from its cache.

    ``timed_events`` is the record a mid-clip case needs to be checkable: the
    frame the parameter was written on, its value on both sides of the write and
    the motion state it left alone. ``quality`` is the measured outcome the
    edit summary quotes.
    """
    path = case_dir / 'physics_transforms.json'
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding='utf-8'))
    return {'quality': payload.get('quality'), 'timed_events': payload.get('timed_events', [])}



# -------------------------------------------------------------------- main


def main() -> None:
    args = parse_args()
    # The vocabulary bounds "AT FRAME n" against the clip length; if the two
    # ever disagree every timed prompt quietly means something else.
    rendered_frames = int(round(float(args.duration_sec) * int(args.fps)))
    from dataclasses import replace
    global VOCAB
    VOCAB = replace(VOCAB, total_frames=rendered_frames)
    wanted = {part.strip() for part in (args.only or '').split(',') if part.strip()}
    unknown = wanted - {SOURCE_CASE_ID, *(case.case_id for case in EDIT_CASES)}
    if unknown:
        raise ValueError(f'Unknown cases: {sorted(unknown)}')
    cases = [c for c in EDIT_CASES if not wanted or c.case_id in wanted]
    if args.dry_run:
        render_case(args, case_dir=args.out_root/'cases'/SOURCE_CASE_ID, overrides_path=None)
        for case in cases:
            build_edit_record(case)
            render_case(args, case_dir=args.out_root/'cases'/case.case_id,
                        overrides_path=args.out_root/'cases'/case.case_id/'scenario_overrides.json')
        return
    args.out_root.mkdir(parents=True, exist_ok=True)
    want_source = True

    keep_ids = {SOURCE_CASE_ID, *(c.case_id for c in EDIT_CASES)}
    if args.clean_stale_cases and not args.dry_run:
        clean_stale(args.out_root, keep_ids)

    manifest_path = args.out_root / 'suite_manifest.json'
    manifest: dict[str, Any] = {
        'schema_version': 3,
        'suite_name': 'pcve_home_basketball_door_suite',
        'description': (
            'One source bedroom video (a basketball is thrown at a half-open '
            'door, knocks it most of the way shut and rebounds across the '
            'floor) plus N edited variants. The ball and the door leaf are the '
            'only movers; each edit is one line of edit-DSL against them.'
        ),
        'baseline_physics': BASELINE_PHYSICS,
        'total_frames': rendered_frames,
        'resolution': [int(args.resolution[0]), int(args.resolution[1])],
        'fps': int(args.fps),
        'duration_sec': float(args.duration_sec),
        'samples': int(args.samples),
        'render_mode': args.mode,
        'source': None,
        'edits': [],
    }
    write_json(manifest_path, manifest)

    # ------------------------------------------------------------- source
    source_dir = args.out_root / 'cases' / SOURCE_CASE_ID
    source_record: dict[str, Any] = {
        'case_id': SOURCE_CASE_ID,
        'kind': 'source',
        'description': DESCRIPTION,
        'case_dir': str(source_dir.resolve()),
        'status': 'pending',
    }
    manifest['source'] = source_record
    write_json(manifest_path, manifest)

    if want_source:
        expected_source_video = (source_dir / 'video.mp4' if args.mode == 'animation'
                                 else source_dir / 'preview_frame_*.png')
        if args.skip_existing and (expected_source_video.exists() if args.mode == 'animation'
                                   else any(source_dir.glob('preview_frame_*.png'))):
            source_record['status'] = 'skipped_existing'
            source_record['outputs'] = standardize_render_outputs(source_dir, has_overrides=False, mode=args.mode)
            source_record.update(read_run_evidence(source_dir))
        elif args.dry_run:
            render_case(args, case_dir=source_dir, overrides_path=None)
            source_record['status'] = 'dry_run'
        else:
            t0 = time.perf_counter()
            print(f'[suite] render source {SOURCE_CASE_ID}')
            render_case(args, case_dir=source_dir, overrides_path=None)
            source_record['outputs'] = standardize_render_outputs(source_dir, has_overrides=False, mode=args.mode)
            # The source carries the numbers the edits are read against, so it
            # records the same quality block and (empty) event log as they do.
            source_record.update(read_run_evidence(source_dir))
            source_record['elapsed_sec'] = round(time.perf_counter() - t0, 3)
            source_record['status'] = 'completed'
        write_json(manifest_path, manifest)

    # -------------------------------------------------------------- edits
    for case in cases:
        case_dir = args.out_root / 'cases' / case.case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        edit_info = build_edit_record(case)

        overrides_path = case_dir / 'scenario_overrides.json'
        write_json(overrides_path, {'physics': edit_info['physics_override']})
        prompts_path = write_prompt_file(case_dir, case, edit_info)

        record: dict[str, Any] = {
            'case_id': case.case_id,
            'kind': 'edit',
            'source_case_id': SOURCE_CASE_ID,
            'seed': case.seed,
            'case_dir': str(case_dir.resolve()),
            'scenario_overrides_json': str(overrides_path.resolve()),
            'prompts_json': str(prompts_path.resolve()),
            'edit_dsl': edit_info['edit_dsl'],
            'edit_summary': edit_info['edit_summary'],
            'applies_from_frame': edit_info['applies_from_frame'],
            'physics_diff': edit_info['physics_diff'],
            'prompts': edit_info['prompts'],
            'status': 'pending',
        }
        manifest['edits'].append(record)
        write_json(manifest_path, manifest)

        expected_video = case_dir / 'video.mp4'
        if args.skip_existing and (expected_video.exists() if args.mode == 'animation'
                                   else any(case_dir.glob('preview_frame_*.png'))):
            record['status'] = 'skipped_existing'
            record['outputs'] = standardize_render_outputs(case_dir, has_overrides=True, mode=args.mode)
            # A skipped case still has its run on disk, so the quality block and
            # the timed-event log come from that run rather than disappearing.
            record.update(read_run_evidence(case_dir))
            write_json(manifest_path, manifest)
            print(f'[suite] skip existing {case.case_id}')
            continue

        if args.dry_run:
            render_case(args, case_dir=case_dir, overrides_path=overrides_path)
            record['status'] = 'dry_run'
            write_json(manifest_path, manifest)
            continue

        t0 = time.perf_counter()
        print(f'[suite] render edit {case.case_id}')
        try:
            render_case(args, case_dir=case_dir, overrides_path=overrides_path)
        except subprocess.CalledProcessError:
            record['status'] = 'failed'
            record['elapsed_sec'] = round(time.perf_counter() - t0, 3)
            write_json(manifest_path, manifest)
            raise
        record['outputs'] = standardize_render_outputs(case_dir, has_overrides=True, mode=args.mode)
        record['elapsed_sec'] = round(time.perf_counter() - t0, 3)
        record['status'] = 'completed'
        record.update(read_run_evidence(case_dir))
        write_json(manifest_path, manifest)
        print(f'[suite] completed {case.case_id} in {record["elapsed_sec"]:.1f}s')

    print(f'[suite] manifest={manifest_path.resolve()}')


if __name__ == '__main__':
    main()

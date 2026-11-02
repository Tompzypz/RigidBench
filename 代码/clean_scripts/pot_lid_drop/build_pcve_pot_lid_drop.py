"""Build the pot_lid_drop PCVE suite.

One source video (the lid slips off the pot, falls 1.1 m edge-first, clangs onto
the floor, tips over its rim and flops flat) plus N edited variants. Each edit
is declared as a single edit-DSL string; the prompts, the scenario override and
the physics diff are all derived from that one string, so a case cannot describe
one video and render another.

    .runtime/render/Scripts/python.exe scripts/pot_lid_drop/build_pcve_pot_lid_drop.py

Only the three knobs in edit_vocab.py can be edited. What each one does to the
clip was measured, not assumed -- see the edit_summary text, which quotes the
numbers simulate_pot_lid_drop.py produces for that case.
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
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
import pcve_edit_dsl as dsl  # noqa: E402
import edit_vocab  # noqa: E402

WORKSPACE_DIR = _PCVE_PROJECT_ROOT
RENDER_SCRIPT = HERE / 'render_pot_lid_drop.py'
DEFAULT_RENDER_PYTHON = WORKSPACE_DIR / '.runtime' / 'render' / 'Scripts' / 'python.exe'

VOCAB = edit_vocab.VOCAB
BASELINE_PHYSICS = edit_vocab.BASELINE_PHYSICS


# --------------------------------------------------------------- edit cases


from pcve_scene_runtime import add_build_arguments, render_prefix, append_render_options

@dataclass(frozen=True)
class EditCase:
    case_id: str
    source_case_id: str
    seed: int
    dsl: str
    edit_summary: str


SOURCE_CASE_ID = 'pot_lid_drop_baseline'


# The vocabulary owns the edit list (see edit_vocab.EDIT_CASES); this table
# attaches the seed and the one-line summary each case record carries.
_VOCAB_CASES = dict(edit_vocab.EDIT_CASES)


def _case(case_id: str, seed: int, summary: str) -> EditCase:
    return EditCase(case_id=case_id, source_case_id=SOURCE_CASE_ID, seed=seed,
                    dsl=_VOCAB_CASES[case_id], edit_summary=summary)


# Per-case metrics are measured during rendering.
EDIT_CASES: tuple[EditCase, ...] = (
    _case(
        'edit_light_gravity', 6101,
        'Thirty percent gravity: the lid falls in slow motion, the impact is far '
        'softer and the whole ground phase stretches out.',
    ),
    _case(
        'edit_add_bowl_at_landing', 6102,
        'A stationary bowl is added exactly where the baseline lid comes to rest, '
        'so the falling lid collides with the bowl wall instead of sliding freely '
        'across the floor.',
    ),
    _case(
        'edit_slick_rim', 6103,
        'A tenth of the rolling friction lets the rim roll carry the lid much further before it stops.',
    ),
    _case(
        'edit_bouncy_lid', 6104,
        'Higher restitution increases the rebound and changes the subsequent rocking motion.',
    ),
    _case(
        'edit_zero_gravity_timed', 6105,
        'The clip runs on the baseline physics through the free fall, the touchdown and '
        'the start of the rebound (frames 1-13); at frame 14 the schedule switches gravity '
        'off inside the running simulation, so the lid coasts up off the floor and never '
        'comes back down.',
    ),
)


# --------------------------------------------------------------------- CLI


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build the pot_lid_drop PCVE suite.')
    parser.add_argument('--out-root', type=Path, default=WORKSPACE_DIR / 'renders' / 'pcve_pot_lid_drop_suite')
    parser.add_argument('--render-python', type=Path, default=DEFAULT_RENDER_PYTHON)
    parser.add_argument('--resolution', nargs=2, type=int, default=(1280, 720))
    parser.add_argument('--fps', type=int, default=24)
    parser.add_argument('--duration-sec', type=float, default=4.0)
    parser.add_argument('--samples', type=int, default=96)
    parser.add_argument('--device', choices=('auto', 'cpu'), default='auto')
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
    seed: int,
    *,
    case_dir: Path,
    overrides_path: Path | None,
) -> list[str]:
    python = Path(args.render_python).expanduser()
    if not python.exists():
        python = Path(shutil.which('python') or 'python')
    cmd = append_render_options(render_prefix(args, RENDER_SCRIPT) + ['--mode', 'animation', '--out-dir', str(case_dir), '--resolution', str(int(args.resolution[0])), str(int(args.resolution[1])), '--fps', str(int(args.fps)), '--duration-sec', str(float(args.duration_sec)), '--samples', str(int(args.samples)), '--device', str(args.device)], args)
    if overrides_path is not None:
        cmd += ['--scenario-overrides-json', str(overrides_path)]
    return cmd


def standardize_render_outputs(case_dir: Path, *, has_overrides: bool) -> dict[str, str]:
    video_source = case_dir / 'pot_lid_drop.mp4'
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
    seed: int,
    overrides_path: Path | None,
) -> None:
    case_dir.mkdir(parents=True, exist_ok=True)
    cmd = render_command(args, seed, case_dir=case_dir, overrides_path=overrides_path)
    if args.dry_run:
        print(' '.join(cmd))
        return
    if args.verbose_render:
        subprocess.run(cmd, check=True)
        return
    result = subprocess.run(cmd, text=True, capture_output=True)
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
            'source_case_id': case.source_case_id,
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


# -------------------------------------------------------------------- main


def main() -> None:
    args = parse_args()
    # The vocabulary bounds "AT FRAME n" against the clip length; if the two
    # ever disagree every timed prompt quietly means something else.
    rendered_frames = int(round(float(args.duration_sec) * int(args.fps)))
    from dataclasses import replace
    global VOCAB
    VOCAB = replace(VOCAB, total_frames=rendered_frames)
    args.out_root.mkdir(parents=True, exist_ok=True)

    keep_ids = {SOURCE_CASE_ID, *(c.case_id for c in EDIT_CASES)}
    if args.clean_stale_cases and not args.dry_run:
        clean_stale(args.out_root, keep_ids)

    manifest_path = args.out_root / 'suite_manifest.json'
    manifest: dict[str, Any] = {
        'schema_version': 3,
        'suite_name': 'pcve_pot_lid_drop_suite',
        'description': (
            'One source kitchen video (a pot lid slips off the pot, falls '
            'edge-first, tips over its rim and flops flat) plus N edited '
            'variants. The lid is the only moving object; each edit is one '
            'line of edit-DSL against it.'
        ),
        'baseline_physics': BASELINE_PHYSICS,
        'total_frames': rendered_frames,
        'resolution': [int(args.resolution[0]), int(args.resolution[1])],
        'fps': int(args.fps),
        'duration_sec': float(args.duration_sec),
        'samples': int(args.samples),
        'source': None,
        'edits': [],
    }
    write_json(manifest_path, manifest)

    # ------------------------------------------------------------- source
    source_dir = args.out_root / 'cases' / SOURCE_CASE_ID
    source_record: dict[str, Any] = {
        'case_id': SOURCE_CASE_ID,
        'kind': 'source',
        'description': {
            'vague': {
                'en': (
                    'A pot lid slips off the pot on the kitchen counter, falls '
                    'edge-first to the tiled floor, tips over and flops flat.'
                ),
                'zh': '锅盖从厨房台面上的锅上滑落,侧着掉到瓷砖地面上,翻了一下摊平停住。',
            },
            'quantitative': {
                'en': (
                    'The lid is released 1.1 m above the floor at a 65 deg tilt '
                    'with no spin, first touches down on frame 13, rebounds '
                    '0.066 m, tips over its rim, curls 0.37 m across the floor '
                    'and is at rest from frame 32 of 96.'
                ),
                'zh': (
                    '锅盖以 65° 倾角、无自转地从离地 1.1 m 处释放,第 13 帧侧棱触地,'
                    '弹起 0.066 m,随后绕触棱翻倒,在地面上划出一道 0.37 m 的弧线,'
                    '约在第 32 帧(共 96 帧)摊平静止。'
                ),
            },
        },
        'case_dir': str(source_dir.resolve()),
        'status': 'pending',
    }
    manifest['source'] = source_record
    write_json(manifest_path, manifest)

    expected_source_video = source_dir / 'video.mp4'
    if args.skip_existing and expected_source_video.exists():
        source_record['status'] = 'skipped_existing'
        source_record['outputs'] = standardize_render_outputs(source_dir, has_overrides=False)
    elif args.dry_run:
        render_case(args, case_dir=source_dir, seed=6001, overrides_path=None)
        source_record['status'] = 'dry_run'
    else:
        t0 = time.perf_counter()
        print(f'[suite] render source {SOURCE_CASE_ID}')
        render_case(args, case_dir=source_dir, seed=6001, overrides_path=None)
        source_record['outputs'] = standardize_render_outputs(source_dir, has_overrides=False)
        source_record['elapsed_sec'] = round(time.perf_counter() - t0, 3)
        source_record['status'] = 'completed'
    write_json(manifest_path, manifest)

    # -------------------------------------------------------------- edits
    for case in EDIT_CASES:
        case_dir = args.out_root / 'cases' / case.case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        edit_info = build_edit_record(case)

        overrides_path = case_dir / 'scenario_overrides.json'
        write_json(overrides_path, {'physics': edit_info['physics_override']})
        prompts_path = write_prompt_file(case_dir, case, edit_info)

        record: dict[str, Any] = {
            'case_id': case.case_id,
            'kind': 'edit',
            'source_case_id': case.source_case_id,
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
        if args.skip_existing and expected_video.exists():
            record['status'] = 'skipped_existing'
            record['outputs'] = standardize_render_outputs(case_dir, has_overrides=True)
            write_json(manifest_path, manifest)
            print(f'[suite] skip existing {case.case_id}')
            continue

        if args.dry_run:
            render_case(args, case_dir=case_dir, seed=case.seed, overrides_path=overrides_path)
            record['status'] = 'dry_run'
            write_json(manifest_path, manifest)
            continue

        t0 = time.perf_counter()
        print(f'[suite] render edit {case.case_id}')
        try:
            render_case(args, case_dir=case_dir, seed=case.seed, overrides_path=overrides_path)
        except subprocess.CalledProcessError:
            record['status'] = 'failed'
            record['elapsed_sec'] = round(time.perf_counter() - t0, 3)
            write_json(manifest_path, manifest)
            raise
        record['outputs'] = standardize_render_outputs(case_dir, has_overrides=True)
        record['elapsed_sec'] = round(time.perf_counter() - t0, 3)
        record['status'] = 'completed'
        write_json(manifest_path, manifest)
        print(f'[suite] completed {case.case_id} in {record["elapsed_sec"]:.1f}s')

    print(f'[suite] manifest={manifest_path.resolve()}')


if __name__ == '__main__':
    main()

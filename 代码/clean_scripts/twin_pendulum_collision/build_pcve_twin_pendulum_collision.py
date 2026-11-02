"""One source and five preset edits declared in edit_vocab, like the other scenes."""

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
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from twin_pendulum_collision.runtime_support import ROOT, python_for, render_prefix, append_render_options, implementation_hashes
from twin_pendulum_collision.scene_config import defaults, merge, validate
from twin_pendulum_collision.cache_contract import validate_cache
from edit_vocab import VOCAB, EDIT_CASES
import pcve_edit_dsl as dsl

SOURCE_CASE_ID = 'twin_pendulum_collision_baseline'
SOURCE_SEED = 10401


def build_edit_record(case_id, dsl_text, edit_summary, sample_fps=24, total_frames=None):
    vocab = replace(VOCAB, total_frames=total_frames or round(6 * sample_fps))
    parsed = dsl.parse(dsl_text, vocab)
    if dsl.is_timed(parsed) and not isinstance(parsed, dsl.DeleteEdit):
        raise ValueError('Only timed DELETE receiver is implemented; parameter edits start at frame 1')
    # A slow-motion render samples the same physical event more densely.
    # Resolve the preset's baseline frame to the new clock, rather than deleting
    # before the collision when sample_fps is greater than 24.
    if dsl.is_timed(parsed):
        parsed = replace(parsed, at_frame=round((parsed.at_frame - 1) * sample_fps / 24) + 1)
    if isinstance(parsed, dsl.SetEdit):
        diff = {f'{parsed.property_name} ({parsed.object_id})': {
            'from': dsl.baseline_value_for(parsed, vocab), 'to': dsl.resolved_to_value(parsed, vocab)}}
    else:
        diff = {parsed.object_id: {'from': 'present', 'to': 'removed'}}
    diff['timing'] = dsl.timing_diff(parsed, vocab)
    return dict(edit_dsl=dsl.serialize(parsed), edit_summary=edit_summary,
                applies_from_frame=dsl.starts_at_frame(parsed), physics_diff=diff,
                prompts=dsl.make_prompts(parsed, vocab),
                physics_override=dsl.to_scenario_override(parsed, vocab))


def write_prompt_file(folder, case_id, info):
    path = folder / 'prompts.json'
    write_json(path, dict(schema_version=2, case_id=case_id,
                         source_case_id=SOURCE_CASE_ID,
                         **{key: info[key] for key in ('edit_dsl', 'edit_summary', 'applies_from_frame',
                                                     'physics_diff', 'prompts')}))
    return path


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')


def run_logged(command, path, args):
    if args.verbose_render:
        subprocess.run(command, check=True)
    else:
        with path.open('w', encoding='utf-8') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)


def run_case(folder, scenario, args):
    validate(scenario)
    folder.mkdir(parents=True, exist_ok=True)
    signature = dict(scenario=scenario, code=implementation_hashes(Path(__file__).parent),
                     engine=args.engine, device=args.device, preview_frame=args.preview_frame,
                     mode=args.mode, simulate_only=args.simulate_only)
    fp = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
    status_path = folder / 'run_status.json'
    required = ['physics_transforms.json', 'simulation_metrics.json']
    if not args.simulate_only:
        required += ['preview.png', 'ground_truth_transforms.json', 'scenario_metadata.json',
                     'render_validation.json', 'twin_pendulum_collision.blend']
        if args.mode == 'animation':
            required += ['video.mp4', 'twin_pendulum_collision.mp4']
    if args.skip_existing and status_path.exists():
        status = json.loads(status_path.read_text(encoding='utf-8'))
        if status.get('fingerprint') == fp and status.get('valid') and all((folder / name).exists() for name in required):
            return dict(status, status='skipped_existing')
    sim = [str(args.physics_python), str(Path(__file__).with_name('simulate_twin_pendulum_collision.py')),
           '--out', str(folder / 'physics_transforms.json'), '--scenario-json', str(folder / 'scenario_input.json')]
    render = render_prefix(args, Path(__file__).with_name('render_twin_pendulum_collision.py'))
    render += ['--physics-json', str(folder / 'physics_transforms.json'), '--out-dir', str(folder),
               '--engine', args.engine, '--device', args.device, '--samples', str(args.samples),
               '--resolution', *map(str, args.resolution), '--mode', args.mode]
    render = append_render_options(render, args)
    if args.dry_run:
        for command in ([] if args.render_only else [sim]) + ([] if args.simulate_only else [render]):
            print(subprocess.list2cmdline(command))
        return dict(status='dry_run', valid=False, quality=dict(valid=False))
    write_json(folder / 'scenario_input.json', scenario)
    if not args.render_only:
        run_logged(sim, folder / 'simulation.log', args)
    data = json.loads((folder / 'physics_transforms.json').read_text(encoding='utf-8'))
    validate_cache(data)
    if data['scenario']['physics'] != scenario['physics'] or any(
            data['scenario']['render'][key] != scenario['render'][key] for key in ('fps', 'slow_motion', 'duration_sec')):
        raise ValueError('Cached physics/timing differs; resimulate before --render-only')
    if not args.simulate_only:
        run_logged(render, folder / 'render.log', args)
    if not all((folder / name).exists() for name in required):
        raise RuntimeError('Incomplete case outputs')
    status = dict(status='completed', valid=True, fingerprint=fp, simulation_only=args.simulate_only,
                  render_mode=args.mode, quality=data['quality'])
    write_json(status_path, status)
    return status


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out-root', type=Path, default=ROOT / 'renders/pcve_twin_pendulum_collision_suite')
    p.add_argument('--physics-python', type=Path, default=python_for('physics'))
    p.add_argument('--render-python', type=Path, default=python_for('render'))
    p.add_argument('--blender', type=Path)
    p.add_argument('--duration-sec', type=float, default=6.)
    p.add_argument('--fps', type=int, default=24)
    p.add_argument('--slow-motion', type=int, choices=(1, 2, 4, 8), default=1)
    p.add_argument('--samples', type=int, default=32)
    p.add_argument('--resolution', type=int, nargs=2, default=[960, 540])
    p.add_argument('--engine', choices=('cycles', 'eevee'), default='cycles')
    p.add_argument('--device', choices=('auto', 'cpu'), default='auto')
    p.add_argument('--mode', choices=('preview', 'animation'), default='animation')
    p.add_argument('--preview-frame', type=int)
    p.add_argument('--simulate-only', action='store_true')
    p.add_argument('--render-only', action='store_true')
    p.add_argument('--skip-existing', action='store_true')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--verbose-render', action='store_true')
    p.add_argument('--cases', nargs='+')
    return p


def outputs(folder):
    names = dict(video='video.mp4', physics='physics_transforms.json', ground_truth='ground_truth_transforms.json',
                 scenario_input='scenario_input.json', scenario_metadata='scenario_metadata.json', preview='preview.png',
                 scenario_overrides='scenario_overrides.json', prompts='prompts.json')
    return {key: str((folder / name).resolve()) for key, name in names.items() if (folder / name).exists()}


def main():
    args = parser().parse_args()
    args.out_root = args.out_root.resolve()
    if args.render_only and args.simulate_only:
        raise ValueError('Conflicting execution modes')
    cases = EDIT_CASES
    if args.cases:
        if set(args.cases) - {SOURCE_CASE_ID, *[case_id for case_id, *_ in cases]}:
            raise ValueError('Unknown case')
        cases = [case for case in cases if case[0] in args.cases]
    source = defaults()
    source['seed'] = SOURCE_SEED
    source['render'].update(fps=args.fps, duration_sec=args.duration_sec, slow_motion=args.slow_motion,
                            resolution=args.resolution, samples=args.samples)
    description = {
        'vague': {'zh': '实验台上两个留有小间距的单摆，释放左摆，碰撞带动右摆，随后往返衰减。',
                  'en': 'Release the left of two slightly separated pendulums and observe collision-driven transfer and decay.'},
        'quantitative': {'zh': '左摆质量 0.26 kg，初始摆幅 32 度，右摆固定 0.26 kg；两摆线性阻力系数 0.006 kg/s，静止球面间距 0.022 m。',
                         'en': 'Driver mass 0.26 kg, release angle 32 degrees, fixed receiver mass 0.26 kg, linear drag 0.006 kg/s on both, rest surface gap 0.022 m.'}}
    manifest = dict(schema_version=3, suite_name='pcve_twin_pendulum_collision_suite',
                    description='One source and exactly five single-edit cases; the timed receiver removal happens inside the simulation and all outcomes are measured by continued simulation.',
                    baseline_physics=source['physics'], total_frames=round(args.fps * args.duration_sec * args.slow_motion),
                    resolution=args.resolution, fps=args.fps, duration_sec=args.duration_sec * args.slow_motion,
                    samples=args.samples, physical_duration_sec=args.duration_sec,
                    playback_duration_sec=args.duration_sec * args.slow_motion,
                    sample_fps=args.fps * args.slow_motion, slow_motion=args.slow_motion, source=None, edits=[])
    path = args.out_root / 'suite_manifest.json'
    for case in [None, *cases]:
        case_id = case[0] if case else SOURCE_CASE_ID
        folder = args.out_root / 'cases' / case_id
        scenario = source
        record = dict(case_id=case_id, kind='edit' if case else 'source', seed=SOURCE_SEED,
                      case_dir=str(folder), status='pending')
        if case:
            info = build_edit_record(*case, args.fps * args.slow_motion, manifest['total_frames'])
            override = {'physics': info['physics_override']}
            scenario = merge(source, override)
            validate(scenario)
            record.update(source_case_id=SOURCE_CASE_ID,
                          **{key: info[key] for key in ('edit_dsl', 'edit_summary', 'applies_from_frame',
                                                     'physics_diff', 'prompts')},
                          scenario_overrides_json=str(folder / 'scenario_overrides.json'), prompts_json=str(folder / 'prompts.json'))
            write_json(folder / 'scenario_overrides.json', override)
            write_prompt_file(folder, case_id, info)
            manifest['edits'].append(record)
        else:
            record['description'] = description
            manifest['source'] = record
            write_json(folder / 'prompts.json', dict(schema_version=1, case_id=case_id, kind='source', prompts=description))
        write_json(path, manifest)
        print(f'[suite] {case_id}', flush=True)
        start = time.perf_counter()
        try:
            record.update(run_case(folder, scenario, args))
            if not args.dry_run and not case and args.duration_sec >= 1 and not record['quality']['transmission_observed']:
                raise RuntimeError('Baseline did not transfer motion to receiver')
            record['outputs'] = outputs(folder)
        except Exception:
            record['status'] = 'failed'
            write_json(path, manifest)
            raise
        record['elapsed_sec'] = round(time.perf_counter() - start, 3)
        write_json(path, manifest)


if __name__ == '__main__':
    main()

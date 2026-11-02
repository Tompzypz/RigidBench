"""A toy-car source clip and five single-variable physical edits."""

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
from pathlib import Path
import subprocess
import sys
import time

from toy_car_collision.runtime_support import ROOT, python_for, render_prefix, append_render_options, implementation_hashes
from toy_car_collision.scene_config import defaults, merge, validate
from toy_car_collision.cache_contract import validate_cache
from edit_vocab import VOCAB, EDIT_CASES
import pcve_edit_dsl as dsl

SOURCE_CASE_ID = 'toy_car_collision_baseline'


_baseline_trace = None


def baseline_receiver_speed_at_frame(frame):
    """The receiver car's live speed on the baseline trace at `frame`.

    The timed speed edit is written as TIMES n, which the simulator applies
    to the velocity the body actually carries at that frame. The honest
    before/after pair for physics_diff is therefore read off the baseline
    run rather than off the vocabulary's baseline parameter table.
    """
    global _baseline_trace
    if _baseline_trace is None:
        from simulate_toy_car_collision import simulate as _simulate
        _baseline_trace = _simulate(defaults())
    lin = _baseline_trace['frames'][frame - 1]['car_b']['linear_velocity']
    return (lin[0] ** 2 + lin[1] ** 2 + lin[2] ** 2) ** .5


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
                     mode=args.mode, keyframes=args.keyframes, simulate_only=args.simulate_only)
    fp = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
    status_path = folder / 'run_status.json'
    required = ['physics_transforms.json', 'simulation_metrics.json']
    if not args.simulate_only:
        required += ['preview.png', 'ground_truth_transforms.json', 'scenario_metadata.json',
                     'render_validation.json', 'toy_car_collision.blend']
        if args.mode == 'keyframes':
            required += ['keyframes.json']
        if args.mode == 'animation':
            required += ['video.mp4', 'toy_car_collision.mp4']
    if args.skip_existing and status_path.exists():
        status = json.loads(status_path.read_text(encoding='utf-8'))
        if status.get('fingerprint') == fp and status.get('valid') and all((folder / name).exists() for name in required):
            return dict(status, status='skipped_existing')
    sim = [str(args.physics_python), str(Path(__file__).with_name('simulate_toy_car_collision.py')),
           '--out', str(folder / 'physics_transforms.json'), '--scenario-json', str(folder / 'scenario_input.json')]
    render = render_prefix(args, Path(__file__).with_name('render_toy_car_collision.py'))
    render += ['--physics-json', str(folder / 'physics_transforms.json'), '--out-dir', str(folder),
               '--engine', args.engine, '--device', args.device, '--samples', str(args.samples),
               '--resolution', *map(str, args.resolution), '--mode', args.mode]
    render = append_render_options(render, args)
    if args.keyframes:
        render += ['--keyframes', *map(str,args.keyframes)]
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
    p.add_argument('--out-root', type=Path, default=ROOT / 'renders/pcve_toy_car_collision_suite')
    p.add_argument('--physics-python', type=Path, default=python_for('physics'))
    p.add_argument('--render-python', type=Path, default=python_for('render'))
    p.add_argument('--blender', type=Path)
    p.add_argument('--duration-sec', type=float, default=4.)
    p.add_argument('--fps', type=int, default=24)
    p.add_argument('--slow-motion', type=int, choices=(1, 2, 4, 8), default=1)
    p.add_argument('--samples', type=int, default=32)
    p.add_argument('--resolution', type=int, nargs=2, default=[960, 540])
    p.add_argument('--engine', choices=('cycles', 'eevee'), default='cycles')
    p.add_argument('--device', choices=('auto', 'cpu'), default='auto')
    p.add_argument('--mode', choices=('preview', 'keyframes', 'animation'), default='keyframes')
    p.add_argument('--preview-frame', type=int)
    p.add_argument('--keyframes', nargs='+',type=int)
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
        if set(args.cases) - {SOURCE_CASE_ID, *[name for name, _ in cases]}:
            raise ValueError('Unknown case')
        cases = [(name, instruction) for name, instruction in cases if name in args.cases]
    source = defaults()
    source['render'].update(fps=args.fps, duration_sec=args.duration_sec, slow_motion=args.slow_motion,
                            resolution=args.resolution, samples=args.samples)
    description = {
        'vague': {'zh': '房间内，主动车撞击静止的传动车，碰撞后两车减速。',
                  'en': 'In a furnished room, a moving toy car rear-ends a stationary toy car and transfers motion.'},
        'quantitative': {'zh': f"主动车质量 {source['physics']['driver_mass']:g} kg，传动车质量 {source['physics']['receiver_mass']:g} kg，初速度 {source['physics']['initial_velocity']:g} m/s；视频为 4 秒。",
                         'en': f"Driver mass {source['physics']['driver_mass']:g} kg; receiver mass {source['physics']['receiver_mass']:g} kg; initial speed {source['physics']['initial_velocity']:g} m/s; four-second playback."}}
    manifest = dict(schema_version=3, suite_name='pcve_toy_car_collision_suite',
                    description='One source and five requested mass, speed, friction and deletion edits, including a mid-run speed boost applied inside the running simulation.',
                    baseline_physics=source['physics'], total_frames=round(args.fps * args.duration_sec * args.slow_motion),
                    resolution=args.resolution, fps=args.fps, duration_sec=args.duration_sec * args.slow_motion,
                    samples=args.samples, physical_duration_sec=args.duration_sec,
                    playback_duration_sec=args.duration_sec * args.slow_motion,
                    sample_fps=args.fps * args.slow_motion, slow_motion=args.slow_motion, source=None, edits=[])
    path = args.out_root / 'suite_manifest.json'
    for case_id, instruction in [(SOURCE_CASE_ID, None), *cases]:
        folder = args.out_root / 'cases' / case_id
        scenario = source
        record = dict(case_id=case_id, kind='edit' if instruction else 'source', case_dir=str(folder), status='pending')
        if instruction:
            edit = dsl.parse(instruction, VOCAB)
            override = {'physics': dsl.to_scenario_override(edit, VOCAB)}
            scenario = merge(source, override)
            if isinstance(edit, dsl.DeleteEdit):
                diff = {'presence (car_b)': {'from': 'present', 'to': 'absent'}}
                summary = 'The receiver car is absent from the physical simulation and rendered scene.'
            elif edit.property_name == 'speed' and edit.object_id == 'car_b':
                speed_before = baseline_receiver_speed_at_frame(edit.at_frame)
                diff = {f'{edit.property_name} ({edit.object_id})':
                        dict(semantics="TIMES scales the receiver car's live speed at the edit frame",
                             multiplier=edit.factor, frame=edit.at_frame,
                             speed_before_m_s=round(speed_before, 6),
                             speed_after_m_s=round(speed_before * edit.factor, 6))}
                summary = f'Only {edit.object_id}.{edit.property_name} is edited; motion is produced by the simulator.'
            else:
                diff = {f'{edit.property_name} ({edit.object_id})':
                        {'from': dsl.baseline_value_for(edit, VOCAB), 'to': dsl.resolved_to_value(edit, VOCAB)}}
                summary = f'Only {edit.object_id}.{edit.property_name} is edited; motion is produced by the simulator.'
                if dsl.is_timed(edit):
                    summary = (f'{summary} The new friction is written into the running simulation at frame '
                               f'{edit.at_frame}, then the simulation continues from that state.')
            diff['timing'] = dsl.timing_diff(edit, VOCAB)
            record.update(source_case_id=SOURCE_CASE_ID, edit_dsl=instruction,
                          applies_from_frame=dsl.starts_at_frame(edit), edit_summary=summary,
                          physics_diff=diff, prompts=dsl.make_prompts(edit, VOCAB),
                          scenario_overrides_json=str(folder / 'scenario_overrides.json'), prompts_json=str(folder / 'prompts.json'))
            write_json(folder / 'scenario_overrides.json', override)
            write_json(folder / 'prompts.json', dict(schema_version=2, **{key: record[key] for key in (
                'case_id', 'source_case_id', 'edit_dsl', 'edit_summary', 'applies_from_frame', 'physics_diff', 'prompts')}))
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
            if not args.dry_run and not instruction and args.duration_sec >= 1 and not record['quality']['transmission_observed']:
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

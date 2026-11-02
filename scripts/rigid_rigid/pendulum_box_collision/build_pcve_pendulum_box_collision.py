"""Source case plus five single-variable edits, in the original suite layout.

Four edits each move one of the scene's launch-condition knobs (the bob's mass
and speed, the block's mass and speed) off its baseline for the whole clip; the
fifth lowers the pair restitution partway through, between the first face
impact and the pendulum's return trip. Each case changes exactly one number,
which is what makes the manifest's ``physics_diff`` a complete description of
the difference between its video and the source video.
"""
# PCVE_UNIFIED_ENTRY_BEGIN

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




from pathlib import Path
import argparse, json, shutil, sys, subprocess, time, hashlib
import pcve_edit_dsl as dsl  # noqa: E402
from scene_config import defaults, merge, validate  # noqa: E402
from edit_vocab import VOCAB, EDIT_CASES  # noqa: E402
from runtime_support import python_for  # noqa: E402
from validate_pendulum_box_collision import validate_cache  # noqa: E402

ROOT = _PCVE_PROJECT_ROOT
SOURCE_CASE_ID = 'pendulum_box_collision_baseline'
BLEND_NAME = 'pendulum_box_collision.blend'


from pcve_scene_runtime import add_build_arguments, render_prefix, append_render_options, implementation_hashes

def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')


def fingerprint(s, args):
    source = implementation_hashes(Path(__file__).parent)
    source.update({f'assets/{p.name}': hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in (Path(__file__).parent / 'assets').glob('*') if p.is_file()})
    return hashlib.sha256(json.dumps(dict(scenario=s, implementation=source, engine=args.engine,
                                          device=args.device, preview_frame=args.preview_frame,mode=args.mode,
                                          simulation_only=args.simulate_only), sort_keys=True).encode()).hexdigest()


def standardize_render_outputs(folder, has_overrides):
    files = dict(video='video.mp4', ground_truth='ground_truth_transforms.json',
                 scenario_metadata='scenario_metadata.json')
    if has_overrides:
        files['scenario_overrides'] = 'scenario_overrides.json'
    for name in files.values():
        if not (folder / name).exists():
            raise FileNotFoundError(f'Missing output: {folder / name}')
    return {key: str((folder / name).resolve()) for key, name in files.items()}


def run_logged(command, log_path, args):
    """Run one external step the way the older scenes do: quiet log by default,
    console output with --verbose-render."""
    if args.verbose_render:
        subprocess.run(command, check=True)
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open('w', encoding='utf-8') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)


def clean_stale(out_root, keep_ids):
    """Drop case directories that are no longer part of this suite."""
    cases_dir = out_root / 'cases'
    if not cases_dir.exists():
        return
    for path in sorted(cases_dir.iterdir()):
        if path.is_dir() and path.name not in keep_ids:
            print(f'[suite] remove stale case directory {path}')
            shutil.rmtree(path)


def commands_for(folder, args):
    """The simulation and render commands a case would run, in that order."""
    sim = [str(args.physics_python), str(Path(__file__).with_name('simulate_pendulum_box_collision.py')),
           '--out', str(folder / 'physics_transforms.json'),
           '--scenario-json', str(folder / 'scenario_input.json')]
    script = Path(__file__).with_name('render_pendulum_box_collision.py')
    render = render_prefix(args, script)
    render += ['--physics-json', str(folder / 'physics_transforms.json'), '--out-dir', str(folder),
               '--engine', args.engine, '--device', args.device, '--samples', str(args.samples),
               '--resolution', *map(str, args.resolution), '--mode', args.mode]
    return sim, append_render_options(render, args)


def run_case(folder, s, args):
    validate(s)
    if args.dry_run:
        sim, render = commands_for(folder, args)
        for command in (([] if args.render_only else [sim]) + ([] if args.simulate_only else [render])):
            print(subprocess.list2cmdline(command))
        return dict(status='dry_run', valid=False, quality=dict(valid=False))
    folder.mkdir(parents=True, exist_ok=True)
    fp = fingerprint(s, args)
    status_file = folder / 'run_status.json'
    required = ['physics_transforms.json', 'simulation_metrics.json']
    if not args.simulate_only:
        required += ['preview.png', 'ground_truth_transforms.json', 'scenario_metadata.json',
                     'render_validation.json', BLEND_NAME]
        required += ['video.mp4'] if args.mode == 'animation' else []
    if args.skip_existing and status_file.exists():
        status = json.loads(status_file.read_text(encoding='utf-8'))
        if (status.get('fingerprint') == fp and status.get('valid')
                and all((folder / name).exists() for name in required)):
            return dict(status, status='skipped_existing')
    sim, render = commands_for(folder, args)
    if args.render_only:
        data = json.loads((folder / 'physics_transforms.json').read_text(encoding='utf-8'))
        validate_cache(data, s)
        write_json(folder / 'scenario_input.json', s)
    else:
        write_json(folder / 'scenario_input.json', s)
        run_logged(sim, folder / 'simulation.log', args)
        data = json.loads((folder / 'physics_transforms.json').read_text(encoding='utf-8'))
        validate_cache(data, s)
    if not args.simulate_only:
        run_logged(render, folder / 'render.log', args)
    status = dict(status='completed', valid=True, simulation_only=args.simulate_only,
                  render_mode=args.mode, fingerprint=fp, quality=data['quality'])
    write_json(status_file, status)
    return status


def parser():
    p = argparse.ArgumentParser()
    p.add_argument('--out-root', type=Path, default=ROOT / 'renders/pcve_pendulum_box_collision_suite')
    p.add_argument('--physics-python', type=Path, default=python_for('physics'))
    p.add_argument('--render-python', type=Path, default=python_for('render'))
    p.add_argument('--blender', type=Path)
    # Match the shared scene duration so all nine videos remain frame-aligned.
    p.add_argument('--duration-sec', type=float, default=defaults()['render']['duration_sec'])
    p.add_argument('--fps', type=int, default=24)
    p.add_argument('--slow-motion', type=int, choices=(1, 2, 4, 8), default=defaults()['render']['slow_motion'])
    p.add_argument('--samples', type=int, default=defaults()['render']['samples'])
    p.add_argument('--resolution', type=int, nargs=2, default=defaults()['render']['resolution'])
    p.add_argument('--engine', choices=('eevee', 'cycles'), default='cycles')
    p.add_argument('--device', choices=('auto', 'cpu'), default='auto')
    p.add_argument('--mode', choices=('preview', 'animation'), default='animation')
    p.add_argument('--simulate-only', action='store_true')
    p.add_argument('--render-only', action='store_true')
    p.add_argument('--skip-existing', action='store_true')
    p.add_argument('--cases', nargs='+')
    p.add_argument('--dry-run', action='store_true', help='Print the commands each case would run and stop.')
    p.add_argument('--verbose-render', action='store_true', help='Stream simulation and render output to the console.')
    p.add_argument('--clean-stale-cases', action='store_true', help='Delete case directories that are no longer part of this suite.')
    return add_build_arguments(p)


def main():
    args = parser().parse_args()
    args.out_root = args.out_root.resolve()
    if args.render_only and args.simulate_only:
        raise ValueError('Conflicting execution modes')
    cases = EDIT_CASES
    if args.cases:
        unknown = set(args.cases) - {SOURCE_CASE_ID, *[name for name, _ in cases]}
        if unknown:
            raise ValueError(f'Unknown cases: {unknown}')
        cases = [entry for entry in cases if entry[0] in args.cases]
    source = defaults()
    source['render'].update(fps=args.fps, duration_sec=args.duration_sec, slow_motion=args.slow_motion,
                            resolution=args.resolution, samples=args.samples)
    validate(source)
    if args.dry_run:
        for case_id, instruction in [(SOURCE_CASE_ID, None), *cases]:
            scenario = source
            if instruction:
                scenario = merge(source, {'physics': dsl.to_scenario_override(dsl.parse(instruction, VOCAB), VOCAB)})
            print(f'[suite] {case_id}', flush=True)
            run_case(args.out_root / 'cases' / case_id, scenario, args)
        return
    if args.clean_stale_cases:
        clean_stale(args.out_root, {SOURCE_CASE_ID, *[name for name, _ in EDIT_CASES]})
    b = source['physics']
    description = {
        'vague': {'zh': '木盒从实验台左端滑入画面，撞上摆动的单摆摆锤。',
                  'en': 'A wooden block slides in from the left end of the lab bench and strikes a swinging pendulum bob.'},
        'quantitative': {
            'zh': (f"质量 {b['box_mass']:g} kg 的木盒从实验台左端以 {b['box_speed']:g} m/s 滑向摆锤；"
                   f"摆锤质量 {b['bob_mass']:g} kg，先在最低点以 {b['bob_speed']:g} m/s 向右侧摆出，摆完半个周期"
                   f"回到最低点时与木盒正面相撞，随后两者各自弹开。"),
            'en': (f"A {b['box_mass']:g} kg wooden block slides in from the left end of the bench at "
                   f"{b['box_speed']:g} m/s towards a {b['bob_mass']:g} kg pendulum bob that leaves the bottom of "
                   f"its arc at {b['bob_speed']:g} m/s, and meets it face to face one half period later; both "
                   f"bodies rebound.")}}
    manifest = dict(
        schema_version=3, suite_name='pcve_pendulum_box_collision_suite',
        description=('One source and five single-variable edits -- bob mass, bob speed, block mass, block '
                     'speed, and a restitution drop that lands partway through the clip; the rebound of '
                     'both bodies is measured, never scripted.'),
        baseline_physics=source['physics'],
        total_frames=round(args.fps * args.duration_sec * args.slow_motion),
        resolution=args.resolution, fps=args.fps, duration_sec=args.duration_sec * args.slow_motion,
        samples=args.samples, physical_duration_sec=args.duration_sec,
        playback_duration_sec=args.duration_sec * args.slow_motion,
        sample_fps=args.fps * args.slow_motion, slow_motion=args.slow_motion,
        source=None, edits=[])
    path = args.out_root / 'suite_manifest.json'
    for i, (case_id, instruction) in enumerate([(SOURCE_CASE_ID, None), *cases]):
        folder = args.out_root / 'cases' / case_id
        s = source
        record = dict(case_id=case_id, kind='edit' if instruction else 'source', seed=9600 + i,
                      case_dir=str(folder.resolve()), status='pending')
        if instruction:
            edit = dsl.parse(instruction, VOCAB)
            override = {'physics': dsl.to_scenario_override(edit, VOCAB)}
            s = merge(source, override)
            record.update(
                source_case_id=SOURCE_CASE_ID, edit_dsl=instruction,
                edit_summary=(dsl.summarize_set_edit(edit, VOCAB) + ' The two bodies are then released, '
                              'and their rebound is solved rather than authored.'),
                applies_from_frame=dsl.starts_at_frame(edit),
                physics_diff={f'{edit.property_name} ({edit.object_id})':
                              {'from': dsl.baseline_value_for(edit, VOCAB),
                               'to': dsl.resolved_to_value(edit, VOCAB)},
                              'timing': dsl.timing_diff(edit, VOCAB)},
                prompts=dsl.make_prompts(edit, VOCAB),
                scenario_overrides_json=str((folder / 'scenario_overrides.json').resolve()),
                prompts_json=str((folder / 'prompts.json').resolve()))
            if dsl.is_timed(edit):
                record['edit_summary'] += (f' The new restitution is applied inside the running simulation '
                                           f'at frame {edit.at_frame}, then the simulation continues from that state.')
            write_json(folder / 'scenario_overrides.json', override)
            write_json(folder / 'prompts.json',
                       {'schema_version': 2, **{key: record[key] for key in
                        ('case_id', 'source_case_id', 'edit_dsl', 'edit_summary',
                         'applies_from_frame', 'physics_diff', 'prompts')}})
            manifest['edits'].append(record)
        else:
            record['description'] = description
            manifest['source'] = record
            write_json(folder / 'prompts.json', dict(schema_version=1, case_id=case_id, kind='source',
                                                     prompts=description))
        write_json(path, manifest)
        print(f'[suite] {case_id}', flush=True)
        start = time.perf_counter()
        try:
            record.update(run_case(folder, s, args))
            if not args.dry_run and not instruction:
                # The source case has to do the thing the scene is named after,
                # and do it hard enough that the video reads without a caption.
                if not record['quality']['hit_box']:
                    raise RuntimeError('Baseline never struck the pendulum bob')
                if record['quality']['box_rebound_speed_mps'] < .12:
                    raise RuntimeError('Baseline block was not knocked back')
                if record['quality']['bob_peak_swing_deg'] < 15.:
                    raise RuntimeError('Baseline bob barely swings')
                # The staging: half a period of free swing, then a hit at the
                # bottom of the arc. Moving the start position or the friction
                # would quietly break this, so it is checked here as well.
                if not .54 < record['quality']['first_contact_sec'] < .67:
                    raise RuntimeError('Baseline contact is not at half a period')
                if abs(record['quality']['bob_angle_at_contact_deg']) > 2.5:
                    raise RuntimeError('Baseline contact is not at the bottom of the arc')
            if not args.dry_run and not args.simulate_only and args.mode == 'animation':
                record['outputs'] = standardize_render_outputs(folder, bool(instruction))
            else:
                record['outputs'] = {key: str((folder / name).resolve()) for key, name in
                                     [('physics', 'physics_transforms.json'),
                                      ('scenario_input', 'scenario_input.json'),
                                      ('preview', 'preview.png'),
                                      ('ground_truth', 'ground_truth_transforms.json')]
                                     if (folder / name).exists()}
        except Exception:
            record['status'] = 'failed'
            write_json(path, manifest)
            raise
        record['elapsed_sec'] = round(time.perf_counter() - start, 3)
        write_json(path, manifest)


if __name__ == '__main__':
    main()

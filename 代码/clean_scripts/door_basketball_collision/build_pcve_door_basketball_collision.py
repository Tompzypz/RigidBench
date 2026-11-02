"""Build one source and five named PCVE edits using the shared edit DSL."""

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
import math
from pathlib import Path
import shutil
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
from pcve_scene_runtime import python_for, render_prefix
if __package__:
    from . import scenario_io, edit_vocab
    from .simulate_door_basketball import simulate
else:
    import scenario_io
    import edit_vocab
    from simulate_door_basketball_collision import simulate
dsl = edit_vocab.dsl
VOCAB = edit_vocab.VOCAB
BASELINE_PHYSICS = edit_vocab.BASELINE_PHYSICS
DESCRIPTION = edit_vocab.DESCRIPTION
EDIT_CASES = edit_vocab.EDIT_CASES
SOURCE_CASE_ID = 'door_basketball_collision_baseline'
SOURCE_SEED = 6701
LEAF_ASSET = ROOT / 'assets' / 'scenarios' / 'door_basketball_collision' / 'door_leaf.json'
# An edit has to move something a viewer can see: two degrees of door travel is
# about a centimetre of leaf edge, and 2 cm of ball is a couple of pixels.
MIN_DOOR_TRAVEL_DEG = 2.0
MIN_BALL_SHIFT_M = 0.02


def physics_diff(edit):
    """The before/after block the manifest and prompts.json carry."""
    if isinstance(edit, dsl.DeleteEdit):
        diff = {f'presence ({edit.object_id})': {'from': 'present', 'to': 'absent'}}
    elif isinstance(edit, dsl.AddEdit):
        diff = {'presence': {'from': 'absent', 'to': 'present'},
                'position': dsl.add_position_diff(edit, VOCAB)}
    else:
        diff = {f'{edit.property_name} ({edit.object_id})': {
            'from': dsl.baseline_value_for(edit, VOCAB),
            'to': dsl.resolved_to_value(edit, VOCAB)}}
        # A ``TO`` edit names an absolute value and has no multiplier.
        if edit.factor is not None:
            diff[f'{edit.property_name} ({edit.object_id})']['factor'] = edit.factor
    diff['timing'] = dsl.timing_diff(edit, VOCAB)
    return diff


def build_edit_record(case):
    parsed = dsl.parse(case.dsl, VOCAB)
    return dict(edit_dsl=case.dsl, edit_summary=case.summary,
                applies_from_frame=dsl.starts_at_frame(parsed),
                prompts=dsl.make_prompts(parsed, VOCAB),
                physics_diff=physics_diff(parsed),
                physics_override=dsl.to_scenario_override(parsed, VOCAB))


def write_prompt_file(folder, case, info):
    path = folder / 'prompts.json'
    scenario_io.write_json(path, dict(schema_version=2, case_id=case.case_id,
        source_case_id=SOURCE_CASE_ID, **{key: info[key] for key in
        ('edit_dsl', 'edit_summary', 'applies_from_frame', 'physics_diff', 'prompts')}))
    return path


def implementation_signature():
    files = sorted(HERE.glob('*.py')) + [ROOT / 'scripts' / name for name in
                                       ('pcve_edit_dsl.py', 'pcve_timed_edits.py')]
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def render_complete(folder, scene, data, args, signature):
    required = ('resolved_scenario.json', 'scenario_metadata.json',
                'ground_truth_transforms.json', 'render_validation.json',
                'door_basketball_collision.blend', 'run_status.json')
    if not all((folder / name).is_file() for name in required):
        return False
    status = scenario_io.read_json(folder / 'run_status.json')
    if status.get('implementation_signature') != signature or status.get('simulation_only', True):
        return False
    if scenario_io.read_json(folder / 'resolved_scenario.json') != scene:
        return False
    meta = scenario_io.read_json(folder / 'scenario_metadata.json')
    if meta['resolution'] != args.resolution or meta['samples'] != args.samples:
        return False
    truth = scenario_io.read_json(folder / 'ground_truth_transforms.json')
    if len(truth['frames']) != len(data['frames']):
        return False
    origin = data['geometry']['leaf']['hinge_world']
    for cached, physical in zip(truth['frames'], data['frames']):
        if cached.get('ball_active', True) != physical['ball_active']:
            return False
        if abs(cached['door_angle_deg'] - math.degrees(physical['door_angle_rad'])) > 1e-5:
            return False
        if physical['ball_active']:
            world = [a + b for a, b in zip(origin, physical['ball_location'])]
            if (cached['ball_location'] is None or math.dist(cached['ball_location'], world) > 1e-5 or
                    math.dist(cached['ball_quaternion_xyzw'], physical['ball_quaternion_xyzw']) > 1e-5):
                return False
        elif cached['ball_location'] is not None:
            return False
    if args.mode == 'animation':
        paths = [folder / 'door_basketball_collision.mp4']
    elif args.mode == 'build':
        paths = [folder / 'door_basketball_collision.blend']
    elif args.mode == 'preview':
        frames = {1, data['quality']['impact_frame'] or 1, data['frame_end']}
        paths = [folder / f'preview_frame_{f:04d}.png' for f in frames]
    else:
        frames = [int(f) for f in args.keyframes.split(',')] if args.keyframes else scene['layout']['keyframes']
        frames = {min(max(1, f), data['frame_end']) for f in frames}
        paths = [folder / 'keyframes' / f'frame_{f:04d}.png' for f in frames]
    return all(path.is_file() and path.stat().st_size > 0 for path in paths)


def leaf_for(folder):
    """Copy the measured leaf next to the take so the case folder is self-contained."""
    path = folder / 'door_leaf.json'
    if not path.is_file():
        shutil.copy2(LEAF_ASSET, path)
    return path


def check_case(case_id, edit, data, source_data):
    """Reject a take that is not a finite simulation of the edit it claims."""
    frames = data['frames']
    for frame in frames:
        values = [frame['door_angle_rad'], frame['door_angular_velocity'],
                  *frame['door_link_position']]
        if frame['ball_active']:
            values += [*frame['ball_location'], *frame['ball_quaternion_xyzw'],
                       *frame['ball_linear_velocity'], *frame['ball_angular_velocity']]
        if not all(math.isfinite(value) for value in values):
            raise RuntimeError(f'{case_id}: non-finite state at frame {frame["frame_index"]}')
    travel = max(abs(a['door_angle_rad'] - b['door_angle_rad'])
                 for a, b in zip(frames, source_data['frames']))
    shift = max((math.dist(a['ball_location'], b['ball_location'])
                 for a, b in zip(frames, source_data['frames'])
                 if a['ball_active'] and b['ball_active']), default=0.0)
    if math.degrees(travel) < MIN_DOOR_TRAVEL_DEG and shift < MIN_BALL_SHIFT_M:
        raise RuntimeError(f'{case_id}: the edited run is indistinguishable from the source')
    start = dsl.starts_at_frame(edit)
    if dsl.is_timed(edit):
        early = [(f['door_angle_rad'], f['ball_location']) for f in frames[:start - 1]]
        source = [(f['door_angle_rad'], f['ball_location']) for f in source_data['frames'][:start - 1]]
        if early != source:
            raise RuntimeError(f'{case_id}: frames before {start} must reproduce the source exactly')
    if isinstance(edit, dsl.DeleteEdit):
        if data['quality']['ball_visible_frames'] != 0 or data['quality']['impact_frame'] is not None:
            raise RuntimeError(f'{case_id}: the ball is still in the scene')
    elif not dsl.is_timed(edit) and not data['quality']['transmission_observed']:
        raise RuntimeError(f'{case_id}: expected motion transfer did not occur')
    return {'door_travel_shift_deg': round(math.degrees(travel), 3),
            'ball_shift_m': round(shift, 4),
            'timed_events': data['quality'].get('timed_events', [])}


def outputs(folder):
    names = ('scenario_input.json', 'scenario_overrides.json', 'prompts.json',
             'physics_transforms.json', 'simulation_metrics.json', 'ground_truth_transforms.json',
             'scenario_metadata.json', 'render_validation.json', 'door_basketball_collision.blend',
             'door_basketball_collision.mp4')
    result = {name: str((folder / name).resolve()) for name in names if (folder / name).exists()}
    # Match the legacy suites' semantic output keys and standard video name.
    native_video = folder / 'door_basketball_collision.mp4'
    if native_video.is_file():
        video = folder / 'video.mp4'
        if not video.is_file() or video.stat().st_mtime_ns < native_video.stat().st_mtime_ns:
            shutil.copy2(native_video, video)
        result['video'] = str(video.resolve())
    for key, name in {'ground_truth': 'ground_truth_transforms.json',
                      'scenario_metadata': 'scenario_metadata.json',
                      'scenario_overrides': 'scenario_overrides.json',
                      'prompts': 'prompts.json'}.items():
        if (folder / name).is_file():
            result[key] = str((folder / name).resolve())
    keyframes = sorted((folder / 'keyframes').glob('frame_*.png'))
    if keyframes:
        result['keyframes'] = [str(path.resolve()) for path in keyframes]
    return result


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out-root', type=Path, default=ROOT / 'renders/pcve_door_basketball_collision_suite')
    p.add_argument('--simulate-only', action='store_true')
    p.add_argument('--render-python', type=Path, default=python_for('render'))
    p.add_argument('--blender', type=Path,
                   help='Blender executable; otherwise use the render Python with bpy.')
    p.add_argument('--mode', choices=('build', 'preview', 'keyframes', 'animation'), default='keyframes')
    p.add_argument('--resolution', type=int, nargs=2, default=[960, 540])
    p.add_argument('--samples', type=int, default=24)
    p.add_argument('--keyframes', default=None, help='comma-separated frame numbers')
    p.add_argument('--device', choices=('auto', 'cpu'), default='cpu')
    p.add_argument('--only', default=None, help='comma-separated edit IDs; source is always included')
    p.add_argument('--skip-existing', action='store_true')
    return p


def main():
    p = parser()
    args = p.parse_args()
    selected = set(args.only.split(',')) if args.only else {c.case_id for c in EDIT_CASES}
    unknown = selected - {SOURCE_CASE_ID, *[c.case_id for c in EDIT_CASES]}
    if unknown:
        p.error('Unknown case IDs: ' + ', '.join(sorted(unknown)))
    if args.samples <= 0 or any(v <= 0 for v in args.resolution):
        p.error('Samples and resolution must be positive')
    source = scenario_io.load_scenario()
    if source['physics'] != BASELINE_PHYSICS:
        raise ValueError('Source and edit vocabulary baseline disagree')
    physics = source['physics']
    signature = implementation_signature()
    cases = [c for c in EDIT_CASES if c.case_id in selected]
    manifest = dict(schema_version=3, suite_name='pcve_door_basketball_collision_suite',
                    scene=source['scene'], baseline_physics=BASELINE_PHYSICS,
                    fps=physics['fps'], duration_sec=physics['duration_sec'],
                    total_frames=round(physics['fps'] * physics['duration_sec']),
                    edit_count=len(cases),
                    render_mode=None if args.simulate_only else args.mode,
                    source=None, edits=[], cases=[])
    source_data = None
    for index, case in enumerate([None, *cases]):
        start = time.perf_counter()
        name = case.case_id if case else SOURCE_CASE_ID
        folder = args.out_root.resolve() / 'cases' / name
        edit = dsl.parse(case.dsl, VOCAB) if case else None
        info = build_edit_record(case) if case else None
        override = {'physics': info['physics_override']} if info else {'physics': {}}
        scene = scenario_io.merge(source, override)
        scenario_io.validate(scene)
        record = dict(case_id=name, kind='edit' if case else 'source', seed=SOURCE_SEED + index,
                      case_dir=str(folder), status='pending',
                      prompts_json=str(folder / 'prompts.json'),
                      scenario_overrides_json=str(folder / 'scenario_overrides.json'),
                      render_mode=None if args.simulate_only else args.mode)
        if case:
            record.update(source_case_id=SOURCE_CASE_ID, **info)
            write_prompt_file(folder, case, info)
            manifest['edits'].append(record)
        else:
            record['description'] = DESCRIPTION
            scenario_io.write_json(folder / 'prompts.json', dict(schema_version=2, case_id=name,
                                                                kind='source', prompts=DESCRIPTION))
            manifest['source'] = record
        manifest['cases'].append(record)
        scenario_io.write_json(folder / 'scenario_input.json', scene)
        scenario_io.write_json(folder / 'scenario_overrides.json', override)
        scenario_io.write_json(args.out_root / 'suite_manifest.json', manifest)
        try:
            data = simulate(scene, fps=physics['fps'], duration_sec=physics['duration_sec'],
                            substeps=physics['substeps_per_frame'], leaf_path=leaf_for(folder))
            if case is None:
                source_data = data
                # The source take is what every edit is measured against, so its
                # own gate stays exactly as it was.
                if not data['quality']['transmission_observed']:
                    raise RuntimeError('Baseline did not transfer motion to the ball')
                record['check'] = {'door_travel_shift_deg': 0.0, 'ball_shift_m': 0.0, 'timed_events': []}
            else:
                record['check'] = check_case(name, edit, data, source_data)
            scenario_io.write_json(folder / 'physics_transforms.json', data)
            scenario_io.write_json(folder / 'simulation_metrics.json', data['quality'])
            reused = args.skip_existing and render_complete(folder, scene, data, args, signature)
            if not args.simulate_only and not reused:
                command = render_prefix(args, HERE / 'render_door_basketball_collision.py') + [
                           '--scenario', str(folder / 'scenario_input.json'), '--out-dir', str(folder),
                           '--mode', args.mode, '--resolution', *map(str, args.resolution),
                           '--samples', str(args.samples), '--device', args.device]
                if args.keyframes:
                    command.extend(['--keyframes', args.keyframes])
                subprocess.run(command, check=True)
            record.update(status='completed', simulation_only=args.simulate_only, quality=data['quality'],
                          outputs=outputs(folder), elapsed_sec=round(time.perf_counter() - start, 3))
            # A simulation-only refresh must not invalidate a still matching render cache.
            if not args.simulate_only:
                scenario_io.write_json(folder / 'run_status.json', dict(implementation_signature=signature,
                    simulation_only=False, mode=args.mode, valid=True))
            print(f'[suite] {name}: impact={data["quality"]["impact_frame"]}, '
                  f'visible_ball_frames={data["quality"]["ball_visible_frames"]}, '
                  f'check={record["check"].get("door_travel_shift_deg")} deg / '
                  f'{record["check"].get("ball_shift_m")} m', flush=True)
        except Exception as exc:
            record.update(status='failed', error=str(exc))
            scenario_io.write_json(args.out_root / 'suite_manifest.json', manifest)
            raise
        scenario_io.write_json(args.out_root / 'suite_manifest.json', manifest)


if __name__ == '__main__':
    main()

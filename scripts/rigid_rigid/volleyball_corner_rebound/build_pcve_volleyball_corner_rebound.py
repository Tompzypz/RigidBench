"""Build one fixed source and exactly five independent PCVE edits."""
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
import math
from pathlib import Path
import subprocess
from scene_config import SCENARIO_DIR, load_scenario, write_json, runtime
from pcve_scene_runtime import render_prefix, python_for
from simulate_volleyball_corner_rebound import simulate
from edit_vocab import dsl, VOCAB, EDIT_CASES
from scene_geometry import geometry_snapshot

HERE = Path(__file__).resolve().parent
SOURCE_CASE_ID = 'volleyball_corner_rebound_baseline'

SOURCE_DESCRIPTION = {
    'vague': {
        'zh': '一个排球从画面右上方斜向砸向房间墙角，先落地弹起，再依次撞上两面墙；碰撞摩擦带出自旋，排球随后贴着地面弹跳、滚向房间中部。',
        'en': 'A volleyball is thrown diagonally down into a room corner; it bounces off the floor, then rebounds off both corner walls, picks up spin from contact friction and rolls out across the floor.',
    },
    'quantitative': {
        'zh': '半径 0.105 m、质量 0.27 kg 的排球从 (4.80, 4.50, 2.30) m 处以 5.85 m/s 沿 (-4.80, -3.20, -0.96) 方向斜向下抛出，初始自旋为零，重力 9.81 m/s²；约 0.58 s 首次触地，约 1.33 s 撞上 x=0 的墙，约 2.26 s 撞上 y=0 的墙，4 s 时停在 (2.25, 0.70, 0.10) m 附近。',
        'en': 'A volleyball of radius 0.105 m and mass 0.27 kg leaves (4.80, 4.50, 2.30) m at 5.85 m/s along (-4.80, -3.20, -0.96) with zero initial spin under gravity 9.81 m/s^2. It first touches the floor at about 0.58 s, hits the x=0 wall at about 1.33 s and the y=0 wall at about 2.26 s, and ends near (2.25, 0.70, 0.10) m after 4 s.',
    },
}

# What each edit does to the measured trajectory, in the words of the run the
# case actually produced (baseline: floor 0.583 s, wall_x 1.325 s, wall_y
# 2.263 s, endpoint 2.25/0.70 m, path 10.81 m, peak spin 30.5 rad/s).
EDIT_SUMMARIES = {
    'edit_speed_x15': '排球初始速度从 5.85 m/s 提高到 8.775 m/s，三维方向不变：撞墙提前到 0.74 s，路径从 10.81 m 增至 12.38 m，4 s 时停在 (4.21, 1.23) m，比原轨迹深入房间约 2 m。',
    'edit_restitution_x03': '排球恢复系数从 0.78 降到 0.234：弹跳高度立刻变矮，0.58 s 首次触地后又在 0.89、0.97、1.43、2.36 s 各弹一次，1.33 s 与 2.18 s 两次撞上 x=0 的墙，2.30 s 蹭过 y=0 的墙后停在墙角 (0.15, 0.11) m，全程路径从 10.81 m 缩短到 7.77 m，峰值自旋 29.6 rad/s。',
    'edit_friction_x05': '排球摩擦系数从 0.55 降到 0.275：触地后打滑时间更长，峰值自旋从 30.5 rad/s 降到 19.4 rad/s，球被带出墙角后滑到 (3.97, 1.20) m，比原轨迹远约 1.8 m。',
    'edit_wall_restitution_x04': '墙面恢复系数从 1.0 降到 0.4：撞上 x=0 的墙时法向速度被吃掉六成，排球不再折返回房间中部而是沿墙滑落，2.23 s 又蹭过 y=0 的墙，4 s 时停在墙角 (0.50, 0.20) m，全程路径缩到 9.57 m，与原轨迹相距 1.82 m。',
    'edit_gravity_x25_at24': '第 24 帧（0.958 s，排球第一次弹起后仍在空中）把重力加速度从 -9.81 提高到 -24.525 m/s²，由求解器在第 24 帧接手计算：第 1~23 帧与原视频逐帧一致，之后抛物线明显变矮，第二次触地由 1.541 s 提前到 1.251 s，撞上 y=0 的墙推迟到 2.743 s，4 s 时停在 (0.89, 0.20) m，与原轨迹相距 1.45 m。',
}

def build_record(case_id, edit_dsl):
    """The DSL, its resolved physics diff and its prompts for one edit case."""
    edit = dsl.parse(edit_dsl, VOCAB)
    override = dsl.to_scenario_override(edit, VOCAB)
    if isinstance(edit, dsl.SetEdit):
        difference = {f'{edit.property_name} ({edit.object_id})': {
            'from': dsl.baseline_value_for(edit, VOCAB), 'to': dsl.resolved_to_value(edit, VOCAB)}}
    elif isinstance(edit, dsl.DeleteEdit):
        difference = {f'presence ({edit.object_id})': {'from': 'present', 'to': 'absent'}}
    else:
        difference = {f'position ({edit.object_id})': dsl.add_position_diff(edit, VOCAB)}
    difference['timing'] = dsl.timing_diff(edit, VOCAB)
    if dsl.is_timed(edit):
        difference['timing'].update(schedule=override['timed_edits'],
            note='The parameters leave the baseline values in place and are written into the running solver at this frame.')
    frame = dsl.starts_at_frame(edit)
    return {'case_id': case_id, 'kind': 'edit', 'source_case_id': SOURCE_CASE_ID, 'edit_dsl': edit_dsl,
        'edit_summary': EDIT_SUMMARIES[case_id], 'applies_from_frame': frame,
        'applies_from_time_s': (frame - 1) / VOCAB.baseline_physics['fps'],
        'physics_diff': difference, 'prompts': dsl.make_prompts(edit, VOCAB)}, override

def check_applied(record, override, data):
    """Prove the run really carries the edit the record claims.

    The three things that can drift apart are the scheduled frame, the physics
    the solver ran with, and the physics_diff written for the manifest. They
    are compared here instead of being trusted, and a timed case additionally
    has to show its edit event inside the simulation and an unedited prefix.
    """
    for key, value in override.items():
        if key == 'timed_edits':
            continue
        if data['physics'][key] != value:
            raise ValueError(f'{record["case_id"]}: simulated {key}={data["physics"][key]!r}, record says {value!r}')
    events = data['metrics']['timed_events']
    if 'timed_edits' not in override:
        if events:
            raise ValueError(f'{record["case_id"]}: a whole-clip case reported timed events')
        return {}
    schedule = override['timed_edits']
    if [event['frame_index'] for event in events] != [entry['frame'] for entry in schedule]:
        raise ValueError(f'{record["case_id"]}: applied frames {[e["frame_index"] for e in events]} '
                         f'differ from the schedule {[e["frame"] for e in schedule]}')
    for event, entry in zip(events, schedule):
        for key, value in entry['params'].items():
            if event['parameter'] != key or event['to_value'] != value:
                raise ValueError(f'{record["case_id"]}: simulation applied {event["parameter"]}={event["to_value"]}, '
                                 f'schedule says {key}={value}')
        if event['from_value'] != data['metrics'][f'{event["parameter"]}_baseline']:
            raise ValueError(f'{record["case_id"]}: event starts from {event["from_value"]}, not the baseline')
    return {'timed_events': events}

def compare_to_source(record, data, source):
    """How far the case moved, and -- for a timed case -- whether it started later."""
    offsets = [math.dist(row['ball_location'], base['ball_location'])
               for row, base in zip(data['frames'], source['frames'])]
    frame = record['applies_from_frame']
    if frame > 1 and data['frames'][:frame - 1] != source['frames'][:frame - 1]:
        raise ValueError(f'{record["case_id"]}: frames before {frame} already differ from the source')
    # An edit the solver never received renders as the source video, which is
    # the one failure a manifest full of correct numbers would not show.
    if max(offsets[frame - 1:]) <= 1e-6:
        raise ValueError(f'{record["case_id"]}: the edit changed nothing in the simulated trajectory')
    return {'max_deviation_from_source_m': max(offsets),
        'deviation_at_edit_frame_m': offsets[frame - 1],
        'source_prefix_frames': frame - 1,
        'source_prefix_identical': frame == 1 or data['frames'][:frame - 1] == source['frames'][:frame - 1]}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-root', type=Path, default=_PCVE_PROJECT_ROOT / 'renders' / 'pcve_volleyball_corner_rebound_suite')
    parser.add_argument('--camera-preset', choices=('comparison', 'scene'), default='comparison',
        help='Full-suite comparison uses a shared fixed wide camera; scene uses the preferred close camera')
    parser.add_argument('--simulate-only', action='store_true')
    parser.add_argument('--reuse-physics', action='store_true', help='Reuse only cached physics that matches parameters and static colliders')
    parser.add_argument('--mode', choices=('build', 'preview', 'keyframes', 'animation'), default='keyframes')
    parser.add_argument('--only', help='Comma-separated edit IDs; source is always included')
    parser.add_argument('--resolution', nargs=2, type=int, default=(960, 540))
    parser.add_argument('--samples', type=int, default=24)
    parser.add_argument('--engine', choices=('cycles', 'eevee'), default='cycles')
    parser.add_argument('--device', choices=('auto', 'cpu'), default='cpu')
    parser.add_argument('--render-python', type=Path, default=python_for('render'))
    parser.add_argument('--blender', type=Path,
                        help='Blender executable; otherwise use the render Python with bpy.')
    parser.add_argument('--keyframes', default='1,15,24,33,56,72,96',
        help='Shared comparison frames spanning the four seconds, including the timed gravity frame')
    parser.add_argument('--dry-run', action='store_true', help='Print what each case would write and run, then stop')
    args = parser.parse_args()
    selected = set(args.only.split(',')) if args.only else {case_id for case_id, _ in EDIT_CASES}
    unknown = selected - {case_id for case_id, _ in EDIT_CASES}
    if unknown:
        parser.error(f'Unknown case IDs: {sorted(unknown)}')
    root = args.out_root.resolve()
    baseline = VOCAB.baseline_physics
    fps, duration = int(baseline['fps']), float(baseline['duration_sec'])
    source_record = {'case_id': SOURCE_CASE_ID, 'kind': 'source', 'source_case_id': None, 'edit_dsl': None,
        'edit_summary': '排球从空中斜向砸入墙角，经历下落、两次触地、两面墙碰撞，碰撞摩擦产生自旋后滚出墙角。',
        'applies_from_frame': 1, 'applies_from_time_s': 0.0, 'physics_diff': {}, 'description': SOURCE_DESCRIPTION}
    jobs = [('source', source_record, {})]
    for case_id, edit_dsl in EDIT_CASES:
        if case_id in selected:
            record, physics_override = build_record(case_id, edit_dsl)
            jobs.append(('edit', record, physics_override))
    manifest = {'schema_version': 3, 'suite_name': 'pcve_volleyball_corner_rebound_suite',
        'interaction_category': 'rigid_rigid',
        'description': 'One source and exactly five single-edit cases: the ball alone is edited, plus one gravity change applied while it is airborne.',
        'baseline_physics': baseline, 'fps': fps, 'duration_sec': duration, 'frame_count': round(fps * duration),
        'camera_preset': args.camera_preset, 'engine': args.engine, 'samples': args.samples,
        'resolution': list(args.resolution), 'render_mode': 'simulate-only' if args.simulate_only else args.mode,
        'source': None, 'edits': []}
    source_data = None
    if args.dry_run:
        for kind, record, physics_override in jobs:
            print(f'{record["case_id"]}: physics={physics_override or "baseline"} '
                  f'from frame {record["applies_from_frame"]} -> {root / "cases" / record["case_id"]}')
        return
    for kind, record, physics_override in jobs:
        case_dir = root / 'cases' / record['case_id']
        case_dir.mkdir(parents=True, exist_ok=True)
        overrides = {'physics': physics_override} if physics_override else {}
        if args.camera_preset == 'comparison':
            overrides['render'] = json.loads((SCENARIO_DIR / 'comparison_camera.json').read_text(encoding='utf-8'))['render']
        write_json(case_dir / 'scenario_overrides.json', overrides)
        write_json(case_dir / 'prompts.json', record)
        scenario = load_scenario(overrides)
        write_json(case_dir / 'scenario_input.json', scenario)
        if args.reuse_physics:
            data = json.loads((case_dir / 'physics_transforms.json').read_text(encoding='utf-8'))
            if data['physics'] != scenario['physics'] or data.get('static_geometry') != geometry_snapshot():
                raise ValueError(f'Cached scene mismatch: {record["case_id"]}')
        else:
            data = simulate(scenario)
        write_json(case_dir / 'physics_transforms.json', data)
        write_json(case_dir / 'simulation_metrics.json', data['metrics'])
        if not data['metrics']['finite_states']:
            raise ValueError(f'{record["case_id"]}: non-finite trajectory')
        applied = check_applied(record, physics_override, data)
        record['metrics'] = {'wall_collisions': [(event['wall'], round(event['time_sec'], 3)) for event in data['metrics']['wall_collisions']],
            'path_length_m': data['metrics']['path_length_m'],
            'floor_collision_count': len(data['metrics']['floor_collisions']),
            'peak_angular_speed_rad_s': data['metrics']['max_angular_speed_rad_s'],
            'final_position': data['metrics']['final_position'], 'gravity_z_final': data['metrics']['gravity_z_final']}
        if kind == 'source':
            source_data = data
        else:
            record.update(applied, **compare_to_source(record, data, source_data))
        write_json(case_dir / 'run_status.json', {'simulation': 'complete', 'render': 'pending' if not args.simulate_only else 'not_requested'})
        if not args.simulate_only:
            command = render_prefix(args, HERE / 'render_volleyball_corner_rebound.py') + ['--out-dir', str(case_dir),
                '--scenario-overrides-json', str(case_dir / 'scenario_overrides.json'), '--mode', args.mode,
                '--physics-json', str(case_dir / 'physics_transforms.json'),
                '--resolution', *map(str, args.resolution), '--samples', str(args.samples), '--engine', args.engine,
                '--device', args.device, '--keyframes', args.keyframes]
            with (case_dir / 'render.log').open('w', encoding='utf-8') as log:
                completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
            if completed.returncode:
                write_json(case_dir / 'run_status.json', {'simulation': 'complete', 'render': 'failed'})
                raise RuntimeError(f'Render failed, see {case_dir / "render.log"}')
            write_json(case_dir / 'run_status.json', {'simulation': 'complete', 'render': 'complete'})
        entry = {**record, 'directory': str(case_dir), 'physics_transforms': str(case_dir / 'physics_transforms.json'),
            'scenario_overrides_json': str(case_dir / 'scenario_overrides.json'), 'prompts_json': str(case_dir / 'prompts.json'),
            'ground_truth': str(case_dir / 'ground_truth_transforms.json') if not args.simulate_only else None,
            'video': str(case_dir / 'video.mp4') if args.mode == 'animation' and not args.simulate_only else None}
        if record['kind'] == 'source':
            manifest['source'] = entry
        else:
            manifest['edits'].append(entry)
        write_json(root / 'suite_manifest.json', manifest)
        if record['kind'] == 'edit':
            print(f'{record["case_id"]}: from frame {record["applies_from_frame"]}, '
                  f'source prefix identical={record["source_prefix_identical"]}, '
                  f'max deviation={record["max_deviation_from_source_m"]:.3f} m, '
                  f'walls={record["metrics"]["wall_collisions"]}', flush=True)
        else:
            print(f'{record["case_id"]}: walls={record["metrics"]["wall_collisions"]}', flush=True)
    write_json(root / 'suite_manifest.json', manifest)

if __name__ == '__main__':
    main()

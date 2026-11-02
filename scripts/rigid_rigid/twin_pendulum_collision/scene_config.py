"""Baseline and edit overrides; receiver mass is fixed, presence is editable."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
from copy import deepcopy
import json
import math

SCENE_NAME = 'twin_pendulum_collision'
BASELINE_PHYSICS = dict(driver_mass=.26, initial_angle_deg=32., drag_coefficient=.006,
                        receiver_active=[1])
PHYSICS_LIMITS = dict(driver_mass=(.08, .80), initial_angle_deg=(12., 55.), drag_coefficient=(0., .08))
TOTAL_FRAMES = 144


def defaults():
    return dict(schema_version=1, scene=SCENE_NAME, physics=deepcopy(BASELINE_PHYSICS),
                render=dict(fps=24, duration_sec=6., slow_motion=1, resolution=[960, 540], samples=32),
                camera=dict(location=[.68, -1.90, 1.36], target=[-.015, 0., 1.04], lens_mm=55))


def merge(base, overrides):
    result = deepcopy(base)
    for key, value in overrides.items():
        if key not in result and key != 'timed_edits':
            raise ValueError(f'Unknown scenario field: {key}')
        result[key] = merge(result[key], value) if isinstance(value, dict) else deepcopy(value)
    return result


def validate(s):
    if set(s) - {'schema_version', 'scene', 'physics', 'render', 'camera', 'seed'}:
        raise ValueError('Unknown scenario field')
    if s['scene'] != SCENE_NAME or s['schema_version'] != 1:
        raise ValueError('Wrong scene/schema')
    if set(s['physics']) - {*BASELINE_PHYSICS, 'timed_edits'} or set(BASELINE_PHYSICS) - set(s['physics']):
        raise ValueError('Unknown/missing physics parameter')
    for key, (low, high) in PHYSICS_LIMITS.items():
        value = s['physics'][key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f'{key} must be finite and within {low}..{high}')
    if s['physics']['receiver_active'] not in ([0], [1]):
        raise ValueError('receiver_active must be [0] or [1]')
    r = s['render']
    if isinstance(r['fps'], bool) or not isinstance(r['fps'], int) or r['fps'] <= 0:
        raise ValueError('fps must be a positive integer')
    if r['slow_motion'] not in (1, 2, 4, 8) or 4800 % (r['fps'] * r['slow_motion']):
        raise ValueError('fps * slow_motion must divide the 4800 Hz physics clock')
    if not math.isfinite(r['duration_sec']) or r['duration_sec'] <= 0 or round(r['fps'] * r['slow_motion'] * r['duration_sec']) < 2:
        raise ValueError('Duration must include at least two sampled frames')
    if len(r['resolution']) != 2 or any(not isinstance(v, int) or v <= 0 for v in r['resolution']):
        raise ValueError('Resolution must contain two positive integers')
    if not isinstance(r['samples'], int) or r['samples'] <= 0:
        raise ValueError('samples must be positive')
    count = round(r['fps'] * r['slow_motion'] * r['duration_sec'])
    schedule = s['physics'].get('timed_edits', [])
    if not isinstance(schedule, list):
        raise ValueError('timed_edits must be a list')
    frames = set()
    for event in schedule:
        if not isinstance(event, dict) or set(event) != {'frame', 'params'}:
            raise ValueError('Each timed edit needs frame and params')
        frame = event['frame']
        if isinstance(frame, bool) or not isinstance(frame, int) or not 2 <= frame <= count or frame in frames:
            raise ValueError('Timed edit frames must be distinct integers within the clip, after frame 1')
        frames.add(frame)
        if event['params'] != {'receiver_active': [0]}:
            raise ValueError('Only timed DELETE receiver is implemented; parameter edits start at frame 1')
    for key in ('location', 'target'):
        if len(s['camera'][key]) != 3 or not all(math.isfinite(v) for v in s['camera'][key]):
            raise ValueError('Invalid camera vector')
    if not math.isfinite(s['camera']['lens_mm']) or s['camera']['lens_mm'] <= 0:
        raise ValueError('Invalid camera lens')


def load_scenario(args):
    s = json.loads(args.scenario_json.read_text(encoding='utf-8')) if args.scenario_json else defaults()
    if args.scenario_overrides_json:
        s = merge(s, json.loads(args.scenario_overrides_json.read_text(encoding='utf-8')))
    for key in PHYSICS_LIMITS:
        if getattr(args, key, None) is not None:
            s['physics'][key] = getattr(args, key)
    for key in ('fps', 'duration_sec', 'slow_motion'):
        if getattr(args, key, None) is not None:
            s['render'][key] = getattr(args, key)
    validate(s)
    return s


def add_scenario_arguments(parser):
    from pathlib import Path
    parser.add_argument('--scenario-json', type=Path)
    parser.add_argument('--scenario-overrides-json', type=Path)
    for key in PHYSICS_LIMITS:
        parser.add_argument('--' + key.replace('_', '-'), type=float)
    parser.add_argument('--fps', type=int)
    parser.add_argument('--duration-sec', type=float)
    parser.add_argument('--slow-motion', type=int, choices=(1, 2, 4, 8))
    return parser

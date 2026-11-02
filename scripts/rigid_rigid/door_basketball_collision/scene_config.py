"""Single scenario loader for simulation, rendering, suites and CLI edits."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import argparse
import copy
import json
import math
from pathlib import Path

ROOT = _PCVE_ROOT
SCENARIO_PATH = ROOT / 'assets' / 'scenarios' / 'door_basketball_collision' / 'scenario.json'
PARAMETERS = {
    'door_initial_velocity': (0.0, 8.0, 'rad/s; positive opens the door into the room'),
    'door_mass': (2.0, 80.0, 'kg'),
    'ball_mass': (0.2, 12.4, 'kg'),
}
EDIT_FIELDS = {*PARAMETERS, 'ball_active', 'timed_edits'}
# What a schedule entry may write into a running simulation: the hinge torque
# is applied every substep, so changing it partway through changes what the
# leaf does next; a mass change rewrites the body the contact acts on.
TIMED_FIELDS = {'door_hinge_friction', 'door_mass', 'ball_mass', 'ball_active'}
# What a schedule entry may write into a running simulation: the hinge torque
# is applied every substep, so changing it partway through changes what the
# leaf does next; a mass change rewrites the body the contact acts on.
TIMED_FIELDS = {'door_hinge_friction', 'door_mass', 'ball_mass', 'ball_active'}


def ball_active(value):
    """Accept the shared DSL's one-element presence list (or a scalar flag)."""
    flags = value if isinstance(value, list) else [value]
    if len(flags) != 1 or isinstance(flags[0], bool) or flags[0] not in (0, 1):
        raise ValueError('ball_active must be [0] or [1]')
    return bool(flags[0])


def read_json(path):
    value = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError('Expected a JSON object')
    return value


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')


def add_parameter_arguments(parser):
    for name, (low, high, units) in PARAMETERS.items():
        parser.add_argument('--' + name.replace('_', '-'), type=float,
                            help=f'{units}; supported range {low}..{high}')


def merge(base, update):
    result = copy.deepcopy(base)
    for key, value in update.items():
        if key not in result:
            raise ValueError(f'Unknown scenario field: {key}')
        result[key] = merge(result[key], value) if isinstance(value, dict) else copy.deepcopy(value)
    return result


def validate(scene):
    if scene['scene'] != 'door_basketball_collision':
        raise ValueError('Wrong scene')
    for name, (low, high, _) in PARAMETERS.items():
        v = scene['physics'][name]
        if isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) or not low <= v <= high:
            raise ValueError(f'{name} must be finite and within {low}..{high}')
    p = scene['physics']
    if isinstance(p['fps'], bool) or not isinstance(p['fps'], int) or p['fps'] <= 0:
        raise ValueError('fps must be a positive integer')
    if not math.isfinite(p['duration_sec']) or p['duration_sec'] <= 0 or round(p['fps'] * p['duration_sec']) < 2:
        raise ValueError('Duration must contain at least two frames')
    if not isinstance(p['substeps_per_frame'], int) or p['substeps_per_frame'] < 1:
        raise ValueError('substeps_per_frame must be a positive integer')
    ball_active(p.get('ball_active', [1]))
    # A timed edit is a schedule of events inside the clip, not a second
    # spelling of a frame-1 edit: every entry has to name one frame this clip
    # has and one set of parameters the simulator can write into a live run.
    schedule = p.get('timed_edits', [])
    if not isinstance(schedule, list):
        raise ValueError('timed_edits must be a list of {frame, params} events')
    frame_end = round(p['fps'] * p['duration_sec'])
    scheduled = set()
    for entry in schedule:
        if not isinstance(entry, dict) or set(entry) != {'frame', 'params'}:
            raise ValueError('Each timed edit needs exactly a frame and a params object')
        frame = entry['frame']
        if isinstance(frame, bool) or not isinstance(frame, int) or not 2 <= frame <= frame_end:
            raise ValueError(f'Timed edit frame {frame!r} is outside 2..{frame_end}')
        if frame in scheduled:
            raise ValueError(f'Two timed edits target frame {frame}')
        scheduled.add(frame)
        params = entry['params']
        if not isinstance(params, dict) or not params:
            raise ValueError(f'Timed edit at frame {frame} carries no parameters')
        unknown = set(params) - TIMED_FIELDS
        if unknown:
            raise ValueError('A timed edit cannot change: ' + ', '.join(sorted(unknown)))
        for name, value in params.items():
            if isinstance(value, bool):
                raise ValueError(f'{name} must be a number, not a flag')
            if name == 'ball_active':
                ball_active(value)
            elif not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f'Timed {name} must be a finite number')


def load_scenario(scenario_path=None, overrides_path=None, args=None):
    scene = read_json(scenario_path or SCENARIO_PATH)
    if overrides_path:
        overrides = read_json(overrides_path)
        if set(overrides) - {'physics'} or set(overrides.get('physics', {})) - EDIT_FIELDS:
            raise ValueError('Unknown physics edit; allowed: ' + ', '.join(sorted(EDIT_FIELDS)))
        scene = merge(scene, overrides)
    if args is not None:
        for name in (*PARAMETERS, 'fps', 'duration_sec'):
            value = getattr(args, name, None)
            if value is not None:
                scene['physics'][name] = value
        if getattr(args, 'substeps', None) is not None:
            scene['physics']['substeps_per_frame'] = args.substeps
    validate(scene)
    return scene

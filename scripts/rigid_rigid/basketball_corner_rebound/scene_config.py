"""Single source of truth for simulation, edit vocabulary and visual geometry."""
from __future__ import annotations
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import copy
import json
import math
from pathlib import Path

ROOT = _PCVE_ROOT
HERE = next((p for p in (ROOT / 'new-scripts' / 'basketball_corner_rebound', ROOT / 'scripts' / 'rigid_rigid' / 'basketball_corner_rebound') if p.is_dir()), ROOT / 'scripts' / 'rigid_rigid' / 'basketball_corner_rebound')
SCENARIO_DIR = ROOT / 'assets' / 'scenarios' / 'basketball_corner_rebound'
MODELS = ROOT / 'assets' / 'models'

def load_scenario(overrides=None):
    result = json.loads((SCENARIO_DIR / 'scenario.json').read_text(encoding='utf-8'))
    # A timed edit travels as a schedule inside the physics block. The key is
    # reserved on every load so an override that carries one is not unknown.
    result['physics'].setdefault('timed_edits', [])
    # A spin edit is a multiple of the ball's own rotation at that instant,
    # so the declared parameter is a ratio: 1.0 means "the ball is spinning
    # exactly as it already was", and an unedited run keeps exactly that.
    result['physics'].setdefault('ball_spin_scale', 1.0)
    if overrides is not None:
        patch = json.loads(Path(overrides).read_text(encoding='utf-8')) if isinstance(overrides, (str, Path)) else copy.deepcopy(overrides)
        for section, values in patch.items():
            if section not in result or not isinstance(values, dict):
                raise ValueError(f'Unsupported scenario section: {section}')
            unknown = set(values) - set(result[section])
            if unknown:
                raise ValueError(f'Unknown {section} keys: {sorted(unknown)}')
            result[section].update(values)
    p = result['physics']
    for key in ('fps', 'duration_sec', 'substeps_per_frame', 'ball_mass', 'ball_radius', 'ball_initial_speed'):
        if not math.isfinite(float(p[key])) or p[key] <= 0:
            raise ValueError(f'{key} must be positive and finite')
    for key in ('ball_restitution', 'floor_restitution', 'wall_restitution'):
        if not 0 <= p[key] <= 1:
            raise ValueError(f'{key} must be in [0, 1]')
    for key in ('ball_friction', 'ball_rolling_friction', 'ball_spinning_friction', 'floor_friction', 'floor_rolling_friction', 'wall_friction', 'linear_damping', 'angular_damping'):
        if not math.isfinite(float(p[key])) or p[key] < 0:
            raise ValueError(f'{key} must be nonnegative and finite')
    if len(p['room_size']) != 3 or min(p['room_size']) <= 0:
        raise ValueError('room_size must contain three positive dimensions')
    if len(p['launch_direction_xy']) != 2 or math.hypot(*p['launch_direction_xy']) == 0:
        raise ValueError('Nonzero launch_direction_xy required')
    if len(p['ball_initial_location_xy']) != 2 or any(not p['ball_radius'] < v < extent-p['ball_radius'] for v, extent in zip(p['ball_initial_location_xy'], p['room_size'])):
        raise ValueError('Ball starts outside the room or intersects a wall')
    if 2*p['ball_radius'] >= p['room_size'][2]:
        raise ValueError('Ball must fit below the ceiling')
    return result

def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')

def runtime(kind):
    relative = 'render/Scripts/python.exe' if kind == 'render' else 'sim/python.exe'
    for root in (ROOT, ROOT.parent / 'PCVE-ElasticBench'):
        path = root / '.runtime' / relative
        if path.is_file():
            return str(path)
    raise FileNotFoundError(f'No {kind} Python runtime; use an environment with bpy/pybullet')

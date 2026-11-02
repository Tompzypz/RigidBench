"""Reject trajectories made with different geometry, dynamics or timing.

The cache is the only thing the renderer and the suite re-use across runs, so
it has to be able to prove it belongs to the current code. The signature covers
the simulator implementation, the geometry module, this file, the four physics
parameters and the sampling clock; the object metadata is compared field by
field as a second line of defence.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import hashlib, json
from pathlib import Path
from scene_geometry import (
    BOB_CENTER_Z, BOB_RADIUS, BOX_SIZE, BOX_START_X, PENDULUM_LENGTH, PIVOT,
    TABLE_Z, moving_objects)

def _scene_directory():
    scripts_root = _PCVE_ROOT / 'scripts'
    for candidate in (scripts_root / "rigid_rigid" / "pendulum_box_collision", scripts_root / "pendulum_box_collision"):
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("Scene directory not found for pendulum_box_collision")


CACHE_SCHEMA_VERSION = 3


def geometry_metadata():
    return dict(box_size=list(BOX_SIZE), box_start_x=BOX_START_X, table_z=TABLE_Z,
                bob_radius=BOB_RADIUS, pendulum_length=PENDULUM_LENGTH,
                pivot=list(PIVOT), bob_center_z=BOB_CENTER_Z)


def simulation_signature(scenario):
    import hashlib, json
    scene_dir = _PCVE_SCENE_ROOT
    common_dir = _PCVE_ROOT / "scripts"
    files = [p for sub in (scene_dir, scene_dir / "physics", scene_dir / "appearance")
             for p in sub.glob("*.py")] + list(common_dir.glob("*.py"))
    implementation = {str(path.relative_to(_PCVE_ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in files if path.is_file()}
    payload = dict(implementation=implementation, scenario=scenario)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False, default=str).encode()).hexdigest()
def validate_cache(data, scenario=None):
    error = 'Incompatible physics cache: geometry, dynamics or timing changed; resimulate first.'
    if data.get('scene') != 'pendulum_box_collision' or data.get('schema_version') != CACHE_SCHEMA_VERSION:
        raise ValueError(error)
    requested = scenario if scenario is not None else data['scenario']
    if data.get('simulation_signature') != simulation_signature(requested):
        raise ValueError(error)
    if data.get('geometry') != geometry_metadata() or data.get('objects') != moving_objects(requested['physics']):
        raise ValueError(error)
    r = requested['render']; count = round(r['fps'] * r['slow_motion'] * r['duration_sec'])
    if (data.get('playback_fps') != r['fps'] or data.get('slow_motion') != r['slow_motion']
            or data.get('physical_duration_sec') != r['duration_sec'] or data.get('frame_end') != count
            or len(data.get('frames', [])) != count or data['scenario']['physics'] != requested['physics']):
        raise ValueError(error)
    if not data.get('quality', {}).get('valid'):
        raise ValueError('Invalid physics cache')

"""Reject caches from changed physics, geometry, timing or solver code."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import hashlib
import json
from pathlib import Path
from scene_config import validate
from scene_geometry import fixed_constants, KEYS

from runtime_support import HERE, ROOT

def simulation_signature(s):
    import hashlib, json
    scene_dir = _PCVE_SCENE_ROOT
    common_dir = _PCVE_ROOT / "scripts"
    files = [p for sub in (scene_dir, scene_dir / "physics", scene_dir / "appearance")
             for p in sub.glob("*.py")] + list(common_dir.glob("*.py"))
    implementation = {str(path.relative_to(_PCVE_ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in files if path.is_file()}
    payload = dict(implementation=implementation, scenario=s)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False, default=str).encode()).hexdigest()
def validate_cache(data):
    validate(data['scenario'])
    if data.get('scene') != 'twin_pendulum_collision' or data.get('schema_version') != 2:
        raise ValueError('Wrong scene/cache schema')
    if data.get('simulation_signature') != simulation_signature(data['scenario']):
        raise ValueError('Stale physics cache; resimulate with the current solver')
    if set(data['objects']) != set(KEYS) or not data['quality']['valid']:
        raise ValueError('Invalid cached simulation')
    r = data['scenario']['render']
    count = round(r['fps'] * r['slow_motion'] * r['duration_sec'])
    if data['frame_end'] != count or len(data['frames']) != count:
        raise ValueError('Incomplete physics cache')

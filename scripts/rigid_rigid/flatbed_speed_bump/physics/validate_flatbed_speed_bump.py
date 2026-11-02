"""Compatibility contract for flatbed trajectories and renderer replays."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import hashlib,json
from pathlib import Path
def _scene_directory():
    scripts_root = _PCVE_ROOT / 'scripts'
    for candidate in (scripts_root / "rigid_rigid" / "flatbed_speed_bump", scripts_root / "flatbed_speed_bump"):
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("Scene directory not found for flatbed_speed_bump")


CACHE_SCHEMA_VERSION=4

def signature(parameters):
    import hashlib, json
    scene_dir = _PCVE_SCENE_ROOT
    common_dir = _PCVE_ROOT / "scripts"
    files = [p for sub in (scene_dir, scene_dir / "physics", scene_dir / "appearance")
             for p in sub.glob("*.py")] + list(common_dir.glob("*.py"))
    implementation = {str(path.relative_to(_PCVE_ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in files if path.is_file()}
    payload = dict(implementation=implementation, scenario=parameters)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False, default=str).encode()).hexdigest()
def validate_cache(data,requested=None):
    message='Incompatible flatbed physics cache: parameters, geometry or implementation changed; resimulate first.'
    if data.get('schema_version')!=CACHE_SCHEMA_VERSION or data.get('scene')!='flatbed_speed_bump':raise ValueError(message)
    params=data.get('simulation_parameters',{})
    if data.get('simulation_signature')!=signature(params):raise ValueError(message)
    for name,value in (requested or {}).items():
        if value is not None and params.get(name)!=value:raise ValueError(message+' Mismatch: '+name)
    count=max(2,round(params['fps']*params['duration_sec']))
    if data.get('fps')!=params['fps'] or data.get('duration_sec')!=params['duration_sec'] or data.get('frame_end')!=count or len(data.get('frames',[]))!=count:raise ValueError(message)
    for name,value in data['physics_parameters'].items():
        if name in params and value!=params[name]:raise ValueError(message)

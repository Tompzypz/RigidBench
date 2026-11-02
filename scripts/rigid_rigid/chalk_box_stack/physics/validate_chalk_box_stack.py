"""Reject trajectories made with different geometry, dynamics or timing."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import hashlib,json
from pathlib import Path
from scene_geometry import BOX_SIZE,ERASER_SIZE,COUNT,TABLE_Z,moving_objects

CACHE_SCHEMA_VERSION=3

def geometry_metadata():
    return dict(box_size=list(BOX_SIZE),eraser_size=list(ERASER_SIZE),count=COUNT,table_z=TABLE_Z)

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
def validate_cache(data,scenario=None):
    from scene_config import validate
    error='Incompatible physics cache: geometry, dynamics or timing changed; resimulate first.'
    if data.get('scene')!='chalk_box_stack' or data.get('schema_version')!=CACHE_SCHEMA_VERSION:
        raise ValueError(error)
    requested=scenario if scenario is not None else data['scenario']
    validate(requested)
    if data.get('simulation_signature')!=simulation_signature(requested):raise ValueError(error)
    if data.get('geometry')!=geometry_metadata() or data.get('objects')!=moving_objects(requested['physics']):
        raise ValueError(error)
    r=requested['render'];count=round(r['fps']*r['duration_sec'])
    if (data.get('playback_fps')!=r['fps'] or data.get('slow_motion')!=r['slow_motion']
        or data.get('physical_duration_sec')!=r['duration_sec'] or data.get('frame_end')!=count
        or len(data.get('frames',[]))!=count or data['scenario']['physics']!=requested['physics']):
        raise ValueError(error)
    if not data.get('quality',{}).get('valid'):raise ValueError('Invalid physics cache')

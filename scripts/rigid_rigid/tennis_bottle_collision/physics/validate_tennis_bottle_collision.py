from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import hashlib,json,math
from pathlib import Path
from scene_config import validate,SCENE_NAME
from scene_geometry import KEYS,present

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
def validate_cache(d):
 validate(d['scenario'])
 if d.get('simulation_signature')!=simulation_signature(d['scenario']):raise ValueError('Stale physics cache: resimulate')
 if d['scene']!=SCENE_NAME or len(d['frames'])!=d['frame_end'] or d['frame_end']!=4*d['playback_fps']:raise ValueError('Wrong frame count')
 if not d['quality']['valid']:raise ValueError('Invalid physical trace')
 for i,f in enumerate(d['frames']):
  if f['frame_index']!=i+1 or abs(f['time_sec']-i/d['sample_fps'])>1e-9:raise ValueError('Frame clock')
  for k in KEYS:
   active=present(d['scenario']['physics'],k)
   if f[k]['present']!=active or d['objects'][k]['present']!=active:raise ValueError('Presence mismatch')
   if not active:
    if f[k]!={'present':False}:raise ValueError('Ghost transform')
   elif not all(math.isfinite(v) for row in f[k]['matrix_world'] for v in row):raise ValueError('Nonfinite matrix')

"""Fingerprint solver, fixed geometry, initial conditions, and sampling clock."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import hashlib
import json
import math
from pathlib import Path
from scene_config import validate, SCENE_NAME
from scene_geometry import fixed_constants,KEYS

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

def _absent_from_frame(physics, index):
    """The frame a timed edit removes this body from (None if it never leaves).

    A whole-clip delete is a ``ball_active`` flag in the baseline itself; a
    timed delete ships the flag change in the schedule instead, and presence
    switches at the top of that frame.
    """
    frame = None
    for entry in physics.get('timed_edits') or []:
        params = entry.get('params') if isinstance(entry, dict) else None
        flags = params.get('ball_active') if isinstance(params, dict) else None
        if flags is not None and not flags[index]:
            candidate = int(entry['frame'])
            frame = candidate if frame is None else min(frame, candidate)
    return frame

def validate_cache(d):
    validate(d['scenario'])
    if d.get('scene') != SCENE_NAME or d.get('schema_version') != 2: raise ValueError('Wrong cache scene/schema')
    if d.get('simulation_signature') != simulation_signature(d['scenario']): raise ValueError('Stale cache; resimulate')
    r=d['scenario']['render']; count=round(r['fps']*r['slow_motion']*r['duration_sec'])
    if d['frame_end'] != count or len(d['frames']) != count or set(d['objects']) != set(KEYS): raise ValueError('Incomplete cache')
    if not d['quality']['valid']: raise ValueError('Invalid physical trace')
    ph=d['scenario']['physics']
    for i,f in enumerate(d['frames']):
        if f['frame_index'] != i+1 or abs(f['time_sec']-i/d['sample_fps']) > 1e-9: raise ValueError('Bad frame clock')
        for key in KEYS:
            state=f[key]
            index=KEYS.index(key)
            # Whole-clip presence comes from the baseline flag; a timed delete
            # switches it off from the top of its frame onwards.
            absent_from=_absent_from_frame(ph, index)
            expected=bool(ph['ball_active'][index]) and (absent_from is None or f['frame_index'] < absent_from)
            if state.get('present') is not expected:
                raise ValueError('Presence differs between scenario, timed schedule and frames')
            if d['objects'][key].get('present') is not bool(ph['ball_active'][index]):
                raise ValueError('Presence differs between scenario and objects')
            if not expected:
                if any(state.get(field) is not None for field in ('location','quaternion_xyzw','linear_velocity','angular_velocity','matrix_world')): raise ValueError('Deleted object must have null transforms and velocities')
                continue
            if not all(math.isfinite(v) for row in state['matrix_world'] for v in row): raise ValueError('Nonfinite transform')

"""Locate the project's existing runtime without modifying sibling scenes."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import sys
from pathlib import Path

ROOT = _PCVE_ROOT
HERE = _PCVE_SCENE_ROOT

from pcve_scene_runtime import python_for, render_prefix, append_render_options, parse_render_args, run_renderer


def implementation_hashes(directory):
    import hashlib
    paths = list(Path(directory).glob('*.py'))
    paths += [ROOT / 'scripts' / name for name in
              ('pcve_scene_runtime.py', 'pcve_blender_compat.py', 'pcve_edit_dsl.py')]
    paths += [ROOT / 'assets/polyhaven/newtons_cradle' / name for name in
              ('render_quality.py', 'look_twin_pendulum_collision.py')]
    paths += list((ROOT / 'assets/polyhaven/newtons_cradle').glob('*'))
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in paths if p.is_file()}

"""Use the established project runtime and compatibility utilities."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import sys
from pathlib import Path
import hashlib

ROOT=_PCVE_ROOT
HERE = _PCVE_SCENE_ROOT

from pcve_scene_runtime import python_for,render_prefix,append_render_options,parse_render_args,run_renderer


def implementation_hashes(directory):
    files=list(Path(directory).glob('*.py'))
    files += [ROOT/'scripts'/n for n in ('pcve_scene_runtime.py','pcve_blender_compat.py','pcve_edit_dsl.py')]
    files += [ROOT/'scripts/pcve_render_quality.py']
    files += [(ROOT/'assets/models'/n) for n in ('modern_kitchen.glb','bowl_and_chops.glb','pepsi_tin_with_texture.glb')]
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()}

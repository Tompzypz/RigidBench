"""Use repository runtimes without changing existing scenes."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import sys
from pathlib import Path
ROOT=_PCVE_ROOT
HERE = _PCVE_SCENE_ROOT

from pcve_scene_runtime import python_for,render_prefix,parse_render_args,run_renderer

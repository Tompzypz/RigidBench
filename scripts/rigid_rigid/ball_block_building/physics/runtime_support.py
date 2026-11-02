"""Local runtime discovery; scripts also work in ordinary Python/Blender installs."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import os,sys
from pathlib import Path

ROOT=_PCVE_ROOT
_dll_handles=[]
if os.name=='nt':
    directory=Path(sys.prefix)/'Library/bin'
    if directory.exists():_dll_handles.append(os.add_dll_directory(str(directory)))

def python_for(role):
    sys.path.insert(0, str(ROOT/'scripts'))
    from pcve_scene_runtime import python_for as resolve_python
    return resolve_python(role)

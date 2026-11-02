"""Generate reproducible parameter variants, each with all five edits."""
# PCVE_UNIFIED_ENTRY_BEGIN

# Resolve the shared scripts directory, then this scene's module folders.
import sys as _clean_sys
from pathlib import Path as _CleanPath
_clean_scene_dir = _CleanPath(__file__).resolve().parents[1]
_scripts_dir = _clean_scene_dir.parents[1]
_PCVE_PROJECT_ROOT = next(p for p in _clean_scene_dir.parents if (p / "assets").is_dir())
if str(_scripts_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_scripts_dir))
if str(_clean_scene_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_clean_scene_dir))
# Shared modules live in scripts/; scene-local modules live in this directory and
# its physics/, appearance/ and tools/ subdirectories.
for _scene_sub in ("", "physics", "appearance", "tools"):
    _scene_sub_dir = _clean_scene_dir / _scene_sub if _scene_sub else _clean_scene_dir
    if _scene_sub_dir.is_dir() and str(_scene_sub_dir) not in _clean_sys.path:
        _clean_sys.path.insert(1, str(_scene_sub_dir))
# PCVE_UNIFIED_ENTRY_END


import argparse,json,random,subprocess,sys
from pathlib import Path
from scene_config import defaults
from runtime_support import ROOT

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--count',type=int,default=3);p.add_argument('--seed',type=int,default=0)
 p.add_argument('--out-root',type=Path,default=ROOT/'renders/tennis_bottle_batch');p.add_argument('--simulate-only',action='store_true');a=p.parse_args()
 if a.count<1:raise ValueError('count')
 rng=random.Random(a.seed)
 for i in range(a.count):
  folder=a.out_root/f'sample_{i:03d}';folder.mkdir(parents=True,exist_ok=True);s=defaults();s['seed']=a.seed+i
  s['physics'].update(initial_velocity=rng.uniform(.75,.95),bottle_mass=.026)
  file=folder/'scenario.json';file.write_text(json.dumps(s,indent=2),encoding='utf-8')
  cmd=[sys.executable,str(Path(__file__).with_name('build_pcve_tennis_bottle_collision.py')),'--out-root',str(folder),'--scenario-json',str(file)]
  if a.simulate_only:cmd+=['--simulate-only']
  subprocess.run(cmd,check=True)
if __name__=='__main__':main()

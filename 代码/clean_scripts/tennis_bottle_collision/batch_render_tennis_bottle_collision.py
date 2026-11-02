"""Generate reproducible parameter variants, each with all five edits."""

# Load this seven-file scene bundle and the reference common scripts.
import sys as _clean_sys
from pathlib import Path as _CleanPath
_clean_scene_dir = _CleanPath(__file__).resolve().parent
_clean_scripts_dir = _clean_scene_dir.parent
_PCVE_PROJECT_ROOT = next(p for p in _clean_scene_dir.parents if (p / "assets").is_dir())
if str(_clean_scripts_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_clean_scripts_dir))
if str(_clean_scene_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_clean_scene_dir))
import edit_vocab as _clean_scene_bundle
_clean_scene_bundle.install_scene_support()


import argparse,json,random,subprocess,sys
from pathlib import Path
from tennis_bottle_collision.scene_config import defaults
from tennis_bottle_collision.runtime_support import ROOT

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

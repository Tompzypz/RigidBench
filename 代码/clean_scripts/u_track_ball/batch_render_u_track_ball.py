
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




from pathlib import Path
import argparse,random,sys,json
from u_track_ball.build_pcve_u_track_ball import parser,run_case,save,ROOT
from scene_support.u_track_ball.scene_config import defaults

def main():
    p=parser();p.set_defaults(out_root=ROOT/'renders/batch_u_track_ball');p.add_argument('--count',type=int,default=4);p.add_argument('--start-index',type=int,default=0);p.add_argument('--seed-base',type=int,default=6100)
    args=p.parse_args();manifest=dict(schema_version=1,scene='u_track_ball',start_index=args.start_index,seed_base=args.seed_base,samples=[])
    if args.count<1 or args.start_index<0:raise ValueError('Count must be positive and start index nonnegative')
    if args.cases:raise ValueError('Use the suite builder for named edit cases')
    if args.simulate_only and args.render_only:raise ValueError('Conflicting modes')
    for offset in range(args.count):
        index=args.start_index+offset;seed=args.seed_base+index;rng=random.Random(seed);s=defaults();s['seed']=seed
        s['physics'].update(friction=rng.uniform(.03,.8),initial_speed=rng.uniform(0,1.2),initial_position=rng.uniform(-.88,-.45))
        s['render'].update(fps=args.fps,duration_sec=args.duration_sec,slow_motion=args.slow_motion,resolution=args.resolution,samples=args.samples)
        folder=args.out_root.resolve()/f'sample_{index:04d}';result=run_case(folder,s,args)
        manifest['samples'].append(dict(sample_index=index,seed=seed,case_dir=str(folder.resolve()),**result));save(args.out_root/'batch_manifest.json',manifest)

if __name__=='__main__':main()

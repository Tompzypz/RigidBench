"""Random draws over the four editable parameters, reproducible from the seed.

The ranges are narrower than ``scene_config.PHYSICS_LIMITS`` on purpose. The
limits are what the staging can survive -- a bob speed above 0.9 m/s raises the
bob's centre to the top of the slider, a slider below 1.12 m/s is still crossing
the bench when the clip ends -- while a batch wants draws that also land in
"reads as a school-lab impact" territory rather than at the extremes of the
contract.
"""
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




from pathlib import Path
import random, sys
from build_pcve_pendulum_box_collision import parser, run_case, write_json, ROOT
from scene_config import defaults

BOB_MASS = (.15, 1.00)
BOB_SPEED = (.20, .88)
BOX_MASS = (.20, 1.00)
BOX_SPEED = (1.15, 1.95)


def main():
    p = parser()
    p.set_defaults(out_root=ROOT / 'renders/batch_pendulum_box')
    p.add_argument('--count', type=int, default=4)
    p.add_argument('--start-index', type=int, default=0)
    p.add_argument('--seed-base', type=int, default=9700)
    args = p.parse_args()
    args.out_root = args.out_root.resolve()
    if args.count < 1 or args.start_index < 0 or args.cases or (args.simulate_only and args.render_only):
        raise ValueError('Invalid batch options')
    manifest = dict(schema_version=1, scene='pendulum_box_collision', start_index=args.start_index,
                    seed_base=args.seed_base, ranges=dict(bob_mass=list(BOB_MASS), bob_speed=list(BOB_SPEED),
                                                          box_mass=list(BOX_MASS), box_speed=list(BOX_SPEED)),
                    samples=[])
    for offset in range(args.count):
        index = args.start_index + offset
        seed = args.seed_base + index
        rng = random.Random(seed)
        s = defaults()
        s['seed'] = seed
        s['physics'].update(bob_mass=rng.uniform(*BOB_MASS), bob_speed=rng.uniform(*BOB_SPEED),
                            box_mass=rng.uniform(*BOX_MASS), box_speed=rng.uniform(*BOX_SPEED))
        s['render'].update(fps=args.fps, duration_sec=args.duration_sec, slow_motion=args.slow_motion,
                           resolution=args.resolution, samples=args.samples)
        folder = args.out_root / f'sample_{index:04d}'
        result = run_case(folder, s, args)
        manifest['samples'].append(dict(sample_index=index, seed=seed, physics=s['physics'],
                                        case_dir=str(folder.resolve()), **result))
        if not args.dry_run:
            write_json(args.out_root / 'batch_manifest.json', manifest)


if __name__ == '__main__':
    main()


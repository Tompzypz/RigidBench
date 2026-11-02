"""Deterministic random sampling of the same three editable parameters."""

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


import random
from pathlib import Path
import sys
from build_pcve_twin_pendulum_collision import parser, run_case, write_json, outputs, ROOT
from twin_pendulum_collision.scene_config import defaults


def main():
    p = parser()
    p.set_defaults(out_root=ROOT / 'renders/batch_twin_pendulum_collision')
    p.add_argument('--count', type=int, default=4)
    p.add_argument('--start-index', type=int, default=0)
    p.add_argument('--seed-base', type=int, default=10400)
    args = p.parse_args()
    args.out_root = args.out_root.resolve()
    if args.count < 1 or args.start_index < 0 or args.cases or (args.simulate_only and args.render_only):
        raise ValueError('Invalid batch options')
    manifest = dict(schema_version=1, scene='twin_pendulum_collision', seed_base=args.seed_base,
                    start_index=args.start_index, samples=[])
    for offset in range(args.count):
        index = args.start_index + offset
        seed = args.seed_base + index
        rng = random.Random(seed)
        scenario = defaults()
        scenario['seed'] = seed
        scenario['physics'].update(driver_mass=rng.uniform(.13, .52), initial_angle_deg=rng.uniform(16, 48),
                                   drag_coefficient=rng.uniform(.0015, .048))
        scenario['render'].update(fps=args.fps, duration_sec=args.duration_sec, slow_motion=args.slow_motion,
                                  resolution=args.resolution, samples=args.samples)
        folder = args.out_root / f'sample_{index:04d}'
        result = run_case(folder, scenario, args)
        manifest['samples'].append(dict(sample_index=index, seed=seed, case_dir=str(folder), outputs=outputs(folder), **result))
        write_json(args.out_root / 'batch_manifest.json', manifest)


if __name__ == '__main__':
    main()

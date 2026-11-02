"""Generate seeded samples of the three supported parameters."""
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


import argparse
import copy
from pathlib import Path
import random
import subprocess
import sys

HERE = Path(__file__).resolve().parent
import scene_config
from simulate_door_basketball_collision import simulate


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out-root', type=Path, required=True)
    p.add_argument('--count', type=int, default=3)
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--simulate-only', action='store_true')
    p.add_argument('--render-python', type=Path, default=HERE.parents[1] / '.runtime/render/Scripts/python.exe')
    p.add_argument('--samples', type=int, default=16)
    args = p.parse_args()
    if args.count < 1:
        p.error('--count must be positive')
    rng = random.Random(args.seed)
    manifest = dict(scene='door_basketball_collision', seed=args.seed, samples=[])
    for index in range(args.count):
        scenario = copy.deepcopy(scene_config.load_scenario())
        edits = dict(door_initial_velocity=round(rng.uniform(1.35, 1.85), 4),
                     door_mass=round(rng.uniform(6, 10), 4), ball_mass=round(rng.uniform(.45, .85), 4))
        scenario['physics'].update(edits)
        folder = args.out_root.resolve() / f'sample_{index:04d}'
        scene_config.write_json(folder / 'scenario_input.json', scenario)
        scene_config.write_json(folder / 'scenario_overrides.json', {'physics': edits})
        data = simulate(scenario, fps=24, duration_sec=4, substeps=60, leaf_path=folder / 'door_leaf.json')
        scene_config.write_json(folder / 'physics_transforms.json', data)
        scene_config.write_json(folder / 'simulation_metrics.json', data['quality'])
        if not data['quality']['transmission_observed']:
            raise RuntimeError('Sample did not produce a collision')
        if not args.simulate_only:
            subprocess.run([str(args.render_python), str(HERE / 'render_door_basketball_collision.py'),
                            '--scenario', str(folder / 'scenario_input.json'), '--out-dir', str(folder),
                            '--mode', 'keyframes', '--samples', str(args.samples), '--device', 'cpu'], check=True)
        manifest['samples'].append(dict(index=index, physics_edits=edits, quality=data['quality'], path=str(folder)))
        scene_config.write_json(args.out_root / 'batch_manifest.json', manifest)


if __name__ == '__main__':
    main()

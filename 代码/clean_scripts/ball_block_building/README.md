# Ball Block Building (rigid_rigid)

## Scene files

| File | Role |
| --- | --- |
| `simulate_ball_block_building.py` | PyBullet rigid-body simulation |
| `render_ball_block_building.py` | Blender scene construction and rendering |
| `build_pcve_ball_block_building.py` | PCVE source/edit suite builder |
| `batch_render_ball_block_building.py` | Batch rendering entry point |
| `edit_vocab.py` | Declared editable physical parameters |
| `entrypoints.json` | Entry-point and native option manifest |
| `README.md` | Run instructions and scene notes |

The scene package contains exactly these seven files. Its scene-specific implementation is included in the Python entrypoints. Common CLI/edit utilities are in `clean_scripts/`; model, texture and scenario assets are loaded from repository-level `assets/`.

## Edit suite

The suite contains one baseline and exactly five edits:

1. Double the ball mass.
2. Increase the ball's initial velocity by a factor of 1.5.
3. Reduce the blocks' friction to 0.4 times baseline; this kept the stack on the tabletop while remaining visibly different from baseline.
4. Delete `block_01` (the top block).
5. Increase gravity to 1.5 times baseline at frame 12; the simulator applies the event while advancing the physical trajectory.

`entrypoints.json` lists the same five case IDs used by the builder manifest. Deleted bodies are absent from both simulation and rendering, and frame-level presence is recorded in physics and render ground truth.

## Run

From the repository root, use the configured Python and Blender Python environments:

```powershell
& .runtime/sim/python.exe clean_scripts/ball_block_building/simulate_ball_block_building.py --help
& .runtime/render/Scripts/python.exe clean_scripts/ball_block_building/render_ball_block_building.py --help
& .runtime/sim/python.exe clean_scripts/ball_block_building/build_pcve_ball_block_building.py --dry-run --out-root renders/ball_block_building_suite
```

## Dependencies

The scene reads shared assets from `assets/`. Scene-specific Python implementation is contained in this folder; shared interfaces and edit utilities are listed in `entrypoints.json`.

# Uneven Ground Ball (rigid_rigid)

## Scene files

| File | Role |
| --- | --- |
| `simulate_uneven_ground_ball.py` | PyBullet rigid-body simulation |
| `render_uneven_ground_ball.py` | Blender scene construction and rendering |
| `build_pcve_uneven_ground_ball.py` | PCVE source/edit suite builder |
| `batch_render_uneven_ground_ball.py` | Batch rendering entry point |
| `edit_vocab.py` | Declared editable physical parameters |
| `entrypoints.json` | Entry-point and native option manifest |
| `README.md` | Run instructions and scene notes |

The scene package contains exactly these seven files. Its scene-specific implementation is included in the Python entrypoints. Common CLI/edit utilities are in `clean_scripts/`; model, texture and scenario assets are loaded from repository-level `assets/`.

## Run

From the repository root, use the configured Python and Blender Python environments:

```powershell
& .runtime/sim/python.exe clean_scripts/uneven_ground_ball/simulate_uneven_ground_ball.py --help
& .runtime/render/Scripts/python.exe clean_scripts/uneven_ground_ball/render_uneven_ground_ball.py --help
& .runtime/sim/python.exe clean_scripts/uneven_ground_ball/build_pcve_uneven_ground_ball.py --dry-run --out-root renders/uneven_ground_ball_suite
```

## Dependencies

The scene reads shared assets from `assets/`. Scene-specific Python implementation is contained in this folder; shared interfaces and edit utilities are listed in `entrypoints.json`.

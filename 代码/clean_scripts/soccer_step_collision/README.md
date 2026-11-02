# Soccer Step Collision (rigid_rigid)

## Scene files

| File | Role |
| --- | --- |
| `simulate_soccer_step_collision.py` | PyBullet rigid-body simulation |
| `render_soccer_step_collision.py` | Blender scene construction and rendering |
| `build_pcve_soccer_step_collision.py` | PCVE source/edit suite builder |
| `batch_render_soccer_step_collision.py` | Batch rendering entry point |
| `edit_vocab.py` | Declared editable physical parameters |
| `entrypoints.json` | Entry-point and native option manifest |
| `README.md` | Run instructions and scene notes |

The scene package contains exactly these seven files. Its scene-specific implementation is included in the Python entrypoints. Common CLI/edit utilities are in `clean_scripts/`; model, texture and scenario assets are loaded from repository-level `assets/`.

## Run

From the repository root, use the configured Python and Blender Python environments:

```powershell
& .runtime/sim/python.exe clean_scripts/soccer_step_collision/simulate_soccer_step_collision.py --help
& .runtime/render/Scripts/python.exe clean_scripts/soccer_step_collision/render_soccer_step_collision.py --help
& .runtime/sim/python.exe clean_scripts/soccer_step_collision/build_pcve_soccer_step_collision.py --dry-run --out-root renders/soccer_step_collision_suite
```

## Dependencies

The scene reads shared assets from `assets/`. Scene-specific Python implementation is contained in this folder; shared interfaces and edit utilities are listed in `entrypoints.json`.

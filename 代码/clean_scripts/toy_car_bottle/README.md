# Toy Car Bottle (rigid_rigid)

## Entry points

| File | Role |
| --- | --- |
| `simulate_toy_car_bottle.py` | PyBullet rigid-body simulation |
| `render_toy_car_bottle.py` | Blender scene construction and rendering |
| `build_pcve_toy_car_bottle.py` | Source/edit suite builder |
| `batch_render_toy_car_bottle.py` | Randomized batch runner |
| `edit_vocab.py` | Declared physical edits and scene descriptions |
| `entrypoints.json` | Entry-point and native option manifest |

The scene folder contains exactly these seven files. The physics and scene-specific rendering implementation live in the Python entrypoints. Shared command-line/edit utilities are in `clean_scripts/`; models, textures and scenario data are read from the repository `assets/` directory.

The source case has no second bottle. The suite contains exactly five edits: multiply the original bottle's mass by 4; multiply the car's initial velocity by 1.5; multiply the bottle's friction by 0.25; add a second bottle upright on the shared action plane at the car/original-bottle midpoint, using its own PyBullet collider, rendered model and frame-by-frame presence label; and multiply the car's running speed by 1.5 at frame 5. The timed speed edit occurs after the car has started moving and changes its velocity without teleporting it. Timed events are validated against the simulated frame range and allowed physics fields, with before/after values recorded in `physics_transforms.json`.

## Run

From the repository root, use the configured runtimes:

```powershell
# Simulate
& .runtime/sim/python.exe clean_scripts/toy_car_bottle/simulate_toy_car_bottle.py `
    --out renders/toy_car_bottle/physics_transforms.json

# Render a low-cost preview
& .runtime/render/Scripts/python.exe clean_scripts/toy_car_bottle/render_toy_car_bottle.py `
    --mode preview --preview-frame 18 --resolution 320 180 --samples 1 --device cpu

# Plan the full source/edit suite without rendering
& .runtime/sim/python.exe clean_scripts/toy_car_bottle/build_pcve_toy_car_bottle.py `
    --dry-run --out-root renders/toy_car_bottle_suite

# Build and render the full suite
& .runtime/sim/python.exe clean_scripts/toy_car_bottle/build_pcve_toy_car_bottle.py `
    --out-root renders/toy_car_bottle_suite
```

## Assets

The scene reads its baseline configuration from `assets/scenarios/toy_car_bottle/scenario.json`. It imports `futuristic_room.glb`, `hotwheels_technetium__www.vecarz.com.glb`, and `plastic_water_bottle.glb` from `assets/models/`. `--models-dir` can point to another directory containing those models.

The simulator uses a box-shaped car body and one or two convex bottle colliders, depending on the case. Wheel rotation is added only to the rendered car; it does not alter the simulated contacts.

# Toy Car Bottle (rigid_rigid)

## 目录结构

按 PCVE-Bench 的 `scripts/<category>/<scene>/` 布局整理：场景实现内核（物理、几何、外观、编辑词表、案例集合）与 `clean_scripts` 版本逐字一致，只把原先内嵌在 `edit_vocab.py` 里的源码 bundle 展开为真实模块文件，并按职责分到 `physics/`、`appearance/`、`tools/` 三个子目录。

```
toy_car_bottle/
  simulate_toy_car_bottle.py            PyBullet 求解（公开入口）
  render_toy_car_bottle.py              Blender 回放与渲染（公开入口）
  build_pcve_toy_car_bottle.py          source + 编辑案例套件构建（公开入口）
  scene_config.py           物理/相机/渲染默认值与校验的唯一来源
  edit_vocab.py             编辑 DSL 词表、案例列表与 prompt
  entrypoints.json  scene_manifest.json  README.md  requirements.txt
  tools/        audit_toy_car_bottle.py  render_queue.py
```

`physics/` 放求解侧与几何模块，`appearance/` 放只依赖 Blender 的外观层，`tools/` 放不在正式链路里的独立脚本。三个入口的 `PCVE_UNIFIED_ENTRY_BEGIN` 段落把这四个目录和共享的 `scripts/` 一起挂到 `sys.path`，所以模块可以直接按扁平名字 import。

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

## Assets

The scene reads its baseline configuration from `assets/scenarios/toy_car_bottle/scenario.json`. It imports `futuristic_room.glb`, `hotwheels_technetium__www.vecarz.com.glb`, and `plastic_water_bottle.glb` from `assets/models/`. `--models-dir` can point to another directory containing those models.

The simulator uses a box-shaped car body and one or two convex bottle colliders, depending on the case. Wheel rotation is added only to the rendered car; it does not alter the simulated contacts.

## 运行

在仓库根目录执行（`--out-root` 由各入口的 argparse 决定默认值，显式传入即可）：

```bash
python scripts/rigid_rigid/toy_car_bottle/simulate_toy_car_bottle.py --out <case>/physics_transforms.json
python scripts/rigid_rigid/toy_car_bottle/build_pcve_toy_car_bottle.py --out-root <suite> --simulate-only
python scripts/rigid_rigid/toy_car_bottle/build_pcve_toy_car_bottle.py --out-root <suite> --mode animation
python scripts/rigid_rigid/toy_car_bottle/tools/audit_toy_car_bottle.py --out-root <suite>
```

渲染阶段需要 Blender（`--blender` 或 `--render-python` 指定）；求解阶段需要 `requirements.txt` 里的 PyBullet。共享工具 `scripts/pcve_scene_runtime.py` 会自动探测 `--physics-python` / `--render-python`。

## 依赖

- Python：见 `requirements.txt`；Blender 4.x 的 `bpy` 由渲染环境自带，不是 pip 依赖。
- 资产：模型 `assets/models/`，贴图与 HDRI `assets/polyhaven/toy_car_bottle/`，场景配方 `assets/scenarios/`。
- 共享代码：`scripts/pcve_edit_dsl.py`、`scripts/pcve_scene_runtime.py`、`scripts/pcve_project_paths.py`、`scripts/pcve_blender_compat.py`、`scripts/pcve_render_quality.py`、`scripts/pcve_legacy_scene.py`。

## 案例

| case |
| --- |
| `toy_car_bottle_baseline` |
| `edit_heavy_bottle` |
| `edit_fast_car` |
| `edit_slippery_bottle` |
| `edit_add_midpoint_bottle` |
| `edit_fast_car_midflight` |

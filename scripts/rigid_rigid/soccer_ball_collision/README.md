# Soccer Ball Collision (rigid_rigid)

## 目录结构

按 PCVE-Bench 的 `scripts/<category>/<scene>/` 布局整理：场景实现内核（物理、几何、外观、编辑词表、案例集合）与 `clean_scripts` 版本逐字一致，只把原先内嵌在 `edit_vocab.py` 里的源码 bundle 展开为真实模块文件，并按职责分到 `physics/`、`appearance/`、`tools/` 三个子目录。

```
soccer_ball_collision/
  simulate_soccer_ball_collision.py            PyBullet 求解（公开入口）
  render_soccer_ball_collision.py              Blender 回放与渲染（公开入口）
  build_pcve_soccer_ball_collision.py          source + 编辑案例套件构建（公开入口）
  scene_config.py           物理/相机/渲染默认值与校验的唯一来源
  edit_vocab.py             编辑 DSL 词表、案例列表与 prompt
  entrypoints.json  scene_manifest.json  README.md  requirements.txt
  physics/      runtime_support.py  scene_geometry.py  validate_soccer_ball_collision.py
  appearance/   look_soccer_ball_collision.py
  tools/        audit_soccer_ball_collision.py  render_queue.py
```

`physics/` 放求解侧与几何模块，`appearance/` 放只依赖 Blender 的外观层，`tools/` 放不在正式链路里的独立脚本。三个入口的 `PCVE_UNIFIED_ENTRY_BEGIN` 段落把这四个目录和共享的 `scripts/` 一起挂到 `sys.path`，所以模块可以直接按扁平名字 import。

## 运行

在仓库根目录执行（`--out-root` 由各入口的 argparse 决定默认值，显式传入即可）：

```bash
python scripts/rigid_rigid/soccer_ball_collision/simulate_soccer_ball_collision.py --out <case>/physics_transforms.json
python scripts/rigid_rigid/soccer_ball_collision/build_pcve_soccer_ball_collision.py --out-root <suite> --simulate-only
python scripts/rigid_rigid/soccer_ball_collision/build_pcve_soccer_ball_collision.py --out-root <suite> --mode animation
python scripts/rigid_rigid/soccer_ball_collision/tools/audit_soccer_ball_collision.py --out-root <suite>
```

渲染阶段需要 Blender（`--blender` 或 `--render-python` 指定）；求解阶段需要 `requirements.txt` 里的 PyBullet。共享工具 `scripts/pcve_scene_runtime.py` 会自动探测 `--physics-python` / `--render-python`。

## 依赖

- Python：见 `requirements.txt`；Blender 4.x 的 `bpy` 由渲染环境自带，不是 pip 依赖。
- 资产：模型 `assets/models/`，贴图与 HDRI `assets/polyhaven/soccer_ball_collision/`，场景配方 `assets/scenarios/`。
- 共享代码：`scripts/pcve_edit_dsl.py`、`scripts/pcve_scene_runtime.py`、`scripts/pcve_project_paths.py`、`scripts/pcve_blender_compat.py`、`scripts/pcve_render_quality.py`、`scripts/pcve_legacy_scene.py`。

## 案例

| case |
| --- |
| `soccer_ball_collision_baseline` |
| `edit_fast_driver` |
| `edit_heavy_receiver` |
| `edit_dead_receiver` |
| `edit_add_midpoint_ball` |
| `edit_overspin_receiver_timed` |
| `edit_dsl` |
| `edit_summary` |

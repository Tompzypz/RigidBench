# PCVE 场景代码（rigid_rigid）

本目录把 `PCVE-RigidBench/clean_scripts` 的 21 个刚体场景，按 `PCVE-Bench/scripts/`
的组织方式重新落地为 `scripts/<category>/<scene>/`。

**实现内核未改**：每个场景的物理参数、几何构造、编辑词表、案例集合、渲染外观逻辑
都来自 `clean_scripts/<scene>` 原文，只做了两件事：

1. 把原先内嵌在 `edit_vocab.py` 里、通过 `sys.meta_path` 注册的源码 bundle
   （`_BUNDLE_SOURCES` + `install_scene_support()`）展开成真实模块文件；
2. 把这些模块按职责分到 `physics/`、`appearance/`、`tools/` 三个子目录，
   并把原来的相对导入改成扁平导入。

## 公共接口

每个场景恰好有五个对外文件：

| 文件 | 运行时 | 作用 |
| --- | --- | --- |
| `simulate_<scene>.py` | Python + PyBullet | 求解物理，输出 `physics_transforms.json` |
| `render_<scene>.py` | Python + bpy（Blender 4.x） | 回放求解位姿并渲染视频，不重算物理 |
| `build_pcve_<scene>.py` | Python（渲染阶段调 bpy） | 构建 source + 编辑案例套件 |
| `tools/render_queue.py` | Python | 随机批量采样，构建在 builder 之上 |
| `tools/audit_<scene>.py` | Python | 只读审计套件：清单、缓存、帧数 |

外加 `scene_config.py`（物理/相机/渲染默认值与校验的唯一来源）、`edit_vocab.py`
（编辑 DSL 词表、案例列表与 prompt）、`entrypoints.json`、`scene_manifest.json`、
`README.md`、`requirements.txt`。

所有入口共享同一段 `PCVE_UNIFIED_ENTRY_BEGIN` / `PCVE_UNIFIED_ENTRY_END` 前置块：
它在导入任何场景模块之前，把本场景根目录、`physics/`、`appearance/`、`tools/` 和共享的
`scripts/` 一起挂到 `sys.path`，所以模块按扁平名字互相 import 即可，不依赖包层级。

`entrypoints.json` 里 `python_runtime` 一律为 `null`：入口跑在调用它的解释器里，
需要指定环境时用 `--physics-python` / `--render-python` / `--blender`，不把机器路径写进清单。

## 校验

```bash
python scripts/check_scene_layout.py            # 含资产存在性检查
python scripts/check_scene_layout.py --skip-assets
```

检查项：必需文件是否齐全、`PCVE_UNIFIED_ENTRY_BEGIN` 标记是否存在、三个入口能否被 `ast`
解析、`entrypoints.json` 声明的入口文件名与实际文件是否一致、`implementation_files`
与 `scene_manifest.json` 声明的文件和资产是否真的在盘上。不启动求解器，也不渲染视频。

## 场景

| Scene | 案例数 | physics/ | appearance/ | 说明 |
| --- | --- | --- | --- | --- |
| [`ball_block_building`](rigid_rigid/ball_block_building/README.md) | 6 | 2 | 2 | 球撞击积木楼 |
| [`basketball_corner_rebound`](rigid_rigid/basketball_corner_rebound/README.md) | 6 | 0 | 1 | 篮球撞墙角反弹 |
| [`chalk_box_stack`](rigid_rigid/chalk_box_stack/README.md) | 6 | 5 | 2 | 粉笔盒堆叠 |
| [`door_basketball_collision`](rigid_rigid/door_basketball_collision/README.md) | 6 | 0 | 2 | 篮球撞门 |
| [`flatbed_speed_bump`](rigid_rigid/flatbed_speed_bump/README.md) | 6 | 2 | 2 | 平板车过减速带 |
| [`home_basketball_door`](rigid_rigid/home_basketball_door/README.md) | 6 | 0 | 1 | 室内篮球撞门 |
| [`kitchen_can_collision`](rigid_rigid/kitchen_can_collision/README.md) | 6 | 3 | 3 | 厨房罐头碰撞 |
| [`kitchen_tableware_collision`](rigid_rigid/kitchen_tableware_collision/README.md) | 6 | 3 | 1 | 厨房餐具碰撞 |
| [`newtons_cradle`](rigid_rigid/newtons_cradle/README.md) | 6 | 2 | 2 | 牛顿摆 |
| [`pendulum_box_collision`](rigid_rigid/pendulum_box_collision/README.md) | 6 | 3 | 2 | 单摆撞纸箱 |
| [`pool_break`](rigid_rigid/pool_break/README.md) | 6 | 2 | 3 | 台球开球 |
| [`pot_lid_drop`](rigid_rigid/pot_lid_drop/README.md) | 6 | 0 | 0 | 锅盖下落 |
| [`soccer_ball_collision`](rigid_rigid/soccer_ball_collision/README.md) | 8 | 3 | 1 | 足球对撞 |
| [`soccer_step_collision`](rigid_rigid/soccer_step_collision/README.md) | 6 | 3 | 2 | 足球撞台阶 |
| [`tennis_bottle_collision`](rigid_rigid/tennis_bottle_collision/README.md) | 6 | 5 | 1 | 网球撞塑料瓶 |
| [`toy_car_bottle`](rigid_rigid/toy_car_bottle/README.md) | 6 | 0 | 0 | 玩具车撞瓶 |
| [`toy_car_collision`](rigid_rigid/toy_car_collision/README.md) | 6 | 3 | 2 | 玩具车对撞 |
| [`twin_pendulum_collision`](rigid_rigid/twin_pendulum_collision/README.md) | 6 | 3 | 1 | 双摆碰撞 |
| [`u_track_ball`](rigid_rigid/u_track_ball/README.md) | 6 | 2 | 2 | U 型轨道滚球 |
| [`uneven_ground_ball`](rigid_rigid/uneven_ground_ball/README.md) | 6 | 2 | 2 | 不平地面滚球 |
| [`volleyball_corner_rebound`](rigid_rigid/volleyball_corner_rebound/README.md) | 6 | 1 | 2 | 排球撞墙角 |

合计 21 个场景、128 个案例、309 个场景内文件。机读索引见
[`scene_registry.json`](scene_registry.json)。

## 模块命名约定

`clean_scripts` 里的模块名与本目录的落点：

| clean_scripts 模块 | 本目录落点 | 含义 |
| --- | --- | --- |
| `scenario_io.py` | `scene_config.py` | 场景配方读写 + `BASELINE_*` 校验 |
| `scene_config.py` | `scene_config.py` | 同上（部分场景原本就叫这个名字） |
| `scene_geometry.py` / `*_geometry.py` | `physics/` | 碰撞体几何与初始位姿 |
| `runtime_support.py` | `physics/` | 求解器封装、步进与采样 |
| `motion_analysis.py` / `tail_analysis.py` | `physics/` | 求解后轨迹分析 |
| `cache_contract.py` | `physics/validate_<scene>.py` | 缓存签名与校验 |
| `scene_environment.py` | `appearance/look_<scene>.py` | 场景外观搭建（Blender） |
| `render_quality.py` / `camera_rig.py` / `props.py` 等 | `appearance/` | 只依赖 bpy 的外观层 |
| `batch_render_<scene>.py` | `tools/render_queue.py` | 批量渲染工作流 |

未被上表点名的模块按"是否 `import bpy`"自动归位：只碰 Blender 的进 `appearance/`，
其余进 `physics/`。

唯一的跨场景复用：`twin_pendulum_collision` 的外观层直接复用 `newtons_cradle` 的材质与
几何辅助函数（原文就是 `from newtons_cradle.scene_environment import ...`），现在指向
`newtons_cradle/appearance/look_newtons_cradle.py`，并在导入前把该目录加入 `sys.path`。

## 共享模块

`scripts/` 根目录下是本项目复用的公共代码，场景侧只读不改：

| 文件 | 作用 |
| --- | --- |
| `pcve_project_paths.py` | 从任意锚点向上定位仓库根与场景根 |
| `pcve_scene_runtime.py` | CLI/输出契约、解释器与 Blender 探测、实现指纹 |
| `pcve_blender_compat.py` | 跨 Blender 版本的 shader/Eevee 兼容层 |
| `pcve_render_quality.py` | 渲染质量档位与校验 |
| `pcve_legacy_scene.py` | 兼容层：按场景名定位目录并注入 `sys.path` |
| `pcve_scene_entry.py` | 统一入口参数适配（`--out-root`、`--dry-run`、`--describe` 等） |
| `pcve_scene_pipeline.py` | 分阶段运行器 |
| `pcve_edit_dsl.py` | 编辑指令 DSL 解析 |
| `pcve_timed_edits.py` | 定时编辑调度 |
| `pcve_verify_video.py` | 视频完整性校验 |
| `build_benchmark.py` | 全场景套件构建驱动 |
| `download_render_assets.py` | 渲染资产拉取 |
| `check_scene_layout.py` | 本目录的结构校验器 |

## 与 clean_scripts 的差异

只限组织方式，不改数值与算法：

- `_BUNDLE_SOURCES` 内嵌 bundle → 真实文件；
- `install_scene_support()` 的 `sys.meta_path` 加载器 → 普通 `sys.path` 注入；
- `from scene_support.<scene>.x import y` / `from <scene>.x import y` → `from x import y`；
- 场景目录深了一层（`scripts/rigid_rigid/<scene>/`），所以 `scene_dir.parent` 改成
  `scene_dir.parents[1]` 才能找到 `scripts/`；
- 缓存指纹原先 glob 场景目录下的 `*.py`，现在同时覆盖 `physics/` 与 `appearance/`，
  否则把模块挪进子目录后，改动它们将不再使缓存失效；
- `edit_vocab.py` 里有两类 `BASELINE_PHYSICS.update(...)` / `PHYSICS_LIMITS.update(...)`
  补丁（8 个场景涉及），原先靠"入口脚本 import `edit_vocab`"这一副作用生效。新入口不再
  import `edit_vocab`，所以这些补丁被逐字下沉到 `scene_config.py` 里、紧跟在它们扩展的
  定义之后——`scene_config.py` 本来就是"默认值与校验的唯一来源"，补丁放这里语义更准，
  且对所有入口一致生效。

`simulation_signature` 的哈希值会与 clean_scripts 版本不同——它是指纹，包含文件相对
路径与内容哈希，路径变了哈希必然变。`frames` / `events` / `objects` / `solver` /
`quality` / `fps` / `frame_end` 全部逐字段一致。

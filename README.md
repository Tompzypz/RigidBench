# my-bench

把 `PCVE-RigidBench` 的 21 个刚体场景，按 `PCVE-Bench` 的目录约定重新组织的一份工作副本。

场景名、物理参数、几何构造、编辑词表、案例集合、外观与渲染逻辑全部沿用
`PCVE-RigidBench/clean_scripts` 原文；改的只是文件组织方式——原先每个场景是"七个文件 +
内嵌源码 bundle"，现在展开成真实模块，并按 `scripts/<category>/<scene>/` 布局分到
`physics/`、`appearance/`、`tools/` 子目录。

```
my-bench/
├── scripts/
│   ├── README.md                  场景代码总览（含模块映射表与场景清单）
│   ├── scene_registry.json        21 个场景的机读索引
│   ├── check_scene_layout.py      结构校验器
│   ├── pcve_*.py                  跨场景共享模块
│   ├── build_benchmark.py         全场景套件构建驱动
│   ├── download_render_assets.py  渲染资产拉取
│   └── rigid_rigid/
│       └── <scene>/               21 个场景
│           ├── simulate_<scene>.py     PyBullet 求解（公开入口）
│           ├── render_<scene>.py       Blender 回放渲染（公开入口）
│           ├── build_pcve_<scene>.py   source + 编辑案例套件（公开入口）
│           ├── scene_config.py         默认值与校验的唯一来源
│           ├── edit_vocab.py           编辑 DSL 词表与案例
│           ├── entrypoints.json        声明式入口清单
│           ├── scene_manifest.json     模块/案例/资产清单
│           ├── requirements.txt
│           ├── README.md
│           ├── physics/                求解侧：几何、步进、轨迹分析、缓存校验
│           ├── appearance/             外观侧：只依赖 bpy 的材质/灯光/相机
│           └── tools/                  render_queue.py 与 audit_<scene>.py
└── assets/                        共享 3D 资产（689 MB / 140 个文件）
    ├── README.md                  资产清单与场景对应表
    ├── models/                    36 个 .glb
    ├── polyhaven/<scene>/         按场景分组的贴图与 HDRI
    └── scenarios/<scene>/         场景配方 JSON
```

## 快速开始

```bash
# 1. 结构校验（不启动求解器，不渲染）
python scripts/check_scene_layout.py

# 2. 求解一个场景
python scripts/rigid_rigid/pool_break/simulate_pool_break.py \
    --out /tmp/pool_break/physics_transforms.json

# 3. 构建完整套件（source + 编辑案例）
python scripts/rigid_rigid/pool_break/build_pcve_pool_break.py \
    --out-root /tmp/pool_break_suite --simulate-only

# 4. 渲染（需要 bpy 4.x 或 Blender）
python scripts/rigid_rigid/pool_break/render_pool_break.py \
    --physics-json /tmp/pool_break/physics_transforms.json \
    --out-dir /tmp/pool_break_frames

# 5. 审计产物
python scripts/rigid_rigid/pool_break/tools/audit_pool_break.py \
    --out-root /tmp/pool_break_suite
```

## 运行时

求解侧需要 Python + `pybullet`（版本见各场景 `requirements.txt`），渲染侧需要
Blender 4.x 的 `bpy`。`entrypoints.json` 里的 `python_runtime` 一律为 `null`，
入口跑在调用它的解释器里；需要指定环境时用：

- `--physics-python` / `PCVE_PHYSICS_PYTHON`
- `--render-python` / `PCVE_RENDER_PYTHON`
- `--blender` / `BLENDER_BIN`

## 场景

21 个场景全部在 `scripts/rigid_rigid/` 下，共 128 个案例（每个场景 source + 5 或 7 个编辑）。
完整清单、模块落点映射、以及"与 clean_scripts 的差异"见
[`scripts/README.md`](scripts/README.md)。

## 资产

`assets/` 从 `PCVE-RigidBench/assets` 完整复制：`models/` 36 个 GLB 模型、
`polyhaven/<scene>/` 按场景分组的 2K 贴图与 HDRI、`scenarios/<scene>/` 场景配方 JSON。
场景代码通过 `pcve_project_paths.project_root()` 向上定位仓库根，再拼 `assets/` 下的路径，
不依赖绝对路径。资产与场景的对应关系见 [`assets/README.md`](assets/README.md)。

## 实现等价性

新旧实现（`clean_scripts/<scene>` 与 `scripts/rigid_rigid/<scene>`）用同一台机器、同一份
PyBullet 环境分别求解，逐字段比较 `frames` / `events` / `objects` / `solver` / `quality` /
`fps` / `frame_end`，21 个场景全部一致。

`simulation_signature` 哈希值会不同：它是指纹，输入包含实现文件的相对路径与内容哈希，
目录结构变了哈希必然变——这是缓存契约的正常行为，不是物理差异。

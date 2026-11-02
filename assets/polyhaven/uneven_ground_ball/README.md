# 材质来源（CC0）

目录与命名沿用 `/scripts` 里其他场景（`flatbed_speed_bump`、`newtons_cradle`、
`ball_block_building`、`u_track_ball`）的约定：贴图平铺在 `assets/` 下，
命名 `<资产>_<通道>_<分辨率>.jpg`，`sources.json` 记录逐文件的下载地址、
字节数与 sha256。

本目录下的贴图来自 [Poly Haven](https://polyhaven.com)，授权为 **CC0 1.0 Universal（公有领域）**，
无需署名，也不限制商用。保留来源信息只是为了让渲染结果可复现、可审计。

| 资产 | 用途 | 分辨率 | 来源 |
|---|---|---|---|
| `floor_pebbles_01` | 庭院土路（漫反射 / 置换 / 法线 / 粗糙度 / AE） | 2k | https://polyhaven.com/a/floor_pebbles_01 |
| `grass_ground` | 小路两侧草坪（同一套通道） | 2k | https://polyhaven.com/a/grass_ground |
| `dirt_floor` | 备选土路，`--ground-texture dirt_floor` 可切换 | 2k | https://polyhaven.com/a/dirt_floor |

通道后缀：`diff`（漫反射，sRGB）、`disp`（高度）、`nor_gl`（OpenGL 法线）、
`rough`（粗糙度）、`ao`（烘焙遮蔽）。三套共 15 个文件、约 41 MB。

## 重新下载 / 换分辨率

```powershell
./.runtime/render/Scripts/python.exe scripts/uneven_ground_ball/fetch_visual_assets.py
./.runtime/render/Scripts/python.exe scripts/uneven_ground_ball/fetch_visual_assets.py --res 1k --assets floor_pebbles_01 grass_ground
```

脚本只下载缺失的文件，下载完会重写 `sources.json`。

## 为什么用贴图而不是直接下扫描地面模型

PCVE 的约束是**渲染面必须等于碰撞面**：`terrain_mesh.npz` 里的顶点同时喂给 pybullet 和 Blender，`mesh_hash` 会对两者做一致性断言。直接把 Sketchfab 上的扫描地形当作渲染网格，球的接触位置与画面就会脱钩，基准数据随即失效。

所以宏观起伏仍由解析高度场生成（见 `terrain_geometry.py`），贴图只补 5 cm 网格装不下的亚厘米级细节，并且**只进法线和置换着色，不移动任何顶点**。贴图缺失时材质自动退回程序化版本，离线也能渲染。

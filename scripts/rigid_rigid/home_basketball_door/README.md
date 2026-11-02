# Home Basketball Door (rigid_rigid)

## 目录结构

按 PCVE-Bench 的 `scripts/<category>/<scene>/` 布局整理：场景实现内核（物理、几何、外观、编辑词表、案例集合）与 `clean_scripts` 版本逐字一致，只把原先内嵌在 `edit_vocab.py` 里的源码 bundle 展开为真实模块文件，并按职责分到 `physics/`、`appearance/`、`tools/` 三个子目录。

```
home_basketball_door/
  simulate_home_basketball_door.py            PyBullet 求解（公开入口）
  render_home_basketball_door.py              Blender 回放与渲染（公开入口）
  build_pcve_home_basketball_door.py          source + 编辑案例套件构建（公开入口）
  scene_config.py           物理/相机/渲染默认值与校验的唯一来源
  edit_vocab.py             编辑 DSL 词表、案例列表与 prompt
  entrypoints.json  scene_manifest.json  README.md  requirements.txt
  appearance/   door_asset.py
  tools/        audit_home_basketball_door.py  render_queue.py
```

`physics/` 放求解侧与几何模块，`appearance/` 放只依赖 Blender 的外观层，`tools/` 放不在正式链路里的独立脚本。三个入口的 `PCVE_UNIFIED_ENTRY_BEGIN` 段落把这四个目录和共享的 `scripts/` 一起挂到 `sys.path`，所以模块可以直接按扁平名字 import。

## What can be edited

| DSL object.property | unit | baseline | simulated key |
| --- | --- | --- | --- |
| `ball.mass` | kg | 0.62 | `ball_mass` |
| `ball.speed` | m/s | 7.2 | `ball_speed` (launch condition — no `AT FRAME`) |
| `door.mass` | kg | 12.0 | `door_mass` |
| `door.friction` | N·m | 1.0 | `door_hinge_friction` |

`ball.speed` is marked `initial_condition=True`: the ball cannot retroactively
have been thrown slower. `door.friction` is a joint property, not a rigid-body
one — the simulator writes it with `changeDynamics(jointDamping=...)` on the
hinge and reads it back with `getJointInfo`, which is why the timed case can move
the hinge mid-swing while the leaf keeps the angular velocity it already has.

## The five cases

Source run: impact on frame 11, the leaf swings 45.0 → 0.07° (44.93° of travel,
peaking at 1.01 rad/s) and rests against the jamb from frame 33; the ball leaves
the impact at 3.92 m/s, traces 6.27 m of floor and ends at (0.91, 3.24).

| case | edit DSL | measured outcome |
| --- | --- | --- |
| `edit_light_ball` | `SET ball.mass TIMES 0.3` | 0.186 kg: a fifth of the momentum on the same frame, so the leaf travels only **9.92°** and hangs **35.08°** open; the lighter ball rebounds faster (4.23 m/s) and runs 6.76 m |
| `edit_heavy_door` | `SET door.mass TIMES 10` | 120 kg leaf: the same impulse buys a tenth of the spin — travel **10.64°**, still **34.36°** open at the end, creeping to rest only on frame 77, peak rate 1.01 → **0.11 rad/s** |
| `edit_stiff_hinge` | `SET door.friction TIMES 4` | 4.0 N·m braking torque eats the swing in 25.16° of travel, at rest on frame 29 with the leaf 19.84° open; the ball's path is identical to the source to the millimetre |
| `edit_slow_throw` | `SET ball.speed TIMES 0.5` | 3.60 m/s: impact slips from frame 11 to **frame 20**, travel **22.06°**, settles **22.94°** open on frame 53, ball path 5.52 m |
| `edit_stiff_hinge_late` | `SET door.friction TIMES 5 AT FRAME 12` | **mid-run**: see below — travel 23.05°, at rest on frame 26 with the leaf 21.95° open |

The two friction cases are the pair worth comparing: 4.0 N·m applied for the whole
clip and 5.0 N·m applied one frame after the impact end up 1.3° apart (19.84° vs
21.95°), because the swing is already dying by frame 12. The same edit applied at
frame 1 would have stopped it much earlier — that difference is the point of
having a timed case at all.

`edit_heavy_door` and `edit_slow_throw` are the pair worth comparing for the
*opposite* reason. They are the two ways to take energy out of the impact, and
they are not equivalent: ten times the leaf mass leaves the ball with more speed
after the hit (4.33 vs 3.84 m/s) because a heavy leaf barely yields, while
halving the throw halves the momentum *before* the contact. The leaf tells them
apart immediately — 10.64° of travel against 22.06°, and 44 frames of settling
instead of 20.

First frame on which each edit differs from the source, measured frame by frame
over the leaf angle, the ball position and both angular velocities:

| case | first differing frame | why there |
| --- | --- | --- |
| `edit_light_ball` | 11 | mass only matters once the contact exists |
| `edit_heavy_door` | 11 | same |
| `edit_stiff_hinge` | 11 | same |
| `edit_slow_throw` | 2 | the ball is already behind the source one frame after launch |
| `edit_stiff_hinge_late` | 13 | the write lands on frame 12, before that frame's substeps |


## How the timed case really lands

`edit_stiff_hinge_late` runs on the source physics for frames 1–11 and is
rewritten at the top of frame 12, one frame after the impact. The simulator
(`simulate_home_basketball_door.py`) reads the hinge out of the live client,
writes the new damping, reads it back, and continues solving from the state it
already reached. `physics_transforms.json` records:

```json
{"frame": 12, "time_sec": 0.4583, "parameter": "door_hinge_friction",
 "from": 1.0, "to": 5.0,
 "state_before": {"door_angle_deg": 41.28, "door_angular_velocity": -0.994, ...},
 "state_after":  {"door_angle_deg": 41.28, "door_angular_velocity": -0.994, ...}}
```

The angle and the rate are unchanged across the write, which is what a real hinge
does: the torque changes, not the motion. Frames 1–12 are the source clip — the
write lands at the top of frame 12, before that frame's substeps, and the angle
recorded for frame 12 is still the source's 41.28° — and the first frame that
differs is 13 (38.93° against 38.98°). `build_pcve_home_basketball_door.py`
copies the event log and the quality block from the run into
`suite_manifest.json`, so the claim is checkable without re-simulating.

## 运行

在仓库根目录执行（`--out-root` 由各入口的 argparse 决定默认值，显式传入即可）：

```bash
python scripts/rigid_rigid/home_basketball_door/simulate_home_basketball_door.py --out <case>/physics_transforms.json
python scripts/rigid_rigid/home_basketball_door/build_pcve_home_basketball_door.py --out-root <suite> --simulate-only
python scripts/rigid_rigid/home_basketball_door/build_pcve_home_basketball_door.py --out-root <suite> --mode animation
python scripts/rigid_rigid/home_basketball_door/tools/audit_home_basketball_door.py --out-root <suite>
```

渲染阶段需要 Blender（`--blender` 或 `--render-python` 指定）；求解阶段需要 `requirements.txt` 里的 PyBullet。共享工具 `scripts/pcve_scene_runtime.py` 会自动探测 `--physics-python` / `--render-python`。

## 依赖

- Python：见 `requirements.txt`；Blender 4.x 的 `bpy` 由渲染环境自带，不是 pip 依赖。
- 资产：模型 `assets/models/`，贴图与 HDRI `assets/polyhaven/home_basketball_door/`，场景配方 `assets/scenarios/`。
- 共享代码：`scripts/pcve_edit_dsl.py`、`scripts/pcve_scene_runtime.py`、`scripts/pcve_project_paths.py`、`scripts/pcve_blender_compat.py`、`scripts/pcve_render_quality.py`、`scripts/pcve_legacy_scene.py`。

## 案例

| case |
| --- |
| `home_basketball_door_baseline` |
| `edit_light_ball` |
| `edit_heavy_door` |
| `edit_stiff_hinge` |
| `edit_slow_throw` |
| `edit_stiff_hinge_late` |

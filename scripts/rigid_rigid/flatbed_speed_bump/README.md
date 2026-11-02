# Flatbed Speed Bump (rigid_rigid)

## 目录结构

按 PCVE-Bench 的 `scripts/<category>/<scene>/` 布局整理：场景实现内核（物理、几何、外观、编辑词表、案例集合）与 `clean_scripts` 版本逐字一致，只把原先内嵌在 `edit_vocab.py` 里的源码 bundle 展开为真实模块文件，并按职责分到 `physics/`、`appearance/`、`tools/` 三个子目录。

```
flatbed_speed_bump/
  simulate_flatbed_speed_bump.py            PyBullet 求解（公开入口）
  render_flatbed_speed_bump.py              Blender 回放与渲染（公开入口）
  build_pcve_flatbed_speed_bump.py          source + 编辑案例套件构建（公开入口）
  scene_config.py           物理/相机/渲染默认值与校验的唯一来源
  edit_vocab.py             编辑 DSL 词表、案例列表与 prompt
  entrypoints.json  scene_manifest.json  README.md  requirements.txt
  physics/      runtime_support.py  validate_flatbed_speed_bump.py
  appearance/   import_props.py  import_truck.py
  tools/        audit_flatbed_speed_bump.py  render_queue.py
```

`physics/` 放求解侧与几何模块，`appearance/` 放只依赖 Blender 的外观层，`tools/` 放不在正式链路里的独立脚本。三个入口的 `PCVE_UNIFIED_ENTRY_BEGIN` 段落把这四个目录和共享的 `scripts/` 一起挂到 `sys.path`，所以模块可以直接按扁平名字 import。

## What can be edited

| DSL object.property | unit | baseline | simulated key |
| --- | --- | --- | --- |
| `flatbed_truck.initial_velocity` | m/s | 9.0 | `truck_speed` (launch condition — no `AT FRAME`) |
| `flatbed_truck.speed` | m/s | 9.0 | `truck_speed` (live write allowed) |
| `speed_bump.height` | m | 0.17 | `speed_bump_height` |
| `cargo.friction` | – | 0.20 | `cargo_friction` |

The two truck properties are deliberately separate. `initial_velocity` is marked
`initial_condition=True`, so the DSL rejects `... AT FRAME n` on it: the truck
cannot retroactively have started at a different speed. `speed` is the cruise
target the drive force chases every step, which is a quantity that can be
changed while the truck is moving.

## The five cases

One source plus exactly five edits. Every number is read back from
`run_status.json` of the run that produced the clip.

| case | edit DSL | measured outcome |
| --- | --- | --- |
| `edit_fast_truck` | `SET flatbed_truck.initial_velocity TIMES 2` | 18 m/s: deck lift 0.446 → **1.816 m**, 21 and 22 airborne frames, both cartons thrown clear, truck ends at x = 64.14 m (still on the 140 m road) |
| `edit_low_bump` | `SET speed_bump.height TIMES 0.3` | 0.051 m bump: lift collapses to **0.034 m**, clearance 0.029/0.027 m, 2 and 2 airborne frames — nothing visibly separates (`quality.visible` is false) |
| `edit_high_bump` | `SET speed_bump.height TIMES 1.5` | 0.255 m bump: lift 0.909 m, clearance 0.649/0.247 m, 14 and 15 airborne frames — the cartons are thrown clear of the whole deck |
| `edit_slippery_cargo` | `SET cargo.friction TIMES 0.25` | μ 0.20 → 0.05: the cartons slide while the deck moves under them, clearance 0.396/0.039 m, **both** end off the deck instead of one |
| `edit_brake_before_bump` | `SET flatbed_truck.speed TIMES 0.4 AT FRAME 8` | **mid-run**: 9.0 → 3.6 m/s written into the running simulation; lift 0.085 m, clearance 0.006/0.007 m, **zero airborne frames**, truck ends at x = 9.54 m instead of 28.59 m |

Source run: lift 0.446 m, clearance 0.240/0.059 m, 14 and 7 airborne frames, one
carton off the deck at the end, truck at x = 28.594 m.

First frame on which each edit differs from the source, measured by comparing the
recorded chassis, deck and carton poses frame by frame:

| case | first differing frame | why there |
| --- | --- | --- |
| `edit_fast_truck` | 1 | a different launch speed is visible on the first integrated step |
| `edit_slippery_cargo` | 2 | the cartons start creeping as soon as the deck pitches |
| `edit_low_bump` | 14 | the front axle only touches the bump around here |
| `edit_high_bump` | 14 | same, from the other side |
| `edit_brake_before_bump` | 9 | the throttle is written at the top of frame 8; one step later it bites |

Read the table as a single-variable experiment. The 0.3x bump and the late brake
both suppress the throw — one by removing the input, the other by arriving too
slowly to use it — and both end with `quality.visible = false`, which the builder
accepts for an edit (it is the *source* that has to show the effect). The high
bump and the slippery cargo both amplify it, for different reasons: more deck
acceleration versus less traction, which is why the slippery case keeps the deck
lift of the source (0.454 m) while still throwing both cartons off.

## How the timed case really lands

`edit_brake_before_bump` is the one case that cannot be expressed as command-line
parameters, because the same parameter has to hold two values in one run.
`build_pcve_flatbed_speed_bump.py` writes the schedule to `timed_edits.json` and
passes `--timed-edits-json`; `simulate_flatbed_speed_bump.py` loads it before the
first step and consults it at the top of every frame. On frame 8 it lowers the
cruise target, leaves the truck's current velocity alone (lifting off the throttle,
not teleporting), and the force brings the truck down over the next frames.

`run_status.json` records the write with state on both sides:

```json
{"frame": 8, "time_sec": 0.2917, "parameter": "truck_speed",
 "from": 9.0, "to": 3.6, "state_before": {...}, "state_after": {...}}
```

Frames 1–8 are the source run bit for bit (the throttle is written at the top of
frame 8, and the truck's velocity there is still the source's); the first frame
that differs is 9, because the drive force needs one step to take effect.

## Camera rigs

Every rig is bolted to the ground — there is no dolly, deliberately, so the
truck's speed is what moves in frame. `wide` is the three-quarter hero rig
standing 8 m off the near kerb at the bump, and it is the one used for the
delivered stills. `clip4s` stands 20.5 m back and holds the whole 41 m baseline
run, so it is the rig for "what does the last frame look like" on the source
clip. `static` and `survey` are the older bump-side placements; `static` sits
behind the container stack at the near kerb and occludes the right half of the
frame, which is why it is not used for output.

### The preview frame moved from 20 to 24

The burst suspension reaches its peak deck lift around frame 24 in the source
run (1.32 m of truck height at x = 1.6 m), and that is where the cartons are
highest and most separable between cases, so the stills are taken there. Frame
20 was the old choice and it caught the truck still climbing.

That choice also matters for `edit_fast_truck`. At 18 m/s the truck is at
x = 10.1 m and 2.71 m of chassis height on frame 24 — mid-flight, past the bump —
where the source is at 1.6 m and 1.32 m. The `wide` rig's 44 mm frustum holds
both: the truck sits 3.9 m off the axis of a frame that is ±8.8 m wide at that
distance, so the same still is a like-for-like comparison.

```powershell
& .runtime/sim/python.exe clean_scripts/flatbed_speed_bump/build_pcve_flatbed_speed_bump.py `
    --mode preview --camera-mode wide --preview-frame 24 --resolution 960 540 `
    --cases flatbed_speed_bump_baseline edit_fast_truck --out-root renders/flatbed_bump_frames
```

### A 4 s clip now covers 71 m, and only one rig holds it

The doubled launch speed is a real result, not a rendering effect: the truck
covers 71.1 m in the 4 s clip (x = −7 → 64.14) against 35.6 m for the source, and
lifts 1.816 m off the bump — 4× the source's 0.446 m.

Framing that was checked analytically rather than by eye, projecting the chassis
pose of every frame into each rig's frustum:

| rig | source clip | `edit_fast_truck` |
| --- | --- | --- |
| `clip4s` (36 mm, 20.5 m back) | in frame 1–96 | in frame 1–96, sitting at 37 % of half-width on the last frame |
| `wide` (44 mm, 8 m back) | in frame 1–96 | in frame 1–55, off the right edge from 56 |

So `clip4s` still holds the whole doubled run and remains the rig for a full
4 s clip of that case; `wide` is the bump-side hero rig and only covers the
action window. The delivered stills use `wide` on frame 24, where both cases are
comfortably inside the frame — the chassis is 14 % left of centre on the source
and 44 % right of centre on the doubled run, 39 % above centre because it is
mid-flight.


## 运行

在仓库根目录执行（`--out-root` 由各入口的 argparse 决定默认值，显式传入即可）：

```bash
python scripts/rigid_rigid/flatbed_speed_bump/simulate_flatbed_speed_bump.py --out <case>/physics_transforms.json
python scripts/rigid_rigid/flatbed_speed_bump/build_pcve_flatbed_speed_bump.py --out-root <suite> --simulate-only
python scripts/rigid_rigid/flatbed_speed_bump/build_pcve_flatbed_speed_bump.py --out-root <suite> --mode animation
python scripts/rigid_rigid/flatbed_speed_bump/tools/audit_flatbed_speed_bump.py --out-root <suite>
```

渲染阶段需要 Blender（`--blender` 或 `--render-python` 指定）；求解阶段需要 `requirements.txt` 里的 PyBullet。共享工具 `scripts/pcve_scene_runtime.py` 会自动探测 `--physics-python` / `--render-python`。

## 依赖

- Python：见 `requirements.txt`；Blender 4.x 的 `bpy` 由渲染环境自带，不是 pip 依赖。
- 资产：模型 `assets/models/`，贴图与 HDRI `assets/polyhaven/flatbed_speed_bump/`，场景配方 `assets/scenarios/`。
- 共享代码：`scripts/pcve_edit_dsl.py`、`scripts/pcve_scene_runtime.py`、`scripts/pcve_project_paths.py`、`scripts/pcve_blender_compat.py`、`scripts/pcve_render_quality.py`、`scripts/pcve_legacy_scene.py`。

## 案例

| case |
| --- |
| `flatbed_speed_bump_baseline` |
| `edit_fast_truck` |
| `edit_low_bump` |
| `edit_high_bump` |
| `edit_slippery_cargo` |
| `edit_brake_before_bump` |

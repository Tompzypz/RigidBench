# Kitchen Can Collision (rigid_rigid)

## 目录结构

按 PCVE-Bench 的 `scripts/<category>/<scene>/` 布局整理：场景实现内核（物理、几何、外观、编辑词表、案例集合）与 `clean_scripts` 版本逐字一致，只把原先内嵌在 `edit_vocab.py` 里的源码 bundle 展开为真实模块文件，并按职责分到 `physics/`、`appearance/`、`tools/` 三个子目录。

```
kitchen_can_collision/
  simulate_kitchen_can_collision.py            PyBullet 求解（公开入口）
  render_kitchen_can_collision.py              Blender 回放与渲染（公开入口）
  build_pcve_kitchen_can_collision.py          source + 编辑案例套件构建（公开入口）
  scene_config.py           物理/相机/渲染默认值与校验的唯一来源
  edit_vocab.py             编辑 DSL 词表、案例列表与 prompt
  entrypoints.json  scene_manifest.json  README.md  requirements.txt
  physics/      runtime_support.py  scene_geometry.py  validate_kitchen_can_collision.py
  appearance/   look_kitchen_can_collision.py  survey_camera.py  tabletop_props.py
  tools/        audit_kitchen_can_collision.py  render_queue.py
```

`physics/` 放求解侧与几何模块，`appearance/` 放只依赖 Blender 的外观层，`tools/` 放不在正式链路里的独立脚本。三个入口的 `PCVE_UNIFIED_ENTRY_BEGIN` 段落把这四个目录和共享的 `scripts/` 一起挂到 `sys.path`，所以模块可以直接按扁平名字 import。

## What can be edited

`edit_vocab.py` declares the properties below on four objects and maps each to
the physics key the simulator actually reads, so a DSL line and a simulated
quantity are the same thing:

| DSL object.property | unit | baseline | simulated key |
| --- | --- | --- | --- |
| `rolling_can.mass` | kg | 0.24 | `driver_mass` |
| `upright_can.mass` | kg | 0.24 | `receiver_mass` |
| `rolling_can.initial_velocity` | m/s | 0.62 | `initial_velocity` (launch condition — no `AT FRAME`) |
| `rolling_can.speed` | m/s | 0.62 | `initial_velocity` (live write) |
| `upright_can.initial_velocity` | m/s | 0.0 | `receiver_initial_velocity` |
| `pair.restitution` | – | 0.45 | `restitution` |
| `can.friction` | – | 0.065 | `can_friction` |
| `table.friction` | – | 1.0 | `table_friction` |

Every binding above is legal DSL; the five delivered cases happen to use five of
them. The launch-speed pair is declared but not exercised — this scene's story is
"heavier / rougher / gone", and a slower roll is the one edit that a viewer can
reproduce by eye without measuring anything, so the benchmark spends its five
slots on the knobs that are hard to judge instead.

`DELETE upright_can` is supported too: it removes the body, zeroes
`receiver_active`, drops the object from the per-frame ground truth and from the
render roster in the same step, so the removal is not a rendering trick.

### Why friction is two knobs and not one

PyBullet gives every body a single `lateralFriction`; at a contact it multiplies
the two surviving values. There is no per-pair friction in this engine, so
"the cans are rougher" and "the worktop is smoother" have to be written as two
separate body-level writes — `can.friction` writes the can body,
`table.friction` writes the worktop body. The simulation does exactly that and
reports the body values it actually set (`effective_can_lateral_friction`,
`effective_table_lateral_friction`) next to the numbers the edit asked for, so
the two can be compared without trusting a comment.

An earlier revision tried to expose the *pair* value instead and compensate with
`sqrt`: `μ_can = sqrt(pair)`, `μ_table = table / sqrt(pair)`. A control
experiment killed it — scaling the pair by 10 also dragged the worktop body from
1.0 down to 0.316, which cost 9 % of the rolling deceleration. The two
coefficients are not interchangeable in this solver, so they are not pretended
to be.

## The five cases

`build_pcve_kitchen_can_collision.py` writes one source case plus exactly five
edits. Every number below is read back from `simulation_metrics.json` of the run
that produced the clip, not predicted.

| case | edit DSL | what the simulation did |
| --- | --- | --- |
| `edit_heavy_driver` | `SET rolling_can.mass TIMES 3` | 0.72 kg roller: impulse 0.154 → 0.402 N·s, roller runs 0.611 → **0.858 m**, target displaced 0.147 → **0.394 m**, tilt 3.12 → 6.10° |
| `edit_heavy_receiver` | `SET upright_can.mass TIMES 3` | 0.72 kg target: impulse rises to 0.229 N·s but the heavier can barely moves — 0.023 m, tilt 0.94°, and the roller itself is stopped early (0.487 m) |
| `edit_remove_receiver` | `DELETE upright_can` | no contact at all (`first_impact_sec: null`): the roller travels 0.611 → **1.306 m** and is still creeping at 0.085 m/s on the last frame |
| `edit_rough_cans` | `SET can.friction TIMES 3` | can body 0.065 → **0.195**: the roller loses speed faster on the way in (contact at 0.8465 s instead of 0.8431 s) and stops sooner at 0.520 m; the struck can, which now also slides on a 3× rougher body, is left at **0.056 m** even though it leaves the contact a little faster (0.292 vs 0.276 m/s) |
| `edit_slippery_table` | `SET table.friction TIMES 0.25 AT FRAME 30` | **mid-run**: the worktop drops 1.0 → 0.25 at 1.208 s, after the hit — the target keeps sliding to **0.335 m** and the roller to 0.799 m |

Source run for comparison: first impact 0.843 s (≈ frame 21 at 24 fps), roller
0.611 m, target 0.147 m, peak receiver speed 0.276 m/s, max tilt 3.12°, settled
by 1.84 s.

First frame on which each edit differs from the source, measured by comparing
every recorded body pose frame by frame:

| case | first differing frame | why there |
| --- | --- | --- |
| `edit_heavy_driver` | 22 | mass only matters once the contact exists; frame 21 is still the approach |
| `edit_heavy_receiver` | 22 | same |
| `edit_remove_receiver` | 1 | the body is gone before the first frame is recorded |
| `edit_rough_cans` | 2 | the rougher contact bites on the very first rolling step |
| `edit_slippery_table` | 31 | the write lands on frame 30 and takes effect in that frame's substeps |

## How the timed case really lands

`edit_slippery_table` is not a cached re-render.
`simulate_kitchen_can_collision.py` parses the schedule **before** the first
step, then checks `frame_index in schedule` at every frame boundary. On frame 30
it reads both bodies out of the live client, calls `changeDynamics` on the
worktop with the new `lateralFriction`, and lets the solver continue from the
state it already reached. `run_status.json` records the event:

```json
{"frame": 30, "time_sec": 1.2083333333, "parameter": "table_friction",
 "from": 1.0, "to": 0.25, "state_before": {...}, "state_after": {...}}
```

`state_before` and `state_after` are identical on purpose — friction is a
constraint coefficient, not a state variable, so the poses must not jump. What
changes is everything *after*: from frame 31 the two cans slide 0.799 m and
0.335 m instead of 0.611 m and 0.147 m. A friction edit that moved the bodies at
the moment of the write would be a teleport, not a physics change.

Frames 1–30 are therefore byte-identical to the source clip. The frame-30 event
also lands **after** the collision at frame 21, which is the point of the case:
it shows the coefficient controlling a body that is already moving, with no
effect on the impact that already happened.

Timed writes are validated against a second, wider band (`TIMED_FIELDS`) than
the start-of-run options, because a mid-run change is not a launch condition.

### One detail that keeps the baseline honest

Both cans are dropped onto the worktop and given 240 settle steps before the
initial velocity is applied. Those settle steps deliberately run with the
**source** coefficients (`SOURCE_CAN_MU`, `SOURCE_TABLE_MU`) and the declared
`can_friction` / `table_friction` are written afterwards. Without that, editing
friction would also change where the cans came to rest during the settle, and
`edit_rough_cans` would differ from the source before it had rolled a single
centimetre. With it, the baseline trajectory is bit-identical to the revision
before the friction knobs existed, and every difference in a friction case comes
from the rolling itself.

## Is the can actually rolling?

Yes, and it is measured rather than asserted. The simulator writes a per-frame
`max_preimpact_slip_ratio` into `quality`, computed as
`slip = |v_x − ω_y·R|`, `ratio = slip / |v_x|` with `R = 0.033 m`; pure rolling
gives 0, a can skidding across the worktop without turning would give 1.

| case | pre-impact max | pre-impact median |
| --- | --- | --- |
| source | 0.52 % | 0.40 % |
| `edit_rough_cans` | 0.42 % | 0.34 % |
| `edit_slippery_table` | 0.52 % | 0.40 % |

Half a percent is contact-solver noise. Across the whole source clip the largest
ratio is 97 % on frame 22 — the frame *after* the hit — then 57 %, 54 %, 20 %,
and 4.3 % by frame 26, after which the median settles at 0.28 %. That is the
real behaviour of a struck can: the collision reverses the linear velocity in
one substep while the spin cannot follow instantly, so the can skids briefly and
then the contact re-grips. It is not a numerical artefact, and its decay is the
evidence: a solver that had lost the rolling constraint would stay near 1.

The rougher case peaks at 55 % on the same frame instead of 97 %, because a
higher coefficient lets the spin catch up faster. That the edit changes *how*
the transient decays — and not just the stopping distance — is a second,
independent confirmation that the friction value reached the solver.

## 运行

在仓库根目录执行（`--out-root` 由各入口的 argparse 决定默认值，显式传入即可）：

```bash
python scripts/rigid_rigid/kitchen_can_collision/simulate_kitchen_can_collision.py --out <case>/physics_transforms.json
python scripts/rigid_rigid/kitchen_can_collision/build_pcve_kitchen_can_collision.py --out-root <suite> --simulate-only
python scripts/rigid_rigid/kitchen_can_collision/build_pcve_kitchen_can_collision.py --out-root <suite> --mode animation
python scripts/rigid_rigid/kitchen_can_collision/tools/audit_kitchen_can_collision.py --out-root <suite>
```

渲染阶段需要 Blender（`--blender` 或 `--render-python` 指定）；求解阶段需要 `requirements.txt` 里的 PyBullet。共享工具 `scripts/pcve_scene_runtime.py` 会自动探测 `--physics-python` / `--render-python`。

## 依赖

- Python：见 `requirements.txt`；Blender 4.x 的 `bpy` 由渲染环境自带，不是 pip 依赖。
- 资产：模型 `assets/models/`，贴图与 HDRI `assets/polyhaven/kitchen_can_collision/`，场景配方 `assets/scenarios/`。
- 共享代码：`scripts/pcve_edit_dsl.py`、`scripts/pcve_scene_runtime.py`、`scripts/pcve_project_paths.py`、`scripts/pcve_blender_compat.py`、`scripts/pcve_render_quality.py`、`scripts/pcve_legacy_scene.py`。

## 案例

| case |
| --- |
| `kitchen_can_collision_baseline` |
| `edit_heavy_driver` |
| `edit_heavy_receiver` |
| `edit_remove_receiver` |
| `edit_rough_cans` |
| `edit_slippery_table` |

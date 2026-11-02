# Volleyball Corner Rebound (rigid_rigid)

## 目录结构

按 PCVE-Bench 的 `scripts/<category>/<scene>/` 布局整理：场景实现内核（物理、几何、外观、编辑词表、案例集合）与 `clean_scripts` 版本逐字一致，只把原先内嵌在 `edit_vocab.py` 里的源码 bundle 展开为真实模块文件，并按职责分到 `physics/`、`appearance/`、`tools/` 三个子目录。

```
volleyball_corner_rebound/
  simulate_volleyball_corner_rebound.py            PyBullet 求解（公开入口）
  render_volleyball_corner_rebound.py              Blender 回放与渲染（公开入口）
  build_pcve_volleyball_corner_rebound.py          source + 编辑案例套件构建（公开入口）
  scene_config.py           物理/相机/渲染默认值与校验的唯一来源
  edit_vocab.py             编辑 DSL 词表、案例列表与 prompt
  entrypoints.json  scene_manifest.json  README.md  requirements.txt
  physics/      scene_geometry.py
  appearance/   camera_rig.py  look_volleyball_corner_rebound.py
  tools/        audit_volleyball_corner_rebound.py  render_queue.py
```

`physics/` 放求解侧与几何模块，`appearance/` 放只依赖 Blender 的外观层，`tools/` 放不在正式链路里的独立脚本。三个入口的 `PCVE_UNIFIED_ENTRY_BEGIN` 段落把这四个目录和共享的 `scripts/` 一起挂到 `sys.path`，所以模块可以直接按扁平名字 import。

## Suite: one source and five edits

The source video is a 4 s, 96-frame clip of one volleyball thrown diagonally down into a room corner: it lands at 0.58 s, hits the `x=0` wall at 1.33 s and the `y=0` wall at 2.26 s, and rolls out to about (2.25, 0.70) m. The ball's mass is deliberately *not* an editable property: a free sphere under gravity obeys mass-independent contact laws and follows the identical trajectory at any mass, so a mass edit would render as the source video. Every edit below moves the simulated trajectory by at least 1.45 m, and the numbers quoted in `edit_summary` are the ones the run produced.

| Case | DSL | Effect on the run |
| --- | --- | --- |
| `edit_speed_x15` | `SET ball.initial_velocity TIMES 1.5` | 5.85 → 8.775 m/s, same direction; first wall impact at 0.74 s |
| `edit_restitution_x03` | `SET ball.restitution TIMES 0.3` | 0.78 → 0.234; the ball stops bouncing and dies in the corner at (0.15, 0.11) m |
| `edit_friction_x05` | `SET ball.friction TIMES 0.5` | 0.55 → 0.275; peak spin 30.5 → 19.4 rad/s and it slides out to (3.97, 1.20) m |
| `edit_wall_restitution_x04` | `SET wall.restitution TIMES 0.4` | 1.0 → 0.4; the walls absorb the rebound, the ball slides down and stops in the corner at (0.50, 0.20) m |
| `edit_gravity_x25_at24` | `SET world.gravity TIMES 2.5 AT FRAME 24` | at 0.958 s, with the ball airborne, gravity becomes -24.525 m/s² |

The last case is timed. The schedule travels in the case's `scenario_overrides.json` (`physics.timed_edits`) and the simulator writes the new gravity into the live solver at the top of frame 24, before any of that frame's substeps run, so frames 1-23 stay bit-identical to the source video. `build_pcve_*.py` checks that prefix frame by frame, and the applied event — with its before/after values and the ball state at that instant — is recorded in `simulation_metrics.json` and in the case's manifest entry.

There is no ADD and no DELETE here. The ball's story stays inside the near corner and along the two impact walls, and decoration moved in or out would change the picture without changing the physics the edit is meant to demonstrate. What the props do is measured rather than assumed: the cabinet, the two spare volleyballs and the wall-mounted split unit are real static colliders, and the only prop contact in the whole suite is the sideboard that `edit_speed_x15` grazes once at 1.69 s. Everything else is clear of every run by more than 0.48 m.

## Room, camera and props

The room is 10 × 8 × 3 m and the ball plays in the near corner; the window is a 1.4 m opening in the `x=0` wall spanning `y` 1.8-3.2 m.

The corner is empty. That is a decision, not an oversight: the corner the camera can see is the only corner in shot, and it is also the corner the ball rebounds into and comes to rest in. A planter there is a collider the two low-restitution edits roll into — measured, at any radius from 0.15 to 0.19 m — and a planter anywhere else in this room is either out of frame or standing right in front of the window. So the corner is left clear and the ball's story stays its own. `room_layout_validation.json` asserts this per case with `plant_objects` (must be 0), alongside the counts it does expect: one framed artwork, two spare volleyballs, both in frame, the spares stationary, and the window fully in shot.

The single picture hangs on the `y=0` wall at x=3.0 m, 1.75 m up, 0.90 m tall. `cafe_wall_pictures.glb` actually holds three pictures on one shared 0.49 × 0.33 m mesh that differ only in texture, so choosing the artwork is a name lookup and nothing about the wall, the frame depth or the height moves. Picture 1 — the photo-real window-and-coffee-jar still life this scene used to hang — collapses into a brown smudge at the 30-odd pixels it gets, and picture 3, a coffee-bean owl on cream, vanishes against the pale plaster. Picture 2, a copper mug on a flat blush ground, is the one that still reads as a picture from the far end of the room, so `scene_environment.PICTURE_MESH` names it.

The split indoor unit hangs on the window wall (`x=0`), underside 2.40 m up and 0.90 m clear of the window's right reveal at `y=3.2` m, which leaves the top of the case at 2.81 m. Two things drove that wall. `indoor_air_conditioner_unit.glb` imports at 0.531 × 0.131 × 0.181 m and the room is 10 × 8 × 3 m = 240 m³, which a 3 HP split of roughly 1.10 × 0.25 × 0.33 m serves, so it is scaled uniformly by 2.26 to 1.20 m wide (0.409 × 0.296 m) — its own proportions, not the nominal 3 HP figures. And a wall's foreshortening is `sqrt(1-(v·t)²)`: on the `y=0` wall the same face kept 0.56 of its length — the earlier hanging there projected at 2.42 against a true 2.93, which is the "distorted" the eye reads — while on the window wall, seen from this camera, it now keeps 0.95 and projects at 2.89 against the same 2.93. `room_layout_validation.json` records `air_conditioner_count` (1), `air_conditioner_in_frame`, `air_conditioner_back_gap_m` measured along the wall normal (0.006) and `min_air_conditioner_clearance_m` (2.47 m, measured per substep). One material change is deliberate: the glb's packed metallic channel reads 0.91 across the painted shell, which under this overcast HDR renders the unit as a blue-grey mirror, so metallic is pinned to 0 while roughness still comes from the supplied map.

It stops at 2.81 m because of the slab, not because of the camera. Install manuals ask for roughly 0.15 m between the top of the case and the ceiling, and 0.19 m is what the room leaves; the earlier 2.64 m limit was something else entirely — a "no ceiling in shot" rule sitting in `camera_frame_validation` that I had written for the camera and then read as a property of the room. It was not one. Inside a 3 m box every upward ray meets the ceiling somewhere, so the rule could only be satisfied by aiming low, and aiming low is what held the unit down. Delete the rule and the unit rises 0.17 m, grows 20 %, and the roof appears as a 5.8 % band along the top edge. What is a real limit is resolution: from 9.7 m away the 0.19 m between the case and the slab subtends 1.1°, which is 13 px at 640 × 360, so any headroom worth having above the unit necessarily puts the ceiling in frame.

The two spare volleyballs sit at the far end of the sideboard, (4.75, 0.30) and (4.95, 0.80) m, clear of every run by 0.64 m. They used to stand at (3.75, 0.36) and (3.95, 0.78), where the 1.5× speed edit passed one of them by 0.2 mm — a knife-edge that any solver change would have turned into a collision and a different ground-truth trajectory.

The comparison camera is fixed at (8.6, 7.6, 2.25) m, 38 mm, aimed at (3.4, 3.5, 1.20) m. It moved 0.8 m closer to the window wall than the (9.4, 7.4) used before, for two reasons: at 9.7 m the wall is seen more squarely, and the split unit — now the largest prop in the room — gains about 8 % in pixels for free. The aim rose from 0.70 m to 1.20 m once the frame was allowed to contain the roof, which is what gives the unit 23 px of clearance at the top edge while keeping the ball 66 px clear of the bottom one. The framing budget is wide: from this position the near spare ball at (4.75, 0.30) sits on a bearing of −118° and the far end of the unit at (0, 5.30) on −159°, a 41° span that has to fit inside the lens's 50.6° horizontal field along with the artwork and the window. 38 mm is the longest lens that still holds all six trajectories and every gated prop; at 50 mm they leave the frame. The ball is therefore 18 px across at its farthest at 960 × 540. `camera_frame_validation.json` closes the loop by ray-casting the finished frame on a 64 × 36 grid: it reports `ceiling_sample_fraction` (0.058 against a `ceiling_band_limit` of 0.12), `camera_inside_room` and `highest_visible_surface_z_m` (2.999 m, against a 3.0 m room). The ceiling is checked as a band rather than banned: banning it was the constraint that used to hold the split unit down, and the thing worth asserting is that the roof reads as an edge of the room, not as the subject. `--camera-preset scene` uses the closer room camera instead — (5.8, 5.8, 2.75) m at 30 mm, which keeps the whole trajectory in frame and trades floor for a slightly larger ball, at the cost of a wider ceiling band.

The ceiling reads as one even grey band, and that took a fix. It is the only surface in shot that no light aims at: the three interior fills are 2.4–3.5 m disks hanging 0.12–0.35 m under the slab and tilted 45–70°, so their upper rims reach 3.19, 4.13 and 4.28 m — straight through a slab whose underside is at 3.00 m. Every other surface is lit by the face of those disks and does not care; the slab is lit only by the rim, at grazing angles, and that grazing is the blotch. Measured over the slab, the three fills on their own put down a mean of 51.8 with std 18.8, while the sky and the daylight through the window on their own put down a flat 0.4. `exempt_slab_from_fills()` states that instead of moving lights the rest of the shot depends on: light linking leaves the slab listening to the window daylight and nothing else, and every other pixel of the frame is unchanged. With the fills gone the slab has no other source, so its albedo carries the whole tone and rose from 0.73 to 0.88 — it lands at 138.4 with std 0.6, against the previous 146.6 ± 7.4.

## 运行

在仓库根目录执行（`--out-root` 由各入口的 argparse 决定默认值，显式传入即可）：

```bash
python scripts/rigid_rigid/volleyball_corner_rebound/simulate_volleyball_corner_rebound.py --out <case>/physics_transforms.json
python scripts/rigid_rigid/volleyball_corner_rebound/build_pcve_volleyball_corner_rebound.py --out-root <suite> --simulate-only
python scripts/rigid_rigid/volleyball_corner_rebound/build_pcve_volleyball_corner_rebound.py --out-root <suite> --mode animation
python scripts/rigid_rigid/volleyball_corner_rebound/tools/audit_volleyball_corner_rebound.py --out-root <suite>
```

渲染阶段需要 Blender（`--blender` 或 `--render-python` 指定）；求解阶段需要 `requirements.txt` 里的 PyBullet。共享工具 `scripts/pcve_scene_runtime.py` 会自动探测 `--physics-python` / `--render-python`。

## 依赖

- Python：见 `requirements.txt`；Blender 4.x 的 `bpy` 由渲染环境自带，不是 pip 依赖。
- 资产：模型 `assets/models/`，贴图与 HDRI `assets/polyhaven/volleyball_corner_rebound/`，场景配方 `assets/scenarios/`。
- 共享代码：`scripts/pcve_edit_dsl.py`、`scripts/pcve_scene_runtime.py`、`scripts/pcve_project_paths.py`、`scripts/pcve_blender_compat.py`、`scripts/pcve_render_quality.py`、`scripts/pcve_legacy_scene.py`。

## 案例

| case |
| --- |
| `volleyball_corner_rebound_baseline` |
| `edit_speed_x15` |
| `edit_restitution_x03` |
| `edit_friction_x05` |
| `edit_wall_restitution_x04` |
| `edit_gravity_x25_at24` |

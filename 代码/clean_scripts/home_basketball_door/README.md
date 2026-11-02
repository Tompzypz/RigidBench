# Home Basketball Door (rigid_rigid)

A 0.62 kg basketball is thrown across a bedroom at 7.2 m/s into a half-open door,
knocks it most of the way shut, rebounds off the leaf and rolls across the floor
until it stops. The leaf is 12 kg on a hinge with 1.0 N·m of Coulomb friction.

## Scene files

| File | Role |
| --- | --- |
| `simulate_home_basketball_door.py` | PyBullet rigid-body simulation |
| `render_home_basketball_door.py` | Blender scene construction and rendering |
| `build_pcve_home_basketball_door.py` | PCVE source/edit suite builder |
| `batch_render_home_basketball_door.py` | Batch rendering entry point |
| `edit_vocab.py` | Declared editable physical parameters |
| `entrypoints.json` | Entry-point and native option manifest |
| `README.md` | Run instructions and scene notes |

The scene package contains exactly these seven files. Its scene-specific implementation is included in the Python entrypoints. Common CLI/edit utilities are in `clean_scripts/`; model, texture and scenario assets are loaded from repository-level `assets/`.

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

## Run

From the repository root, use the configured Python and Blender Python environments:

```powershell
& .runtime/sim/python.exe clean_scripts/home_basketball_door/simulate_home_basketball_door.py --help
& .runtime/render/Scripts/python.exe clean_scripts/home_basketball_door/render_home_basketball_door.py --help
& .runtime/sim/python.exe clean_scripts/home_basketball_door/build_pcve_home_basketball_door.py --dry-run --out-root renders/home_basketball_door_suite
```

Build the whole suite (six cases, full clips):

```powershell
& .runtime/sim/python.exe clean_scripts/home_basketball_door/build_pcve_home_basketball_door.py --out-root renders/home_basketball_door_suite
```

For a cheap visual check, `--mode preview --preview-frame 96 --resolution 960 540`
renders one still instead of 96 frames; `--only edit_light_ball,edit_heavy_door`
restricts the build to named cases, and `--clean-stale-cases` drops case
directories that are no longer part of the suite.

## Dependencies

The scene reads shared assets from `assets/`. Scene-specific Python implementation is contained in this folder; shared interfaces and edit utilities are listed in `entrypoints.json`.

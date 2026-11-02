# Flatbed Speed Bump (rigid_rigid)

A flatbed truck carrying two 42 kg cartons crosses a 0.17 m high, 1.34 m wide
rounded bump at 9 m/s. The deck is sprung (40 kN/m, 1.87 kN·s/m, −0.09/+0.07 m of
travel) and the cartons sit on it with a friction coefficient of 0.2, so the
wheel strike pumps the deck and the cartons are thrown: both leave the deck for
14 and 7 frames respectively, and the near-side one slides over the tail onto the
road while the far one settles back onto the deck.

## Scene files

| File | Role |
| --- | --- |
| `simulate_flatbed_speed_bump.py` | PyBullet rigid-body simulation |
| `render_flatbed_speed_bump.py` | Blender scene construction and rendering |
| `build_pcve_flatbed_speed_bump.py` | PCVE source/edit suite builder |
| `batch_render_flatbed_speed_bump.py` | Batch rendering entry point |
| `edit_vocab.py` | Declared editable physical parameters |
| `entrypoints.json` | Entry-point and native option manifest |
| `README.md` | Run instructions and scene notes |

The scene package contains exactly these seven files. Its scene-specific implementation is included in the Python entrypoints. Common CLI/edit utilities are in `clean_scripts/`; model, texture and scenario assets are loaded from repository-level `assets/`.

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


## Run

From the repository root, use the configured Python and Blender Python environments:

```powershell
& .runtime/sim/python.exe clean_scripts/flatbed_speed_bump/simulate_flatbed_speed_bump.py --help
& .runtime/render/Scripts/python.exe clean_scripts/flatbed_speed_bump/render_flatbed_speed_bump.py --help
& .runtime/sim/python.exe clean_scripts/flatbed_speed_bump/build_pcve_flatbed_speed_bump.py --dry-run --out-root renders/flatbed_speed_bump_suite
```

Build the whole suite (six cases):

```powershell
& .runtime/sim/python.exe clean_scripts/flatbed_speed_bump/build_pcve_flatbed_speed_bump.py --out-root renders/flatbed_speed_bump_suite
```

`--mode preview` renders the tail frame only; `--cases` restricts the build to
named cases; `--clean-stale-cases` drops case directories that are no longer part
of the suite.

## Dependencies

The scene reads shared assets from `assets/`. Scene-specific Python implementation is contained in this folder; shared interfaces and edit utilities are listed in `entrypoints.json`.

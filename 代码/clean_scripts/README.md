# PCVE scene code

Each live scene is stored under `scripts/<category>/<scene>/` and has exactly
one canonical `simulate_<scene>.py`, `render_<scene>.py`,
`build_pcve_<scene>.py`, `README.md` and `entrypoints.json`.
`surface_<scene>.py` is optional when reconstruction is a separate stage.

## Public interface

The public entries share `--out-root`, `--dry-run`, `--describe`, `--python`,
`--blender`, `--gpu` and `--threads`. The builder also lists cases/workflows.
Native physics/input/cache options remain scene-specific and compatible.
No physical, numerical, optical or quality defaults are centralized or changed.
`pcve_scene_entry.py` adapts the CLI before solver/Blender imports; a dry run
only prints its JSON plan. Scene-owned implementations retain their original
process boundaries. `pcve_scene_pipeline.py` remains the stage runner for the
scenes that already use it.

Current edit workflows are indexed in each scene's `entrypoints.json`.
Independent current code has descriptive source/edits/model directories;
superseded implementations and code backup archives are removed. Git keeps
the recoverable code history. Assets and accepted simulation/video data retain
their original provenance paths and are not code-version aliases.

## Validation

```bash
python3 scripts/check_scene_layout.py
```

The checker verifies all canonical files and runs help/read-only planning for
every public entry. It does not start solvers or render videos.

## Scenes

| Category | Scene | Documentation |
| --- | --- | --- |
| `rigid_rigid` | `air_hockey_chain` | [README](rigid_rigid/air_hockey_chain/README.md) |
| `rigid_rigid` | `ball_block` | [README](rigid_rigid/ball_block/README.md) |
| `rigid_rigid` | `ball_box_rebound` | [README](rigid_rigid/ball_box_rebound/README.md) |
| `rigid_rigid` | `ball_carpet_climb` | [README](rigid_rigid/ball_carpet_climb/README.md) |
| `rigid_rigid` | `bouncing_ball` | [README](rigid_rigid/bouncing_ball/README.md) |
| `rigid_rigid` | `bowling` | [README](rigid_rigid/bowling/README.md) |
| `rigid_rigid` | `car_gap_jump` | [README](rigid_rigid/car_gap_jump/README.md) |
| `rigid_rigid` | `car_ramp_climb` | [README](rigid_rigid/car_ramp_climb/README.md) |
| `rigid_rigid` | `curling_collision` | [README](rigid_rigid/curling_collision/README.md) |
| `rigid_rigid` | `dining_chain` | [README](rigid_rigid/dining_chain/README.md) |
| `rigid_rigid` | `domino_chain` | [README](rigid_rigid/domino_chain/README.md) |
| `rigid_rigid` | `mahjong_dice` | [README](rigid_rigid/mahjong_dice/README.md) |
| `rigid_rigid` | `picnic_apple_ball` | [README](rigid_rigid/picnic_apple_ball/README.md) |
| `rigid_rigid` | `pool_collision` | [README](rigid_rigid/pool_collision/README.md) |
| `rigid_rigid` | `ramp_collision` | [README](rigid_rigid/ramp_collision/README.md) |
| `rigid_rigid` | `table_drop_collision` | [README](rigid_rigid/table_drop_collision/README.md) |
| `rigid_rigid` | `table_marble_collision` | [README](rigid_rigid/table_marble_collision/README.md) |
| `rigid_rigid` | `tennis_flight` | [README](rigid_rigid/tennis_flight/README.md) |
| `rigid_rigid` | `toy_car_ball` | [README](rigid_rigid/toy_car_ball/README.md) |
| `rigid_rigid` | `twin_ramp_collision` | [README](rigid_rigid/twin_ramp_collision/README.md) |
| `rigid_fluid` | `apple_drop_kitchen_basin` | [README](rigid_fluid/apple_drop_kitchen_basin/README.md) |
| `rigid_fluid` | `bowling_ball_pool_drop` | [README](rigid_fluid/bowling_ball_pool_drop/README.md) |
| `rigid_fluid` | `coffee_ice_drop` | [README](rigid_fluid/coffee_ice_drop/README.md) |
| `rigid_fluid` | `cooking_oil_pan` | [README](rigid_fluid/cooking_oil_pan/README.md) |
| `rigid_fluid` | `cup_water_drop` | [README](rigid_fluid/cup_water_drop/README.md) |
| `rigid_fluid` | `faucet_sink` | [README](rigid_fluid/faucet_sink/README.md) |
| `rigid_fluid` | `fish_tank_toy` | [README](rigid_fluid/fish_tank_toy/README.md) |
| `rigid_fluid` | `honey_spoon_toast` | [README](rigid_fluid/honey_spoon_toast/README.md) |
| `rigid_fluid` | `juice_dispenser_orange_cup` | [README](rigid_fluid/juice_dispenser_orange_cup/README.md) |
| `rigid_fluid` | `milk_pitcher_glass` | [README](rigid_fluid/milk_pitcher_glass/README.md) |
| `rigid_fluid` | `tilted_cup_table_pour` | [README](rigid_fluid/tilted_cup_table_pour/README.md) |
| `rigid_fluid` | `toy_boat_pool_glide` | [README](rigid_fluid/toy_boat_pool_glide/README.md) |
| `rigid_fluid` | `toy_car_float_bathtub` | [README](rigid_fluid/toy_car_float_bathtub/README.md) |
| `rigid_fluid` | `toy_car_ramp_pool_genesis` | [README](rigid_fluid/toy_car_ramp_pool_genesis/README.md) |
| `rigid_fluid` | `traditional_tea_pour` | [README](rigid_fluid/traditional_tea_pour/README.md) |
| `rigid_fluid` | `wine_pour` | [README](rigid_fluid/wine_pour/README.md) |
| `rigid_elastic` | `beach_ball_hammock_mpm` | [README](rigid_elastic/beach_ball_hammock_mpm/README.md) |
| `elastic_fluid` | `bathroom_sink_duck_neospace` | [README](elastic_fluid/bathroom_sink_duck_neospace/README.md) |
| `elastic_fluid` | `elastic_fluid_duck` | [README](elastic_fluid/elastic_fluid_duck/README.md) |
| `elastic_fluid` | `glass_bottle_water_balloon_true_coupled` | [README](elastic_fluid/glass_bottle_water_balloon_true_coupled/README.md) |
| `elastic_fluid` | `wind_flag` | [README](elastic_fluid/wind_flag/README.md) |

`elastic_elastic/` is reserved and currently has no scenes.

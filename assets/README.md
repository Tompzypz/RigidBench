# Shared scene assets

Models, textures, HDR environments, and scenario JSON files used by the standardized rigid scenes are resolved from this repository-level directory. The previous copies under `scripts/models` and scene-local folders are retained as historical inputs, but current entry points use the shared assets listed here.

## Models

| File | Scene(s) |
| --- | --- |
| `models/tennis_ball.glb` | ball_block_building, uneven_ground_ball |
| `models/building_block_building.glb` | ball_block_building |
| `models/office_desk___6mb.glb` | ball_block_building, u_track_ball |
| `models/realistic_blackboard.glb` | ball_block_building, pendulum_box_collision, u_track_ball |
| `models/indoor_plant.glb` | ball_block_building |
| `models/flatbed_unity3d.glb` | flatbed_speed_bump |
| `models/carton_box_05_closed.glb` | flatbed_speed_bump, u_track_ball |
| `models/speed_bump.glb` | flatbed_speed_bump |
| `models/cloe_room.glb` | home_basketball_door |
| `models/old_door.glb` | home_basketball_door |
| `models/cafe_wall_pictures.glb` | home_basketball_door, pool_break |
| `models/basketball.glb` | home_basketball_door |
| `models/the_pen.glb` | pendulum_box_collision, u_track_ball |
| `models/pool_table_animation.glb` | pool_break |
| `models/pool_table_-_billiard_table_with_cues_and_balls.glb` | pool_break |
| `models/jayden_miles_individual_modular_props.glb` | pool_break |
| `models/rustic_chair.glb` | pool_break |
| `models/a_pot.glb` | pot_lid_drop |
| `models/modern_kitchen.glb` | pot_lid_drop |
| `models/hotwheels_technetium__www.vecarz.com.glb` | toy_car_bottle |
| `models/plastic_water_bottle.glb` | toy_car_bottle |
| `models/lamppost.glb` | toy_car_bottle |
| `models/office_table.glb` | u_track_ball |
| `models/desk.glb` | u_track_ball |
| `models/futuristic_room.glb` | uneven_ground_ball |

## Scenario data

| File | Scene |
| --- | --- |
| `scenarios/home_basketball_door/scenario.json` | home_basketball_door |
| `scenarios/home_basketball_door/door_leaf.json` | home_basketball_door |
| `scenarios/pot_lid_drop/scenario.json` | pot_lid_drop |
| `scenarios/pot_lid_drop/lid_hull.json` | pot_lid_drop |
| `scenarios/toy_car_bottle/scenario.json` | toy_car_bottle |

## Texture and environment maps

These files are grouped by scene under `polyhaven/`:

- `ball_block_building/`: `wood_floor_worn_diff_2k.jpg`, `wood_table_diff_2k.jpg`, `wood_table_nor_gl_2k.jpg`, `wood_table_rough_2k.jpg`, `wooden_lounge_2k.hdr`
- `flatbed_speed_bump/`: `asphalt_02_diff_2k.jpg`, `asphalt_02_nor_gl_2k.jpg`, `asphalt_02_rough_2k.jpg`, `concrete_floor_damaged_01_diff_2k.jpg`, `concrete_floor_damaged_01_nor_gl_2k.jpg`, `concrete_floor_damaged_01_rough_2k.jpg`, `corrugated_iron_02_diff_2k.jpg`, `corrugated_iron_02_nor_gl_2k.jpg`, `corrugated_iron_02_rough_2k.jpg`, `industrial_sunset_02_2k.hdr`, `metal_plate_diff_2k.jpg`, `metal_plate_nor_gl_2k.jpg`, `metal_plate_rough_2k.jpg`, `overcast_industrial_courtyard_4k.hdr`, `painted_metal_shutter_diff_2k.jpg`, `painted_metal_shutter_nor_gl_2k.jpg`, `painted_metal_shutter_rough_2k.jpg`
- `u_track_ball/`: `wood_floor_worn_diff_2k.jpg`, `wood_table_diff_2k.jpg`, `wood_table_nor_gl_2k.jpg`, `wood_table_rough_2k.jpg`, `wooden_lounge_2k.hdr`
- `uneven_ground_ball/`: `dirt_floor_ao_2k.jpg`, `dirt_floor_diff_2k.jpg`, `dirt_floor_disp_2k.jpg`, `dirt_floor_nor_gl_2k.jpg`, `dirt_floor_rough_2k.jpg`, `floor_pebbles_01_ao_2k.jpg`, `floor_pebbles_01_diff_2k.jpg`, `floor_pebbles_01_disp_2k.jpg`, `floor_pebbles_01_nor_gl_2k.jpg`, `floor_pebbles_01_rough_2k.jpg`, `grass_ground_ao_2k.jpg`, `grass_ground_diff_2k.jpg`, `grass_ground_disp_2k.jpg`, `grass_ground_nor_gl_2k.jpg`, `grass_ground_rough_2k.jpg`
- `newtons_cradle/`: `sources.json`, `wood_floor_worn_diff_2k.jpg`, `wood_table_diff_2k.jpg`, `wood_table_nor_gl_2k.jpg`, `wood_table_rough_2k.jpg`, `wooden_lounge_2k.hdr`

Original model and texture files remain in their former locations. Runtime code for the ten standardized scenes loads models from `assets/models`, environment maps and textures from `assets/polyhaven/<scene>`, and scenario recipes from `assets/scenarios/<scene>`.


## New scene assets

The new projects under `new-scripts/` also load their visual resources from this shared directory. The previous `new-scripts/models/` copies are retained for reference; scene code resolves the centralized paths below.

| Shared asset | Scene(s) |
| --- | --- |
| `models/basketball.glb` | basketball_corner_rebound, door_basketball_collision, soccer_step_collision |
| `models/cloe_room.glb`, `models/old_door.glb`, `models/cafe_wall_pictures.glb` | door_basketball_collision |
| `models/modern_kitchen.glb`, `models/bowl_and_chops.glb`, `models/pepsi_tin_with_texture.glb` | kitchen_can_collision, kitchen_tableware_collision |
| `models/cheap_soccer_ball.glb` | soccer_ball_collision, soccer_step_collision |
| `models/fiddle_leaf_fig.glb` | soccer_step_collision, volleyball_corner_rebound |
| `models/plastic_water_bottle.glb`, `models/tennis_ball.glb` | tennis_bottle_collision |
| `models/futuristic_room.glb`, `models/hotwheels_technetium__www.vecarz.com.glb`, `models/cartoonish_toy_car.glb` | toy_car_collision |
| `models/volleyball.glb`, `models/cafe_wall_pictures.glb` | volleyball_corner_rebound |

Scenario inputs are grouped under `scenarios/`: basketball corner, door basketball, both kitchen scenes, both soccer scenes, tennis bottle, toy car, and volleyball corner each have their own folder. Tennis collision and bottle mass-property JSON inputs are in `scenarios/tennis_bottle_collision/`.

Scene texture maps are grouped by slug under `polyhaven/`: `basketball_corner_rebound/`, `soccer_ball_collision/`, `soccer_step_collision/`, and `volleyball_corner_rebound/`. Volleyball's courtyard HDR and floor map live beside the other volleyball textures. Newton's cradle's wood HDR remains in `polyhaven/newtons_cradle/` and is shared by the twin-pendulum scene.

"""Scenario contract for toy_car_bottle.

The physical and layout inputs live in ``assets/scenarios/toy_car_bottle/scenario.json``;
this module is the single import point for the scene code and adds the derived
anchors that the solver, the renderer and the edit vocabulary all share.
"""
from __future__ import annotations

# PCVE_UNIFIED_ENTRY_BEGIN
import sys as _scene_sys
from pathlib import Path as _ScenePath
_SCENE_DIR = _ScenePath(__file__).resolve().parent
_SCRIPTS_DIR = _SCENE_DIR.parents[1]
if str(_SCRIPTS_DIR) not in _scene_sys.path:
    _scene_sys.path.insert(1, str(_SCRIPTS_DIR))
for _scene_sub in ("physics", "appearance", "tools"):
    _scene_sub_dir = _SCENE_DIR / _scene_sub
    if _scene_sub_dir.is_dir() and str(_scene_sub_dir) not in _scene_sys.path:
        _scene_sys.path.insert(1, str(_scene_sub_dir))
# PCVE_UNIFIED_ENTRY_END

import copy
import json
from pathlib import Path

from pcve_project_paths import project_root as _pcve_project_root

_PCVE_ROOT = _pcve_project_root(__file__)

SCENE_NAME = "toy_car_bottle"
SCENARIO_PATH = _PCVE_ROOT / "assets" / "scenarios" / SCENE_NAME / "scenario.json"


def read_json(path):
    return json.loads(Path(path).expanduser().read_text(encoding="utf-8"))


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def prepare_config(config):
    """Add this scene's dormant second-bottle slot and geometry anchors."""
    physics = config["physics"]
    layout = config["layout"]
    car_position = [physics["car_start_x"], 0.0, layout["car_height"] / 2 + 0.0005]
    bottle_position = [physics["bottle_start_x"], physics["bottle_start_y"], layout["bottle_height"] / 2 + 0.001]
    # ADD placement is resolved on the shared action plane; using the car's
    # lower centre height would put an upright bottle midpoint below the floor.
    car_add_anchor = [car_position[0], car_position[1], bottle_position[2]]
    midpoint = [(a + b) / 2 for a, b in zip(car_add_anchor, bottle_position)]
    physics.setdefault("car_start_position", car_position)
    physics.setdefault("car_add_anchor_position", car_add_anchor)
    physics.setdefault("car_geometry_radius", layout["car_length"] / 2)
    physics.setdefault("bottle_radius", layout["bottle_radius"])
    physics.setdefault("bottle_start_position", bottle_position)
    physics.setdefault("bottle_presence", [1, 0])
    physics.setdefault("bottle_2_mass", physics["bottle_mass"])
    physics.setdefault("bottle_2_friction", physics["bottle_friction"])
    physics.setdefault("bottle_2_restitution", physics["bottle_restitution"])
    physics.setdefault("bottle_2_linear_damping", physics.get("bottle_linear_damping", 0.02))
    physics.setdefault("bottle_2_angular_damping", physics.get("bottle_angular_damping", 0.04))
    physics.setdefault("bottle_2_rolling_friction", physics.get("bottle_rolling_friction", 0.002))
    physics.setdefault("bottle_2_start_position", midpoint)
    return config


def load_scenario(scenario_path=None, overrides_path=None):
    """Baseline scenario with an optional override file merged group by group."""
    config = read_json(scenario_path or SCENARIO_PATH)
    if overrides_path is not None:
        for group, values in read_json(overrides_path).items():
            if group not in config:
                raise ValueError(f"Unknown scenario override group: {group}")
            config[group].update(values)
    return prepare_config(config)


BASELINE_CONFIG = prepare_config(copy.deepcopy(read_json(SCENARIO_PATH)))
BASELINE_PHYSICS = BASELINE_CONFIG["physics"]

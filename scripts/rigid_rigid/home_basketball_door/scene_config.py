"""Shared scenario loading for the home_basketball_door scene.

``scenario.json`` holds three blocks -- ``assets``, ``physics`` and
``layout`` -- and every entry point (simulator, renderer, PCVE builder) reads
it through here, so a case's override file is merged exactly one way: group by
group, key by key, with nested dicts merged recursively and everything else
replaced wholesale.

An override file is therefore the same shape as ``scenario.json`` with only the
keys that differ, e.g. ``{"physics": {"lid_mass": 0.9}}``. That is also the
shape ``build_pcve_home_basketball_door.py`` writes for each edit case.
"""

from __future__ import annotations
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)

import copy
import json
from pathlib import Path
from typing import Any

SCENE_DIR = _PCVE_ROOT / 'assets' / 'scenarios' / 'home_basketball_door'
SCENARIO_PATH = SCENE_DIR / 'scenario.json'

GROUPS = ('assets', 'physics', 'layout')


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(Path(path).expanduser().read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError(f'Expected a JSON object: {path}')
    return data


def merge(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def load_scenario(
    scenario_path: Path | None = None,
    overrides_path: Path | None = None,
) -> dict[str, Any]:
    """Baseline scenario, with an optional overrides file merged on top."""
    scenario = read_json(scenario_path or SCENARIO_PATH)
    for group in GROUPS:
        scenario.setdefault(group, {})
    if overrides_path is not None:
        scenario = merge(scenario, read_json(overrides_path))
        scenario['overrides_path'] = str(Path(overrides_path).expanduser().resolve())
    return scenario


def write_json(path: Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')

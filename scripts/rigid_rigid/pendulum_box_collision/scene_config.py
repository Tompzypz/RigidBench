"""Scenario contract for the pendulum-and-box impact scene.

One definition of the four editable physics parameters, the sampling window and
the camera, imported by the simulator, the renderer, the suite builder and the
batch sampler. Nothing outside this file decides what an edit may change.

World conventions
-----------------
* **+X** runs along the bench from the wooden box towards the pendulum. The box
  starts at negative X and travels towards +X; the bob hangs at ``x = 0``.
* **+Y** points from the camera into the wall, so the camera sits at negative Y.
* **+Z** is up. The bench top is ``z = 0.76`` and gravity acts along -Z.
* SI units everywhere: metres, kilograms, seconds, radians in the cache.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
from copy import deepcopy
import json, math

SCENE_NAME = 'pendulum_box_collision'

# The four knobs the scene was built to expose. Bob mass and bob speed are the
# pendulum's two; box mass and box speed are the slider's two. Everything else
# -- restitution, friction, pendulum length, box size, release geometry -- is
# fixed so that an edit changes one thing and nothing else.
BASELINE_PHYSICS = dict(bob_mass=.40, bob_speed=.55, box_mass=.40, box_speed=1.30)

# Legal ranges, enforced before every simulation.
#
# ``bob_speed`` is bounded from above by the block, not by the solver: the bob
# starts at the lowest point and rises ``v^2/2g``, so the swing amplitude grows
# with the square of this number. At 0.90 m/s the bob peaks 26.5 degrees up the
# arc and its centre is still 17 mm below the top of the 85 mm slider, which is
# what keeps a whole-face impact possible at any phase. Above roughly 0.97 m/s
# the bob would meet the block's top edge instead of its face.
#
# ``box_speed`` is bounded from below by the approach: the slider has 0.70 m of
# bench to cover before it reaches the bob, and the initial approach window is 1.05 s, so a
# block below about 1.10 m/s would miss the original approach window.
# Keep these staging limits unchanged when extending the aftermath.
PHYSICS_LIMITS = dict(bob_mass=(.05, 5.0), bob_speed=(0.0, .90),
                      box_mass=(.05, 5.0), box_speed=(1.12, 3.5))

# Editable keys this scene adds on top of the shared baseline. These used to
# run as an import side effect of edit_vocab; scene_config owns them now.
BASELINE_PHYSICS.update(restitution=.55, timed_edits=[])
PHYSICS_LIMITS.update(restitution=(.05, .92))

# Show the return collision and subsequent motion at real-time playback.
DEFAULT_DURATION_SEC = 4.0
TOTAL_FRAMES = 96


def defaults():
    return dict(schema_version=1, scene=SCENE_NAME,
        physics=deepcopy(BASELINE_PHYSICS),
        render=dict(fps=24, duration_sec=DEFAULT_DURATION_SEC, slow_motion=1,
                    resolution=[1280, 720], samples=128),
        camera=dict(location=[.68, -2.28, 1.20], target=[-.02, .03, .925],
                    ortho_scale=1.06))


def merge(base, overrides):
    result = deepcopy(base)
    for key, value in overrides.items():
        result[key] = (merge(result[key], value)
                       if isinstance(value, dict) and isinstance(result.get(key), dict)
                       else deepcopy(value))
    return result


def validate(s):
    if set(s) - {'schema_version', 'scene', 'physics', 'render', 'camera', 'seed'} or s.get('scene') != SCENE_NAME:
        raise ValueError('Invalid scenario fields or scene name')
    c = s['physics']; r = s['render']
    if set(c) != set(BASELINE_PHYSICS):
        raise ValueError('Unknown or missing physics parameter')
    for key, value in c.items():
        if key == 'timed_edits':
            if not isinstance(value, list) or any(
                    not isinstance(entry, dict) or set(entry) != {'frame', 'params'}
                    or type(entry['frame']) is not int
                    or not isinstance(entry['params'], dict) or not entry['params']
                    or any(not isinstance(v, (int, float)) or not math.isfinite(v)
                           for v in entry['params'].values())
                    for entry in value):
                raise ValueError('Invalid timed_edits schedule')
            continue
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f'Invalid {key}')
        low, high = PHYSICS_LIMITS[key]
        if not low <= value <= high:
            raise ValueError(f'{key} must be between {low} and {high}')
    if not isinstance(r['fps'], int) or r['fps'] <= 0 or not math.isfinite(r['duration_sec']) or r['duration_sec'] <= 0:
        raise ValueError('Invalid timing')
    if r['slow_motion'] not in (1, 2, 4, 8):
        raise ValueError('slow_motion must be 1, 2, 4 or 8')
    if r['fps'] * r['slow_motion'] > 2400:
        raise ValueError('Sample rate exceeds physics rate')
    if round(r['fps'] * r['slow_motion'] * r['duration_sec']) < 1:
        raise ValueError('Empty trajectory')
    if (not isinstance(r['samples'], int) or r['samples'] < 1 or len(r['resolution']) != 2
            or any(not isinstance(v, int) or v < 2 or v % 2 for v in r['resolution'])):
        raise ValueError('Invalid render settings; use even resolution')
    camera = s['camera']
    for key in ('location', 'target'):
        if len(camera[key]) != 3 or not all(math.isfinite(v) for v in camera[key]):
            raise ValueError('Invalid camera vector')
    if camera['location'] == camera['target'] or not math.isfinite(camera['ortho_scale']) or camera['ortho_scale'] <= 0:
        raise ValueError('Invalid camera')


def load_scenario(args):
    s = merge(defaults(), json.loads(args.scenario_json.read_text(encoding='utf-8'))) if args.scenario_json else defaults()
    if args.scenario_overrides_json:
        s = merge(s, json.loads(args.scenario_overrides_json.read_text(encoding='utf-8')))
    for key in BASELINE_PHYSICS:
        if getattr(args, key, None) is not None:
            s['physics'][key] = getattr(args, key)
    for key in ('fps', 'duration_sec', 'slow_motion', 'resolution', 'samples'):
        if getattr(args, key, None) is not None:
            s['render'][key] = getattr(args, key)
    validate(s)
    return s

"""Render the scene, or replay a cached trajectory, using the standard scene CLI.

The pendulum's thread is the only object that is not a simulated body: it is
aimed from the pivot to the bob's centre on every frame. The rod constraint
keeps that distance close to PENDULUM_LENGTH. The drawing retains its small
numerical drift so both thread endpoints match the cached simulation.
"""
# PCVE_UNIFIED_ENTRY_BEGIN

# Resolve the shared scripts directory, then this scene's module folders.
import sys as _clean_sys
from pathlib import Path as _CleanPath
_clean_scene_dir = _CleanPath(__file__).resolve().parent
_scripts_dir = _clean_scene_dir.parents[1]
_PCVE_PROJECT_ROOT = next(p for p in _clean_scene_dir.parents if (p / "assets").is_dir())
if str(_scripts_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_scripts_dir))
if str(_clean_scene_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_clean_scene_dir))
# Shared modules live in scripts/; scene-local modules live in this directory and
# its physics/, appearance/ and tools/ subdirectories.
for _scene_sub in ("", "physics", "appearance", "tools"):
    _scene_sub_dir = _clean_scene_dir / _scene_sub if _scene_sub else _clean_scene_dir
    if _scene_sub_dir.is_dir() and str(_scene_sub_dir) not in _clean_sys.path:
        _clean_sys.path.insert(1, str(_scene_sub_dir))
# PCVE_UNIFIED_ENTRY_END




from pathlib import Path
from copy import deepcopy
import argparse, json, sys, subprocess, shutil, math

from runtime_support import python_for  # noqa: E402
from validate_pendulum_box_collision import validate_cache  # noqa: E402
from scene_config import BASELINE_PHYSICS, validate  # noqa: E402
from look_pendulum_box_collision import (  # noqa: E402
    APPEARANCE_VERSION, ENVIRONMENT_THEME, build_room, configure_lighting)
from render_quality import configure_color, configure_renderer  # noqa: E402


from pcve_scene_runtime import parse_render_args, run_renderer

def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')


def thread_pose(pivot, position, rest_length):
    from mathutils import Vector, Quaternion
    direction = Vector(position) - Vector(pivot)
    azimuth = math.atan2(direction.y, direction.x)
    polar = math.atan2(math.hypot(direction.x, direction.y), direction.z)
    rotation = Quaternion((0, 0, 1), azimuth) @ Quaternion((0, 1, 0), polar)
    return Vector(pivot) + direction * .5, rotation, (1, 1, direction.length / rest_length)


def render(args):
    out = args.out_dir.resolve(); out.mkdir(parents=True, exist_ok=True)
    cache = out / 'physics_transforms.json'
    if args.physics_json:
        if any(getattr(args, k) is not None for k in
               ('scenario_json', 'scenario_overrides_json', 'fps', 'duration_sec', 'slow_motion', *BASELINE_PHYSICS)):
            raise ValueError('Resimulate to change cached physics or timing')
        data = json.loads(args.physics_json.read_text(encoding='utf-8')); validate_cache(data)
        if args.physics_json.resolve() != cache:
            shutil.copy2(args.physics_json, cache)
    else:
        command = [str(args.physics_python), str(Path(__file__).with_name('simulate_pendulum_box_collision.py')),
                   '--out', str(cache)]
        for key in ('scenario_json', 'scenario_overrides_json', 'fps', 'duration_sec', 'slow_motion',
                    *BASELINE_PHYSICS):
            value = getattr(args, key)
            if value is not None:
                command += ['--' + key.replace('_', '-'), str(value)]
        subprocess.run(command, check=True)
    data = json.loads(cache.read_text(encoding='utf-8'))
    validate_cache(data)
    scenario = deepcopy(data['scenario'])
    for key in ('samples', 'resolution'):
        if getattr(args, key) is not None:
            scenario['render'][key] = getattr(args, key)
    validate(scenario)
    args.samples = scenario['render']['samples']; args.resolution = scenario['render']['resolution']

    import bpy
    from mathutils import Vector
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    device = configure_renderer(bpy, scene, args); configure_color(scene)
    objects, rig = build_room(bpy, data); configure_lighting(bpy, scene)
    thread = rig['thread']; pivot = rig['pivot']
    for frame in data['frames']:
        for name, obj in objects.items():
            state = frame[name]; q = state['quaternion_xyzw']
            obj.location = state['location']
            obj.rotation_mode = 'QUATERNION'; obj.rotation_quaternion = (q[3], q[0], q[1], q[2])
            obj.keyframe_insert('location', frame=frame['frame_index'])
            obj.keyframe_insert('rotation_quaternion', frame=frame['frame_index'])
        # The thread is aimed, not simulated: pivot -> bob centre is always the
        # rod's length, so only the direction needs a key.
        # atan2 remains accurate at the downward vertical. Retain the solver's
        # small out-of-plane drift and radial constraint error in the drawing.
        thread.location, thread.rotation_quaternion, thread.scale = thread_pose(
            pivot, frame['bob']['location'], rig['thread_length'])
        thread.keyframe_insert('location', frame=frame['frame_index'])
        thread.keyframe_insert('rotation_quaternion', frame=frame['frame_index'])
        thread.keyframe_insert('scale', frame=frame['frame_index'])
    for obj in [*objects.values(), thread]:
        for curve in obj.animation_data.action.fcurves:
            for key in curve.keyframe_points:
                key.interpolation = 'LINEAR'
    scene.frame_start = 1; scene.frame_end = data['frame_end']; scene.render.fps = data['playback_fps']

    camera_cfg = scenario['camera']
    bpy.ops.object.camera_add(location=camera_cfg['location']); camera = bpy.context.object
    camera.rotation_euler = (Vector(camera_cfg['target']) - camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera.data.type = 'ORTHO'; camera.data.ortho_scale = camera_cfg['ortho_scale']; scene.camera = camera
    scene.render.resolution_x, scene.render.resolution_y = args.resolution
    scene.render.resolution_percentage = 100
    scene.render.use_persistent_data = True
    scene.render.image_settings.file_format = 'PNG'

    if not 1 <= args.preview_frame <= scene.frame_end:
        raise ValueError('Preview frame outside trajectory')
    checked = sorted({1, max(1, data['frame_end'] // 4), max(1, data['frame_end'] // 2),
                      max(1, 3 * data['frame_end'] // 4), data['frame_end']})
    maximum = 0.
    for number in checked:
        scene.frame_set(number); bpy.context.view_layer.update()
        frame = data['frames'][number - 1]
        for name, obj in objects.items():
            expected = frame[name]['matrix_world']
            maximum = max(maximum, max(abs(obj.matrix_world[i][j] - expected[i][j])
                                       for i in range(4) for j in range(4)))
        # The drawn thread must land on the bob the cache says is there.
        expected_end = Vector(frame['bob']['location'])
        drawn_end = thread.matrix_world @ Vector((0, 0, rig['thread_length'] / 2))
        maximum = max(maximum, max(abs(a - b) for a, b in zip(drawn_end, expected_end)))
    if maximum > 1e-5:
        raise RuntimeError(f'Rendered animation differs from simulated transforms: {maximum:.9g} at checked frames {checked}')
    write_json(out / 'render_validation.json',
               dict(valid=True, checked_frames=checked, max_matrix_error=maximum))

    scene.frame_set(args.preview_frame); bpy.context.view_layer.update()
    scenario['render'].update(mode=args.mode, engine=args.engine, device=device,
                              environment_theme=ENVIRONMENT_THEME, appearance_version=APPEARANCE_VERSION)
    matrix = [list(row) for row in camera.matrix_world]
    gt = dict(schema_version=1, scene=data['scene'], fps=data['playback_fps'],
              frame_start=1, frame_end=data['frame_end'],
              physics={key: value for key, value in data.items() if key != 'frames'},
              scenario=scenario,
              objects={key: dict(meta, object_name=objects[key].name) for key, meta in data['objects'].items()},
              camera=dict(object_name=camera.name, matrix_world=matrix, projection='orthographic',
                          ortho_scale=camera.data.ortho_scale, resolution=args.resolution),
              sample_fps=data['sample_fps'], slow_motion=data['slow_motion'],
              physical_duration_sec=data['physical_duration_sec'],
              playback_duration_sec=data['playback_duration_sec'],
              frames=[dict(frame, camera_matrix_world=matrix) for frame in data['frames']])
    write_json(out / 'ground_truth_transforms.json', gt)
    write_json(out / 'scenario_metadata.json', scenario)
    bpy.ops.wm.save_as_mainfile(filepath=str(out / 'pendulum_box_collision.blend'))

    if args.mode == 'sampled':
        if not 2 <= args.frame_count <= scene.frame_end:
            raise ValueError('Frame count must be between 2 and trajectory length')
        indices = (sorted(set(args.frame_indices)) if args.frame_indices else
                   [1 + round(i * (scene.frame_end - 1) / (args.frame_count - 1)) for i in range(args.frame_count)])
        if any(index < 1 or index > scene.frame_end for index in indices):
            raise ValueError('Sample frame outside trajectory')
        for index in indices:
            scene.frame_set(index); scene.render.filepath = str(out / f'frame_{index:04d}.png')
            bpy.ops.render.render(write_still=True)
        write_json(out / 'sampled_frames.json', dict(frame_indices=indices, frame_end=scene.frame_end))
    else:
        scene.render.filepath = str(out / 'preview.png')
        bpy.ops.render.render(write_still=True)
    if args.mode == 'animation':
        folder = out / 'frames'; folder.mkdir(exist_ok=True)
        scene.render.filepath = str(folder / 'frame_')
        bpy.ops.render.render(animation=True)
        ffmpeg = shutil.which('ffmpeg')
        if not ffmpeg:
            import imageio_ffmpeg
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run([ffmpeg, '-y', '-framerate', str(data['playback_fps']), '-i',
                        str(folder / 'frame_%04d.png'), '-frames:v', str(data['frame_end']),
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(out / 'video.mp4')], check=True)
        shutil.copy2(out / 'video.mp4', out / 'pendulum_box_collision.mp4')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out-dir', type=Path, required=True); p.add_argument('--physics-json', type=Path)
    p.add_argument('--scenario-json', type=Path); p.add_argument('--scenario-overrides-json', type=Path)
    p.add_argument('--physics-python', type=Path, default=python_for('physics'))
    p.add_argument('--fps', type=int); p.add_argument('--duration-sec', type=float)
    p.add_argument('--slow-motion', type=int, choices=(1, 2, 4, 8))
    for key in BASELINE_PHYSICS:
        p.add_argument('--' + key.replace('_', '-'), type=float)
    p.add_argument('--samples', type=int); p.add_argument('--resolution', type=int, nargs=2)
    p.add_argument('--engine', choices=('cycles', 'eevee'), default='cycles')
    p.add_argument('--device', choices=('auto', 'cpu'), default='auto')
    p.add_argument('--mode', choices=('preview', 'animation', 'sampled'), default='preview')
    p.add_argument('--preview-frame', type=int, default=1); p.add_argument('--frame-count', type=int, default=6)
    p.add_argument('--frame-indices', type=int, nargs='+', help='Explicit frames for sampled mode')
    args = parse_render_args(p, sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else None)
    render(args)


if __name__ == '__main__':
    run_renderer(main, 'pendulum_box_collision')

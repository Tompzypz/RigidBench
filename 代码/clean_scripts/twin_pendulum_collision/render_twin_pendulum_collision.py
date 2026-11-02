"""Blender replay: all moving geometry is driven by the verified physics cache."""

# Load this seven-file scene bundle and the reference common scripts.
import sys as _clean_sys
from pathlib import Path as _CleanPath
_clean_scene_dir = _CleanPath(__file__).resolve().parent
_clean_scripts_dir = _clean_scene_dir.parent
_PCVE_PROJECT_ROOT = next(p for p in _clean_scene_dir.parents if (p / "assets").is_dir())
if str(_clean_scripts_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_clean_scripts_dir))
if str(_clean_scene_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_clean_scene_dir))
import edit_vocab as _clean_scene_bundle
_clean_scene_bundle.install_scene_support()

import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys

from twin_pendulum_collision.runtime_support import python_for, parse_render_args, run_renderer
from twin_pendulum_collision.scene_config import add_scenario_arguments
from twin_pendulum_collision.cache_contract import validate_cache
from twin_pendulum_collision.scene_geometry import PIVOTS, BOB_RADIUS, KEYS
from twin_pendulum_collision.scene_environment import build_environment, make_pendulums, APPEARANCE_VERSION
from pcve_render_quality import configure_renderer, configure_color


def render(args):
    import bpy
    from mathutils import Vector
    if args.samples < 1 or any(v <= 0 for v in args.resolution):
        raise ValueError('Samples and resolution must be positive')
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    physics = args.physics_json.resolve() if args.physics_json else out / 'physics_transforms.json'
    scenario_keys = ('scenario_json', 'scenario_overrides_json', 'driver_mass', 'initial_angle_deg',
                     'drag_coefficient', 'fps', 'duration_sec', 'slow_motion')
    if args.physics_json:
        if any(getattr(args, key) is not None for key in scenario_keys):
            raise ValueError('Resimulate to change physics or timing when using --physics-json')
    else:
        command = [str(args.physics_python or python_for('physics')), str(Path(__file__).with_name('simulate_twin_pendulum_collision.py')), '--out', str(physics)]
        for key in scenario_keys:
            value = getattr(args, key)
            if value is not None:
                command += ['--' + key.replace('_', '-'), str(value)]
        subprocess.run(command, check=True)
    data = json.loads(physics.read_text(encoding='utf-8'))
    validate_cache(data)
    if physics != out / 'physics_transforms.json':
        shutil.copy2(physics, out / 'physics_transforms.json')
    (out / 'simulation_metrics.json').write_text(json.dumps(data['quality'], indent=2), encoding='utf-8')
    s = deepcopy(data['scenario'])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    device = configure_renderer(bpy, scene, args)
    configure_color(scene)
    scene.render.resolution_x, scene.render.resolution_y = args.resolution
    scene.render.resolution_percentage = 100
    scene.render.use_persistent_data = True  # keep scene data between frames; avoids per-frame resync/BVH rebuild
    scene.render.fps = data['playback_fps']
    scene.frame_start, scene.frame_end = 1, data['frame_end']
    mats = build_environment(bpy, scene)
    balls, rods, moving = make_pendulums(bpy, mats, data['frames'][0])
    for frame in data['frames']:
        index = frame['frame_index']
        for i, key in enumerate(KEYS):
            if key not in balls or not frame[key]['present']:
                continue
            obj, state = balls[key], frame[key]
            obj.location = state['location']
            q = state['quaternion_xyzw']
            obj.rotation_mode = 'QUATERNION'
            obj.rotation_quaternion = (q[3], q[0], q[1], q[2])
            obj.keyframe_insert('location', frame=index)
            obj.keyframe_insert('rotation_quaternion', frame=index)
            a = Vector(PIVOTS[i])
            pos = Vector(state['location'])
            end = pos + (a - pos).normalized() * (BOB_RADIUS + .005)
            rod = rods[key]
            rod.location = (a + end) / 2
            rod.scale.z = (a - end).length
            # The rod and bob share R_y(-theta). Use the simulated half-angle
            # quaternion directly: track-to loses precision for almost vertical
            # rods during a free swing after the receiver has been removed.
            rod.rotation_quaternion = obj.rotation_quaternion.copy()
            for prop in ('location', 'scale', 'rotation_quaternion'):
                rod.keyframe_insert(prop, frame=index)
    for obj in [*balls.values(), *rods.values()]:
        for curve in obj.animation_data.action.fcurves:
            for keyframe in curve.keyframe_points:
                keyframe.interpolation = 'LINEAR'
    # Whole-clip deletions never create a model. Mid-run deletions hide the
    # sphere, rod, socket and pivot eye together, with no fade interpolation.
    for key, ball in balls.items():
        gone_at = next((f['frame_index'] for f in data['frames'] if not f[key]['present']), None)
        if gone_at is None:
            continue
        for obj in [ball, rods[key], *ball.children_recursive]:
            for prop in ('hide_render', 'hide_viewport'):
                setattr(obj, prop, False)
                obj.keyframe_insert(prop, frame=gone_at - 1)
                setattr(obj, prop, True)
                obj.keyframe_insert(prop, frame=gone_at)
            for curve in obj.animation_data.action.fcurves:
                if curve.data_path in ('hide_render', 'hide_viewport'):
                    for point in curve.keyframe_points:
                        point.interpolation = 'CONSTANT'
    camera_config = s['camera']
    bpy.ops.object.camera_add(location=camera_config['location'])
    camera = bpy.context.object
    camera.name = 'Laboratory camera'
    camera.data.lens = camera_config['lens_mm']
    camera.rotation_euler = (Vector(camera_config['target']) - camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera.data.dof.use_dof = True
    camera.data.dof.focus_distance = (Vector(camera_config['target']) - camera.location).length
    camera.data.dof.aperture_fstop = 10
    scene.camera = camera
    bpy.context.view_layer.update()
    camera_matrix = [list(row) for row in camera.matrix_world]
    # Validate every frame: bob matrices and the exact endpoints of both rods.
    max_error, max_rod_error = 0., 0.
    visibility_checks = 0
    for frame in data['frames']:
        scene.frame_set(frame['frame_index'])
        bpy.context.view_layer.update()
        for i, key in enumerate(KEYS):
            present = frame[key]['present']
            if key not in balls:
                if present:
                    raise RuntimeError('A present pendulum has no render object')
                continue
            parts = [balls[key], rods[key], *balls[key].children_recursive]
            if any(part.hide_render != (not present) or part.hide_viewport != (not present) for part in parts):
                raise RuntimeError(f'Visibility differs from physics at frame {frame["frame_index"]}: {key}')
            visibility_checks += len(parts)
            if not present:
                continue
            expected = frame[key]['matrix_world']
            max_error = max(max_error, max(abs(balls[key].matrix_world[a][b] - expected[a][b]) for a in range(4) for b in range(4)))
            rod = rods[key]
            ends = [rod.matrix_world @ Vector([0, 0, z]) for z in (-.5, .5)]
            anchor = Vector(PIVOTS[i])
            pos = Vector(frame[key]['location'])
            target = pos + (anchor - pos).normalized() * (BOB_RADIUS + .005)
            max_rod_error = max(max_rod_error, min((ends[0]-anchor).length + (ends[1]-target).length,
                                                   (ends[1]-anchor).length + (ends[0]-target).length))
    if max_error > 2e-6 or max_rod_error > 1e-5:
        raise RuntimeError(f'Blender replay differs: bob={max_error}, rod={max_rod_error}')
    s['render'].update(resolution=args.resolution, samples=args.samples, engine=args.engine, device=device,
                       mode=args.mode, appearance_version=APPEARANCE_VERSION)
    gt = dict(schema_version=1, scene=data['scene'], fps=scene.render.fps, frame_start=1, frame_end=data['frame_end'],
              scenario=s, physics={k: v for k, v in data.items() if k != 'frames'},
              objects={key: dict(meta, object_name=balls[key].name if key in balls else None)
                       for key, meta in data['objects'].items()},
              camera=dict(object_name=camera.name, lens_mm=camera.data.lens, sensor_width_mm=camera.data.sensor_width,
                          resolution=args.resolution, matrix_world=camera_matrix),
              sample_fps=data['sample_fps'], slow_motion=data['slow_motion'],
              physical_duration_sec=data['physical_duration_sec'], playback_duration_sec=data['playback_duration_sec'],
              frames=[dict(frame, camera_matrix_world=camera_matrix) for frame in data['frames']])
    for name, payload in (('ground_truth_transforms.json', gt), ('scenario_metadata.json', s),
                          ('render_validation.json', dict(valid=True, checked_frames=len(data['frames']), objects_checked=len(balls),
                                                         visibility_checks=visibility_checks,
                                                         max_matrix_error=max_error, max_rod_endpoint_error_m=max_rod_error,
                                                         appearance_version=APPEARANCE_VERSION))):
        (out / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    impact = data['quality']['events']['first_ball_impact_sec']
    preview = args.preview_frame or min(scene.frame_end, round(((impact or 0) + .23) * data['sample_fps']) + 1)
    removed_frame = data['quality']['events'].get('receiver_removed_frame')
    if not args.preview_frame and removed_frame:
        preview = min(scene.frame_end, removed_frame + round(.15 * data['sample_fps']))
    if not 1 <= preview <= scene.frame_end:
        raise ValueError('Preview frame outside trajectory')
    scene.frame_set(preview)
    bpy.ops.file.pack_all()
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = str(out / 'preview.png')
    bpy.ops.render.render(write_still=True)
    if args.mode == 'animation':
        scene.render.image_settings.file_format = 'FFMPEG'
        scene.render.ffmpeg.format = 'MPEG4'
        scene.render.ffmpeg.codec = 'H264'
        scene.render.ffmpeg.constant_rate_factor = 'HIGH'
        scene.render.filepath = str(out / 'twin_pendulum_collision.mp4')
        scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(out / 'twin_pendulum_collision.blend'))
    if args.mode == 'animation':
        bpy.ops.render.render(animation=True)
        shutil.copy2(out / 'twin_pendulum_collision.mp4', out / 'video.mp4')


def main():
    parser = add_scenario_arguments(argparse.ArgumentParser(description=__doc__))
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--physics-json', type=Path)
    parser.add_argument('--physics-python', type=Path)
    parser.add_argument('--engine', choices=('cycles', 'eevee'), default='cycles')
    parser.add_argument('--device', choices=('auto', 'cpu'), default='auto')
    parser.add_argument('--samples', type=int, default=32)
    parser.add_argument('--resolution', type=int, nargs=2, default=[960, 540])
    parser.add_argument('--mode', choices=('preview', 'animation'), default='animation')
    parser.add_argument('--preview-frame', type=int)
    render(parse_render_args(parser))


if __name__ == '__main__':
    run_renderer(main, 'twin_pendulum_collision')

"""Blender replay of PyBullet transforms; keyframe rendering is the default."""
# PCVE_UNIFIED_ENTRY_BEGIN
from __future__ import annotations

# Resolve the shared scripts directory, then this scene's module folders.
import sys as _clean_sys
from pathlib import Path as _CleanPath
_clean_scene_dir = _CleanPath(__file__).resolve().parent
_scripts_dir = _clean_scene_dir.parents[1]
_PCVE_PROJECT_ROOT = next(p for p in _clean_scene_dir.parents if (p / "assets").is_dir())
# sys.argv[0] must point at this scene script BEFORE importing edit_vocab:
# the bundle triggers load_scenario() at module level, and top-level
# shared modules (scene_config/scenario_io) locate the scene folder via
# sys.argv[0], which under `blender -b` is the blender binary.
_clean_sys.argv[0] = str(_CleanPath(__file__).resolve())
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


import argparse
import json
import subprocess
import sys
from pathlib import Path
import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
from scene_config import MODELS, load_scenario, write_json, runtime
from look_basketball_corner_rebound import build_room, import_ball, aim

def keyframes(data):
    values={1, data['frame_end']}
    for event in data['metrics']['wall_collisions'][:2]:
        f=event['frame_index']
        values.update((max(1,f-2), f, min(data['frame_end'],f+3)))
    return sorted(values)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir',type=Path,required=True)
    parser.add_argument('--scenario-overrides-json',type=Path)
    parser.add_argument('--mode',choices=('build','preview','keyframes','animation'),default='keyframes')
    parser.add_argument('--keyframes')
    parser.add_argument('--resolution',nargs=2,type=int,default=(960,540))
    parser.add_argument('--samples',type=int,default=24)
    parser.add_argument('--threads',type=int,default=4,help='Limit CPU load on the local computer')
    parser.add_argument('--engine',choices=('cycles','eevee'),default='cycles')
    parser.add_argument('--device',choices=('auto','cpu'),default='cpu')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None)
    out=args.out_dir.resolve()
    out.mkdir(parents=True,exist_ok=True)
    scenario=load_scenario(args.scenario_overrides_json)
    write_json(out/'scenario_input.json',scenario)
    # Always simulate the resolved input; an older trajectory cannot silently survive an edit.
    # The simulator next to this file, not whatever ``scene_config`` finds first
    # (a legacy copy lives under new-scripts/ and knows nothing of these edits).
    command=[runtime('sim'),str(Path(__file__).resolve().with_name('simulate_basketball_corner_rebound.py')),
             '--out',str(out/'physics_transforms.json')]
    if args.scenario_overrides_json:
        command+=['--scenario-overrides-json',str(args.scenario_overrides_json.resolve())]
    subprocess.run(command,check=True)
    data=json.loads((out/'physics_transforms.json').read_text(encoding='utf-8'))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene=bpy.context.scene
    scene.render.engine='CYCLES' if args.engine=='cycles' else 'BLENDER_EEVEE_NEXT'
    scene.cycles.samples=args.samples
    scene.cycles.use_denoising=True
    scene.cycles.device='CPU'
    if scene.cycles.device != 'CPU' or args.device == 'auto':
        prefs = bpy.context.preferences.addons['cycles'].preferences
        try:
            prefs.compute_device_type = 'CUDA'; prefs.get_devices()
            available = [dev for dev in prefs.devices if dev.type == 'CUDA']
            for dev in prefs.devices:
                dev.use = (dev.type == 'CUDA')
            if available and args.device == 'auto':
                scene.cycles.device = 'GPU'
                print('[render] CUDA: ' + ', '.join(dev.name for dev in available), flush=True)
        except Exception as exc:
            scene.cycles.device = 'CPU'
            print('[render] CPU fallback: ' + str(exc), flush=True)
    scene.render.threads_mode='FIXED'
    scene.render.threads=max(1,args.threads)
    scene.render.resolution_x,scene.render.resolution_y=args.resolution
    scene.render.resolution_percentage=100
    scene.render.fps=data['fps']
    scene.frame_start,scene.frame_end=1,data['frame_end']
    scene.render.image_settings.file_format='PNG'
    scene.view_settings.view_transform='AgX'
    scene.view_settings.look='AgX - Medium High Contrast'
    scene.view_settings.exposure=.35
    scene.render.film_transparent=False
    build_room(scenario)
    ball=import_ball(MODELS/scenario['assets']['ball'],scenario['physics']['ball_radius'])
    ball.rotation_mode='QUATERNION'
    for row in data['frames']:
        ball.location=row['ball_location']
        x,y,z,w=row['ball_quaternion_xyzw']
        ball.rotation_quaternion=(w,x,y,z)
        ball.keyframe_insert('location',frame=row['frame_index'])
        ball.keyframe_insert('rotation_quaternion',frame=row['frame_index'])
    for curve in ball.animation_data.action.fcurves:
        for key in curve.keyframe_points:
            key.interpolation='LINEAR'
    cam_data=bpy.data.cameras.new('Room camera')
    cam=bpy.data.objects.new('Room camera',cam_data)
    bpy.context.collection.objects.link(cam)
    scene.camera=cam
    cam.location=scenario['render']['camera_location']
    # A room corner reads as a falling-over box when the camera is pitched: the
    # verticals of every window and door keystone inwards. ``level_camera``
    # keeps the optical axis on the horizon so verticals stay vertical, and the
    # lost tilt is put back as a lens shift, which moves the framing without
    # moving the perspective.
    look_at=scenario['render']['camera_target']
    if scenario['render'].get('level_camera'):
        look_at=(look_at[0],look_at[1],cam.location[2])
    aim(cam,look_at)
    cam_data.lens=scenario['render']['lens_mm']
    cam_data.shift_y=scenario['render'].get('shift_y',0.0)
    cam_data.clip_start=.05
    cam_data.clip_end=100
    cam_data.dof.use_dof=False
    # Validate every rendered frame against the same physical sphere.
    validation=[]
    ground=[]
    r=scenario['physics']['ball_radius']
    for row in data['frames']:
        f=row['frame_index']
        scene.frame_set(f)
        pos=ball.matrix_world.translation
        error=(pos-Vector(row['ball_location'])).length
        points=[world_to_camera_view(scene,cam,pos+Vector(offset)) for offset in
            ((r,0,0),(-r,0,0),(0,r,0),(0,-r,0),(0,0,r),(0,0,-r))]
        inside=all(p.z>0 and 0<=p.x<=1 and 0<=p.y<=1 for p in points)
        deps=bpy.context.evaluated_depsgraph_get()
        direction=pos-cam.location
        hit,point,normal,index,obj,matrix=scene.ray_cast(deps,cam.location,direction.normalized(),distance=direction.length+r)
        visible=bool(hit and obj and obj.original==ball)
        validation.append({'frame_index':f,'position_error_m':error,'sphere_in_frame':inside,'center_visible':visible})
        ground.append({'frame_index':f,'time_sec':row['time_sec'],'basketball':{
            'location':list(pos),'quaternion_xyzw':row['ball_quaternion_xyzw'],'radius_m':r}})
    write_json(out/'ground_truth_transforms.json',{'fps':data['fps'],'frames':ground})
    write_json(out/'render_validation.json',{'all_frames_in_view':all(v['sphere_in_frame'] for v in validation),
        'all_centers_visible':all(v['center_visible'] for v in validation),
        'max_position_error_m':max(v['position_error_m'] for v in validation),'frames':validation})
    write_json(out/'scenario_metadata.json',{'scene':scenario['scene'],'duration_sec':data['duration_sec'],
        'frame_count':data['frame_end'],'assets':{'ball':str(MODELS/scenario['assets']['ball']),
        'room':'Procedural metre-scale plaster room; visible impact faces match PyBullet planes'},
        'physics':'Free PyBullet sphere; immutable walls; no added forces or retiming',
        'camera_location':list(cam.location),'camera_lens_mm':cam_data.lens,'mode':args.mode})
    selected=[int(s) for s in args.keyframes.split(',')] if args.keyframes else keyframes(data)
    if any(f<1 or f>scene.frame_end for f in selected):
        raise ValueError('Keyframes outside simulation range')
    write_json(out/'keyframes.json',{'frames':selected,'wall_collisions':data['metrics']['wall_collisions']})
    scene.frame_set(1)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'basketball_corner_rebound.blend'))
    if args.mode=='animation':
        scene.render.image_settings.file_format='FFMPEG'
        scene.render.ffmpeg.format='MPEG4'
        scene.render.ffmpeg.codec='H264'
        scene.render.filepath=str(out/'video.mp4')
        bpy.ops.render.render(animation=True)
    elif args.mode!='build':
        for f in ([selected[0]] if args.mode=='preview' else selected):
            scene.frame_set(f)
            scene.render.filepath=str(out/f'frame_{f:04d}.png')
            bpy.ops.render.render(write_still=True)
    print(f'Completed {out}')

if __name__=='__main__':
    main()

"""Replay a signed PyBullet cache in Blender, render stills or a four-second clip."""

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
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
from soccer_step_collision.runtime_support import HERE, MODELS, python_for
from soccer_step_collision.scene_config import load_scenario, write_json
from soccer_step_collision.scene_geometry import KEYS, RADII
from soccer_step_collision.cache_contract import validate_cache

def keyframes(data):
    n=data['frame_end']; frames={1,n}
    for e in data['events']:
        f=e['frame_index']; frames.add(f)
        if e['event']=='ball_collision': frames.add(min(n,f+8))
    if data['quality']['climb_time_sec'] is not None:
        frames.add(min(n,1+math.ceil(data['quality']['climb_time_sec']*data['fps'])))
    return sorted(frames)

def render(args):
    import bpy
    from bpy_extras.object_utils import world_to_camera_view
    from mathutils import Vector
    from soccer_step_collision.scene_environment import build_room, make_ball, aim, PLANT_ASSET, PLANT_HEIGHT_M, PLANT_POSITION_XY, PLANT_ROTATION_DEG
    out=args.out_dir.resolve(); out.mkdir(parents=True,exist_ok=True)
    physics=args.physics_json or out/'physics_transforms.json'
    if args.physics_json is None:
        command=[str(args.physics_python or python_for('physics')),str(HERE/'simulate_soccer_step_collision.py'),'--out',str(physics)]
        if args.scenario_json: command+=['--scenario-json',str(args.scenario_json.resolve())]
        if args.scenario_overrides_json: command+=['--scenario-overrides-json',str(args.scenario_overrides_json.resolve())]
        subprocess.run(command,check=True)
    data=json.loads(physics.read_text(encoding='utf-8')); validate_cache(data)
    s=data['scenario']
    if args.scenario_json or args.scenario_overrides_json:
        requested=load_scenario(args.scenario_json,args.scenario_overrides_json)
        if requested != s: raise ValueError('Cache does not match requested scenario')
    write_json(out/'scenario_input.json',s)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene=bpy.context.scene
    scene.render.engine='CYCLES' if args.engine=='cycles' else 'BLENDER_EEVEE_NEXT'
    scene.cycles.device='CPU'; scene.cycles.samples=args.samples
    if args.device=='auto':
        _prefs=bpy.context.preferences.addons['cycles'].preferences
        for _backend in ('OPTIX','CUDA'):
            try:
                _prefs.compute_device_type=_backend; _prefs.get_devices()
            except (TypeError,RuntimeError):
                continue
            _devs=[d for d in _prefs.devices if d.type==_backend]
            if _devs:
                for _d in _prefs.devices: _d.use=(_d.type==_backend)
                scene.cycles.device='GPU'
                print(f'[render] {_backend}: '+', '.join(d.name for d in _devs),flush=True)
                break
    scene.cycles.use_denoising=True; scene.cycles.adaptive_threshold=.04
    scene.cycles.max_bounces=7; scene.cycles.diffuse_bounces=4; scene.cycles.glossy_bounces=4
    scene.render.threads_mode='FIXED'; scene.render.threads=args.threads
    scene.render.resolution_x,scene.render.resolution_y=args.resolution
    scene.render.resolution_percentage=100; scene.render.fps=data['fps']
    scene.render.use_persistent_data=True  # keep scene data between frames; avoids per-frame resync/BVH rebuild
    scene.frame_start=1; scene.frame_end=data['frame_end']
    scene.render.image_settings.file_format='PNG'; scene.render.image_settings.color_mode='RGB'
    scene.render.film_transparent=False; scene.render.use_persistent_data=True
    scene.view_settings.view_transform='AgX'; scene.view_settings.look='AgX - Medium High Contrast'
    scene.view_settings.exposure=.55
    build_room(s)
    balls={k:make_ball(name,k,RADII[i]) for i,(k,name) in enumerate(zip(KEYS,('cheap_soccer_ball.glb','basketball.glb')))}
    for key,ball in balls.items():
        ball.rotation_mode='QUATERNION'
        for row in data['frames']:
            state=row[key]; ball.location=state['location']; x,y,z,w=state['quaternion_xyzw']
            ball.rotation_quaternion=(w,x,y,z)
            ball.keyframe_insert('location',frame=row['frame_index'])
            ball.keyframe_insert('rotation_quaternion',frame=row['frame_index'])
        for curve in ball.animation_data.action.fcurves:
            for point in curve.keyframe_points: point.interpolation='LINEAR'
    cam_data=bpy.data.cameras.new('Fixed architectural camera')
    cam=bpy.data.objects.new('Fixed architectural camera',cam_data); bpy.context.collection.objects.link(cam)
    scene.camera=cam; cam.location=s['camera']['location']; aim(cam,s['camera']['target'])
    cam_data.lens=s['camera']['lens_mm']; cam_data.clip_start=.03; cam_data.clip_end=100
    cam_data.dof.use_dof=False
    checks=[]; ground=[]
    for row in data['frames']:
        scene.frame_set(row['frame_index']); deps=bpy.context.evaluated_depsgraph_get()
        record={'frame_index':row['frame_index'],'time_sec':row['time_sec']}
        for i,key in enumerate(KEYS):
            obj=balls[key]; pos=obj.matrix_world.translation; radius=RADII[i]
            # Check the entire bounding cube, which conservatively contains the sphere.
            projected=[world_to_camera_view(scene,cam,pos+Vector((a*radius,b*radius,c*radius)))
                       for a in (-1,1) for b in (-1,1) for c in (-1,1)]
            inside=all(p.z>0 and 0<=p.x<=1 and 0<=p.y<=1 for p in projected)
            direction=pos-cam.location
            hit,_,_,_,ob,_=scene.ray_cast(deps,cam.location,direction.normalized(),distance=direction.length+radius)
            visible=bool(hit and ob and ob.original==obj)
            error=(pos-Vector(row[key]['location'])).length
            checks.append(dict(frame=row['frame_index'],object=key,in_frame=inside,center_visible=visible,position_error_m=error))
            record[key]=dict(location=list(pos),quaternion_xyzw=row[key]['quaternion_xyzw'],matrix_world=[list(v) for v in obj.matrix_world])
        ground.append(record)
    validation=dict(all_frames_in_view=all(v['in_frame'] for v in checks),
        all_centers_visible=all(v['center_visible'] for v in checks),
        max_replay_error_m=max(v['position_error_m'] for v in checks),frames=checks)
    write_json(out/'render_validation.json',validation)
    write_json(out/'ground_truth_transforms.json',dict(scene=data['scene'],fps=data['fps'],frames=ground,
        camera=dict(matrix_world=[list(v) for v in cam.matrix_world],lens_mm=cam_data.lens),objects=data['objects']))
    if not validation['all_frames_in_view'] or validation['max_replay_error_m']>1e-5:
        raise RuntimeError('Camera framing or physical replay validation failed; see render_validation.json')
    selected=args.keyframes or keyframes(data)
    if any(f<1 or f>data['frame_end'] for f in selected): raise ValueError('Keyframe out of range')
    preview=args.preview_frame or min(data['frame_end'],72)
    if not 1<=preview<=data['frame_end']: raise ValueError('Preview outside clip')
    write_json(out/'keyframes.json',dict(frames=selected,events=data['events'],preview_frame=preview))
    write_json(out/'scenario_metadata.json',dict(scene=data['scene'],duration_sec=data['duration_sec'],
        frame_count=data['frame_end'],fps=data['fps'],simulation_signature=data['simulation_signature'],
        assets={k:str(MODELS/n) for k,n in [('soccer','cheap_soccer_ball.glb'),('basketball','basketball.glb'),('plant',PLANT_ASSET)]},
        plant=dict(height_m=PLANT_HEIGHT_M,pot_base_location=[*PLANT_POSITION_XY,s['physics']['step_height']],
            rotation_deg=PLANT_ROTATION_DEG,outer_planter_height_m=.285,
            styling='Original scan mesh/UV, corrected leaf and stem colours, matte ceramic outer planter',
            scaling='uniform; original scan proportions retained'),
        architecture='Locally authored split-level sitting room, SI scale, scanned concrete and oak',
        physics='Initial velocity and spin only; unforced PyBullet contacts, full 3D',render_mode=args.mode,
        resolution=args.resolution,samples=args.samples,engine=args.engine))
    scene.frame_set(1); bpy.ops.file.pack_all()
    scene.render.filepath=str(out/'frames/frame_')
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'soccer_step_collision.blend'))
    if args.mode=='animation':
        scene.render.image_settings.file_format='FFMPEG'; scene.render.ffmpeg.format='MPEG4'
        scene.render.ffmpeg.codec='H264'; scene.render.ffmpeg.constant_rate_factor='HIGH'
        scene.render.filepath=str(out/'video.mp4'); bpy.ops.render.render(animation=True)
    elif args.mode!='build':
        for f in ([preview] if args.mode=='preview' else selected):
            scene.frame_set(f); scene.render.filepath=str(out/f'frame_{f:04d}.png')
            bpy.ops.render.render(write_still=True)
        available=[f for f in ([preview] if args.mode=='preview' else selected)]
        chosen=min(available,key=lambda f:abs(f-preview))
        shutil.copy2(out/f'frame_{chosen:04d}.png',out/'preview.png')
    print('Completed '+str(out),flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out-dir',type=Path,required=True); p.add_argument('--physics-json',type=Path)
    p.add_argument('--scenario-json',type=Path); p.add_argument('--scenario-overrides-json',type=Path)
    p.add_argument('--physics-python',type=Path)
    p.add_argument('--resolution',type=int,nargs=2,default=[960,540]); p.add_argument('--samples',type=int,default=32)
    p.add_argument('--engine',choices=('cycles','eevee'),default='cycles')
    p.add_argument('--device',choices=('cpu','auto'),default='cpu')
    p.add_argument('--threads',type=int,default=4)
    p.add_argument('--mode',choices=('build','preview','keyframes','animation'),default='keyframes')
    p.add_argument('--keyframes',nargs='+',type=int); p.add_argument('--preview-frame',type=int)
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None)
    if args.samples<1 or args.threads<1 or min(args.resolution)<16: raise ValueError('Invalid render settings')
    render(args)

if __name__=='__main__':
    from pcve_scene_runtime import run_renderer
    run_renderer(main,'soccer_step_collision')

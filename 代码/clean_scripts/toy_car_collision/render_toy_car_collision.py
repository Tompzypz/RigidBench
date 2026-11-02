"""Replay a four-second toy-car collision in the locally imported furnished room."""

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
import math
from pathlib import Path
import shutil
import subprocess
import sys
from toy_car_collision.runtime_support import python_for,parse_render_args,run_renderer
from toy_car_collision.scene_config import add_scenario_arguments,BASELINE_PHYSICS
from toy_car_collision.cache_contract import validate_cache
from toy_car_collision.scene_geometry import KEYS
from toy_car_collision.scene_environment import build_environment,make_cars,APPEARANCE_VERSION,MODELS,ROOM_ASSET,CAR_ASSET,RECEIVER_ASSET,ROOM_ORIGIN,ROOM_YAW
from pcve_render_quality import configure_renderer,configure_color


def render(args):
    import bpy
    from mathutils import Vector,Quaternion
    if args.samples<1 or min(args.resolution)<1:raise ValueError('Invalid render settings')
    out=args.out_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    physics=args.physics_json.resolve() if args.physics_json else out/'physics_transforms.json'
    scenario_keys=('scenario_json','scenario_overrides_json',*BASELINE_PHYSICS,'fps','duration_sec','slow_motion')
    if args.physics_json:
        if any(getattr(args,k,None) is not None for k in scenario_keys):raise ValueError('Resimulate before changing cached initial conditions/timing')
    else:
        command=[str(args.physics_python or python_for('physics')),str(Path(__file__).with_name('simulate_toy_car_collision.py')),'--out',str(physics)]
        for key in scenario_keys:
            value=getattr(args,key,None)
            if value is not None:command+=['--'+key.replace('_','-'),str(value)]
        subprocess.run(command,check=True)
    data=json.loads(physics.read_text(encoding='utf-8'));validate_cache(data)
    if physics!=out/'physics_transforms.json':shutil.copy2(physics,out/'physics_transforms.json')
    (out/'simulation_metrics.json').write_text(json.dumps(data['quality'],indent=2),encoding='utf-8')
    s=deepcopy(data['scenario'])
    bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene
    device=configure_renderer(bpy,scene,args);configure_color(scene)
    scene.view_settings.exposure=-.1
    scene.render.resolution_x,scene.render.resolution_y=args.resolution;scene.render.resolution_percentage=100
    scene.render.use_persistent_data=True  # keep scene data between frames; avoids per-frame resync/BVH rebuild
    scene.render.fps=data['playback_fps'];scene.frame_start=1;scene.frame_end=data['frame_end']
    build_environment(bpy,scene)
    bpy.context.view_layer.update()
    floor_checks=[]
    for x in (-.42,0.,.7,1.5):
        hit,location,normal,face,obj,matrix=scene.ray_cast(bpy.context.evaluated_depsgraph_get(),Vector((x,0,.18)),Vector((0,0,-1)))
        floor_checks.append(dict(x=x,hit=hit,height=location.z if hit else None,object=obj.name if obj else None))
    if any(not v['hit'] or abs(v['height'])>.002 for v in floor_checks):raise RuntimeError(f'Room floor does not support the car lane: {floor_checks}')
    objects,wheels=make_cars(bpy,s['physics']['present'])
    for f in data['frames']:
        for key in objects:
            o=objects[key];state=f[key];o.location=state['location'];q=state['quaternion_xyzw']
            o.rotation_mode='QUATERNION';o.rotation_quaternion=(q[3],q[0],q[1],q[2])
            o.keyframe_insert('location',frame=f['frame_index']);o.keyframe_insert('rotation_quaternion',frame=f['frame_index'])
            for wheel,radius in wheels[key]:
                distance=state['location'][0]-data['frames'][0][key]['location'][0]
                wheel.rotation_mode='QUATERNION';wheel.rotation_quaternion=Quaternion((1,0,0),distance/radius)
                wheel.keyframe_insert('rotation_quaternion',frame=f['frame_index'])
    for o in [*objects.values(),*[w for entries in wheels.values() for w,_ in entries]]:
        for curve in o.animation_data.action.fcurves:
            for k in curve.keyframe_points:k.interpolation='LINEAR'
    cam=s['camera'];bpy.ops.object.camera_add(location=cam['location']);camera=bpy.context.object
    if args.closeup:
        cam=dict(location=[-.28,-.75,.35],target=[-.10,0,.035],lens_mm=30)
        camera.location=cam['location']
    camera.name='Indoor toy-car camera';camera.data.lens=cam['lens_mm']
    camera.rotation_euler=(Vector(cam['target'])-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.dof.use_dof=True;camera.data.dof.focus_distance=(Vector(cam['target'])-camera.location).length
    camera.data.dof.aperture_fstop=7.1;scene.camera=camera
    bpy.context.view_layer.update();cm=[list(row) for row in camera.matrix_world]
    max_error=0.;view_bounds=[1.,1.,0.,0.]
    from bpy_extras.object_utils import world_to_camera_view
    for f in data['frames']:
        scene.frame_set(f['frame_index']);bpy.context.view_layer.update()
        for key in objects:
            max_error=max(max_error,max(abs(objects[key].matrix_world[a][b]-f[key]['matrix_world'][a][b]) for a in range(4) for b in range(4)))
            for child in objects[key].children_recursive:
                if child.type!='MESH':continue
                for corner in child.bound_box:
                    v=world_to_camera_view(scene,camera,child.matrix_world@Vector(corner))
                    view_bounds=[min(view_bounds[0],v.x),min(view_bounds[1],v.y),max(view_bounds[2],v.x),max(view_bounds[3],v.y)]
    if max_error>2e-6:raise RuntimeError(f'Blender replay differs from physics by {max_error}')
    if min(view_bounds[:2])<0 or max(view_bounds[2:])>1:raise RuntimeError(f'Car leaves the camera frame: {view_bounds}')
    metadata=deepcopy(s)
    metadata['render'].update(resolution=args.resolution,samples=args.samples,engine=args.engine,device=device,mode=args.mode)
    metadata['appearance_version']=APPEARANCE_VERSION
    metadata['camera']=cam
    metadata['wheel_animation']='Visual no-slip wheel rotation from signed body displacement; not a wheel-joint simulation.'
    metadata['assets']={n:str((MODELS/n).resolve()) for n in (ROOM_ASSET,CAR_ASSET,RECEIVER_ASSET)}
    metadata['room_transform']=dict(native_action_origin=ROOM_ORIGIN,yaw_radians=ROOM_YAW,description='Raised floor in front of the bed, viewed towards bed and computer desk')
    gt=dict(schema_version=1,scene=data['scene'],fps=scene.render.fps,frame_start=1,frame_end=data['frame_end'],
            scenario=metadata,physics={k:v for k,v in data.items() if k!='frames'},
            objects={k:dict(v,object_name=objects[k].name if k in objects else None) for k,v in data['objects'].items()},
            camera=dict(object_name=camera.name,matrix_world=cm,lens_mm=camera.data.lens,
                        sensor_width_mm=camera.data.sensor_width,resolution=args.resolution),
            sample_fps=data['sample_fps'],slow_motion=data['slow_motion'],
            physical_duration_sec=data['physical_duration_sec'],playback_duration_sec=data['playback_duration_sec'],
            frames=[dict(f,camera_matrix_world=cm) for f in data['frames']])
    for name,payload in [('ground_truth_transforms.json',gt),('scenario_metadata.json',metadata),
                         ('render_validation.json',dict(valid=True,checked_frames=len(data['frames']),objects_checked=len(objects),
                                                        max_matrix_error=max_error,car_screen_bounds=view_bounds,room_floor_checks=floor_checks,present_objects=len(objects),wheel_pairs={k:len(v) for k,v in wheels.items()},appearance_version=APPEARANCE_VERSION))]:
        (out/name).write_text(json.dumps(payload,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    preview=args.preview_frame or min(scene.frame_end,round(((data['quality']['first_impact_sec'] or 0)+.22)*data['sample_fps'])+1)
    if not 1<=preview<=scene.frame_end:raise ValueError('Preview frame outside trajectory')
    scene.frame_set(preview);bpy.ops.file.pack_all()
    scene.render.threads_mode='FIXED';scene.render.threads=6
    scene.render.image_settings.file_format='PNG';scene.render.filepath=str(out/'preview.png')
    if args.mode not in ('build','keyframes'):bpy.ops.render.render(write_still=True)
    if args.mode=='keyframes':
        impact=math.ceil((data['quality']['first_impact_sec'] or 0)*data['sample_fps'])+1
        indices=args.keyframes or [1,max(1,impact-1),impact,impact+5,round(2.5*data['sample_fps'])+1,scene.frame_end]
        if args.keyframes and any(not 1<=i<=scene.frame_end for i in indices):raise ValueError('Keyframe outside trajectory')
        indices=sorted({min(scene.frame_end,i) for i in indices})
        for index in indices:
            scene.frame_set(index);scene.render.filepath=str(out/f'frame_{index:04d}.png');bpy.ops.render.render(write_still=True)
        shutil.copy2(out/f'frame_{min(indices,key=lambda i:abs(i-preview)):04d}.png',out/'preview.png')
        (out/'keyframes.json').write_text(json.dumps([dict(frame=i,time_sec=(i-1)/data['sample_fps'],file=f'frame_{i:04d}.png') for i in indices],indent=2),encoding='utf-8')
    if args.mode=='animation':
        scene.render.image_settings.file_format='FFMPEG';scene.render.ffmpeg.format='MPEG4';scene.render.ffmpeg.codec='H264'
        scene.render.ffmpeg.constant_rate_factor='HIGH';scene.render.filepath=str(out/'toy_car_collision.mp4')
        scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'toy_car_collision.blend'))
    if args.mode=='animation':
        bpy.ops.render.render(animation=True);shutil.copy2(out/'toy_car_collision.mp4',out/'video.mp4')


def main():
    p=add_scenario_arguments(argparse.ArgumentParser(description=__doc__))
    p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--physics-json',type=Path)
    p.add_argument('--physics-python',type=Path);p.add_argument('--engine',choices=('cycles','eevee'),default='cycles')
    p.add_argument('--device',choices=('auto','cpu'),default='auto');p.add_argument('--samples',type=int,default=48)
    p.add_argument('--resolution',nargs=2,type=int,default=[960,540])
    p.add_argument('--mode',choices=('build','preview','keyframes','animation'),default='keyframes')
    p.add_argument('--preview-frame',type=int)
    p.add_argument('--closeup',action='store_true',help='Optional detail camera; use with baseline or small-displacement variants')
    p.add_argument('--keyframes',nargs='+',type=int,help='Frame indices for --mode keyframes')
    render(parse_render_args(p))


if __name__=='__main__':run_renderer(main,'toy_car_collision')

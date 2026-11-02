"""Render a scenario or replay cached poses, using the standard scene CLI."""

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




from pathlib import Path
from copy import deepcopy
import argparse,json,sys,subprocess,shutil
from scene_support.chalk_box_stack.runtime_support import python_for
from scene_support.chalk_box_stack.cache_contract import validate_cache
from scene_support.chalk_box_stack.scene_config import BASELINE_PHYSICS,validate
from scene_support.chalk_box_stack.scene_environment import build_room,configure_lighting,ENVIRONMENT_THEME,APPEARANCE_VERSION
from scene_support.chalk_box_stack.render_quality import configure_renderer,configure_color


from pcve_scene_runtime import parse_render_args, run_renderer

def write_json(path,data):
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')


def render(args):
    out=args.out_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    cache=out/'physics_transforms.json'
    if args.physics_json:
        if any(getattr(args,k,None) is not None for k in ('scenario_json','scenario_overrides_json','fps','duration_sec','slow_motion',*BASELINE_PHYSICS)):
            raise ValueError('Resimulate to change cached physics or timing')
        data=json.loads(args.physics_json.read_text(encoding='utf-8'));validate_cache(data)
        if args.physics_json.resolve()!=cache:shutil.copy2(args.physics_json,cache)
    else:
        command=[str(args.physics_python),str(Path(__file__).with_name('simulate_chalk_box_stack.py')),'--out',str(cache)]
        for key in ('scenario_json','scenario_overrides_json','fps','duration_sec',*BASELINE_PHYSICS):
            value=getattr(args,key)
            if value is not None:command+=['--'+key.replace('_','-'),str(value)]
        subprocess.run(command,check=True)
    data=json.loads(cache.read_text(encoding='utf-8'))
    validate_cache(data)
    write_json(out/'simulation_metrics.json',data['quality'])
    write_json(out/'motion_summary.json',data['motion_summary'])
    scenario=deepcopy(data['scenario'])
    for key in ('samples','resolution'):
        if getattr(args,key) is not None:scenario['render'][key]=getattr(args,key)
    validate(scenario);args.samples=scenario['render']['samples'];args.resolution=scenario['render']['resolution']
    import bpy
    from mathutils import Vector
    bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene
    device=configure_renderer(bpy,scene,args);configure_color(scene)
    objects=build_room(bpy,data);configure_lighting(bpy,scene)
    for frame in data['frames']:
        for name,obj in objects.items():
            state=frame[name];q=state['quaternion_xyzw'];obj.location=state['location']
            obj.rotation_mode='QUATERNION';obj.rotation_quaternion=(q[3],q[0],q[1],q[2])
            obj.keyframe_insert('location',frame=frame['frame_index']);obj.keyframe_insert('rotation_quaternion',frame=frame['frame_index'])
    for obj in objects.values():
        for curve in obj.animation_data.action.fcurves:
            for key in curve.keyframe_points:key.interpolation='LINEAR'
    scene.frame_start=1;scene.frame_end=data['frame_end'];scene.render.fps=data['playback_fps']
    camera_cfg=scenario['camera'];bpy.ops.object.camera_add(location=camera_cfg['location']);camera=bpy.context.object
    camera.rotation_euler=(Vector(camera_cfg['target'])-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.type='ORTHO';camera.data.ortho_scale=camera_cfg['ortho_scale'];scene.camera=camera
    scene.render.resolution_x,scene.render.resolution_y=args.resolution;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG'
    if not 1<=args.preview_frame<=scene.frame_end:raise ValueError('Preview frame outside trajectory')
    checked=sorted({1,max(1,data['frame_end']//4),max(1,data['frame_end']//2),max(1,3*data['frame_end']//4),data['frame_end']})
    maximum=0.
    for number in checked:
        scene.frame_set(number);bpy.context.view_layer.update()
        frame=data['frames'][number-1]
        for name,obj in objects.items():
            expected=frame[name]['matrix_world']
            maximum=max(maximum,max(abs(obj.matrix_world[i][j]-expected[i][j]) for i in range(4) for j in range(4)))
    if maximum>1e-5:raise RuntimeError('Rendered animation differs from simulated transforms')
    write_json(out/'render_validation.json',dict(valid=True,checked_frames=checked,max_matrix_error=maximum))
    scene.frame_set(args.preview_frame);bpy.context.view_layer.update()
    scenario['render'].update(mode=args.mode,engine=args.engine,device=device,environment_theme=ENVIRONMENT_THEME,appearance_version=APPEARANCE_VERSION)
    matrix=[list(row) for row in camera.matrix_world]
    gt=dict(schema_version=1,scene=data['scene'],fps=data['playback_fps'],frame_start=1,frame_end=data['frame_end'],
        physics={key:value for key,value in data.items() if key!='frames'},scenario=scenario,
        objects={key:dict(meta,object_name=objects[key].name) for key,meta in data['objects'].items()},
        camera=dict(object_name=camera.name,matrix_world=matrix,projection='orthographic',
                    ortho_scale=camera.data.ortho_scale,resolution=args.resolution),
        sample_fps=data['sample_fps'],slow_motion=data['slow_motion'],physical_duration_sec=data['physical_duration_sec'],playback_duration_sec=data['playback_duration_sec'],
        frames=[dict(frame,camera_matrix_world=matrix) for frame in data['frames']])
    write_json(out/'ground_truth_transforms.json',gt);write_json(out/'scenario_metadata.json',scenario)
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'chalk_box_stack.blend'))
    if args.mode=='sampled':
        if not 2<=args.frame_count<=scene.frame_end:raise ValueError('Frame count must be between 2 and trajectory length')
        indices=[1+round(i*(scene.frame_end-1)/(args.frame_count-1)) for i in range(args.frame_count)]
        for index in indices:
            scene.frame_set(index);scene.render.filepath=str(out/f'frame_{index:04d}.png');bpy.ops.render.render(write_still=True)
        write_json(out/'sampled_frames.json',dict(frame_indices=indices,frame_end=scene.frame_end))
    else:
        scene.render.filepath=str(out/'preview.png');bpy.ops.render.render(write_still=True)
    if args.mode=='animation':
        folder=out/'frames';folder.mkdir(exist_ok=True);scene.render.filepath=str(folder/'frame_')
        bpy.ops.render.render(animation=True)
        ffmpeg=shutil.which('ffmpeg')
        if not ffmpeg:
            import imageio_ffmpeg
            ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run([ffmpeg,'-y','-framerate',str(data['playback_fps']),'-i',str(folder/'frame_%04d.png'),'-frames:v',str(data['frame_end']),'-c:v','libx264','-pix_fmt','yuv420p',str(out/'video.mp4')],check=True)
        shutil.copy2(out/'video.mp4',out/'chalk_box_stack.mp4')


def main():
    p=argparse.ArgumentParser();p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--physics-json',type=Path)
    p.add_argument('--scenario-json',type=Path);p.add_argument('--scenario-overrides-json',type=Path)
    p.add_argument('--physics-python',type=Path,default=python_for('physics'))
    p.add_argument('--fps',type=int);p.add_argument('--duration-sec',type=float)
    for key in BASELINE_PHYSICS:p.add_argument('--'+key.replace('_','-'),type=float)
    p.add_argument('--samples',type=int);p.add_argument('--resolution',type=int,nargs=2)
    p.add_argument('--engine',choices=('cycles','eevee'),default='cycles');p.add_argument('--device',choices=('auto','cpu'),default='auto')
    p.add_argument('--mode',choices=('preview','animation','sampled'),default='animation');p.add_argument('--preview-frame',type=int,default=1)
    p.add_argument('--frame-count',type=int,default=6)
    args=parse_render_args(p, sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None);render(args)
if __name__=='__main__':run_renderer(main, 'chalk_box_stack')

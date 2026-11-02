"""Replay the five physical pendulums and their twin suspension lines."""

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
import argparse,json,sys,subprocess,shutil
from copy import deepcopy
from scene_support.newtons_cradle.runtime_support import python_for
from scene_support.newtons_cradle.scene_config import defaults
from scene_support.newtons_cradle.scene_geometry import pivots
from scene_support.newtons_cradle.scene_environment import build_room,material,wood,box,pbr_wood,textured_material,configure_lighting,ENVIRONMENT_THEME
from scene_support.newtons_cradle.render_quality import configure_renderer,configure_color,prepare_eevee

from pcve_scene_runtime import parse_render_args, run_renderer

def render(args):
    import bpy
    from mathutils import Vector
    out=args.out_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    physics=args.physics_json.resolve() if args.physics_json else out/'physics_transforms.json'
    if args.physics_json:
        if any(getattr(args,key) is not None for key in ('scenario_json','scenario_overrides_json','initial_height','restitution','fps','duration_sec','slow_motion')):
            raise ValueError('Resimulate to change physics/timing; cached trajectory cannot be edited by the renderer')
    else:
        command=[str(args.physics_python or python_for('physics')),str(Path(__file__).with_name('simulate_newtons_cradle.py')),'--out',str(physics)]
        for key in ('scenario_json','scenario_overrides_json','initial_height','restitution','fps','duration_sec','slow_motion'):
            value=getattr(args,key)
            if value is not None:command+=['--'+key.replace('_','-'),str(value)]
        subprocess.run(command,check=True)
    data=json.loads(physics.read_text(encoding='utf-8'));s=deepcopy(data['scenario']);c=s['physics']
    s['render'].update(resolution=list(args.resolution),samples=args.samples,engine=args.engine,mode=args.mode,appearance_version=6)
    if data['scene']!='newtons_cradle' or not data['quality']['valid']:raise ValueError('Invalid physics cache')
    if set(data['objects'])!={f'ball_{i:02d}' for i in range(5)}:raise ValueError('Cached cradle layout differs')
    if physics!=out/'physics_transforms.json':shutil.copy2(physics,out/'physics_transforms.json')
    bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene
    s['render']['device']=configure_renderer(bpy,scene,args)
    configure_color(scene)
    scene.render.resolution_x,scene.render.resolution_y=args.resolution;scene.render.resolution_percentage=100
    scene.render.fps=data['playback_fps'];scene.frame_start=1;scene.frame_end=data['frame_end'];scene.render.use_persistent_data=True
    build_room(bpy,c);configure_lighting(bpy,scene)
    s['render']['environment_theme']=ENVIRONMENT_THEME
    steel=textured_material(bpy,'Polished steel spheres',(.48,.52,.56),metal=1.0,roughness=.135,scale=700,bump_distance=.000004)
    frame_mat=textured_material(bpy,'Brushed brass frame',(.36,.22,.064),metal=.88,roughness=.25,scale=480,bump_distance=.000012)
    frame_mat.node_tree.nodes.get('Principled BSDF').inputs['Anisotropic'].default_value=.30
    thread_mat=material(bpy,'Dark suspension filament',(.035,.035,.033),roughness=.55)
    base_mat=pbr_wood(bpy,'Scanned varnished cradle base')
    box(bpy,'Walnut cradle base',[0,0,c['table_height']+.018],[.60,.23,.036],base_mat,bevel=.012)
    def rod(name,start,end,radius,mat):
        start,end=Vector(start),Vector(end);delta=end-start
        bpy.ops.mesh.primitive_cylinder_add(vertices=20,radius=radius,depth=1,location=(start+end)/2)
        obj=bpy.context.object;obj.name=name;obj.scale.z=delta.length
        obj.rotation_mode='QUATERNION';obj.rotation_quaternion=delta.to_track_quat('Z','Y');obj.data.materials.append(mat)
        for poly in obj.data.polygons:poly.use_smooth=True
        return obj
    for y in (-.065,.065):
        for x in (-.265,.265):rod('Brass upright',[x,y,c['table_height']+.036],[x,y,c['pivot_height']],.005,frame_mat)
        rod('Brass top rail',[-.265,y,c['pivot_height']],[.265,y,c['pivot_height']],.005,frame_mat)
    for x in (-.265,.265):rod('Brass cross rail',[x,-.065,c['pivot_height']],[x,.065,c['pivot_height']],.004,frame_mat)
    box(bpy,'Desk notebook',[.48,.14,c['table_height']+.012],[.18,.25,.024],textured_material(bpy,'Notebook teal linen',(.045,.14,.15),roughness=.78,scale=230,bump_distance=.00010),bevel=.005)
    rod('Desk pencil',[.38,-.06,c['table_height']+.005],[.55,-.025,c['table_height']+.005],.003,material(bpy,'Pencil ochre',(.64,.35,.08)))
    plaque=material(bpy,'Dark brass maker plate',(.18,.11,.04),metal=.82,roughness=.34)
    box(bpy,'Cradle maker plate',[0,-.1153,c['table_height']+.018],[.13,.0007,.017],plaque,bevel=.001)
    import math
    bpy.ops.object.text_add(location=[-.052,-.1158,c['table_height']+.014],rotation=[math.pi/2,0,0]);label=bpy.context.object;label.name='Maker engraving';label.data.body="NEWTON'S CRADLE";label.data.size=.008;label.data.materials.append(material(bpy,'Plate lettering',(.56,.47,.29),metal=.6))
    for x in (-.23,.23):
        for y in (-.088,.088):
            bpy.ops.mesh.primitive_uv_sphere_add(segments=12,ring_count=6,radius=.003,location=[x,y,c['table_height']+.036]);bolt=bpy.context.object;bolt.name='Base fastening';bolt.scale.z=.30;bolt.data.materials.append(frame_mat)
    objects={};threads={};anchors=pivots(c);presence=c.get('ball_presence',[1]*5)
    for i,anchor in enumerate(anchors):
        key=f'ball_{i:02d}'
        if not presence[i]:
            # Deleted slot: no mesh, no suspension lines; the GT marks the
            # object absent on every frame, matching the simulation.
            continue
        bpy.ops.mesh.primitive_uv_sphere_add(segments=48,ring_count=24,radius=c['ball_radius']);ball=bpy.context.object;ball.name=key
        ball.data.materials.append(steel)
        for poly in ball.data.polygons:poly.use_smooth=True
        objects[key]=ball
        threads[key]=[(side,rod(f'{key} suspension {side}',[anchor[0],side*.065,anchor[2]],[anchor[0],side*c['ball_radius']*.75,anchor[2]-c['pendulum_length']],.00045,thread_mat)) for side in (-1,1)]
    for frame in data['frames']:
        for key,obj in objects.items():
            state=frame[key]
            if not state.get('present',True):continue
            obj.location=state['location'];obj.rotation_mode='QUATERNION';q=state['quaternion_xyzw'];obj.rotation_quaternion=(q[3],q[0],q[1],q[2])
            obj.keyframe_insert('location',frame=frame['frame_index']);obj.keyframe_insert('rotation_quaternion',frame=frame['frame_index'])
        for key,ball in objects.items():
            state=frame[key]
            if not state.get('present',True):continue
            anchor=anchors[int(key.split('_')[1])]
            pos=Vector(state['location'])
            for side,thread in threads[key]:
                start=Vector([anchor[0],side*.065,anchor[2]])
                end=pos+Vector([0,side*c['ball_radius']*.75,0]);delta=end-start
                thread.location=(start+end)/2;thread.scale.z=delta.length;thread.rotation_quaternion=delta.to_track_quat('Z','Y')
                for prop in ('location','scale','rotation_quaternion'):thread.keyframe_insert(prop,frame=frame['frame_index'])
    for obj in [*objects.values(),*(thread for pair in threads.values() for _,thread in pair)]:
        for curve in obj.animation_data.action.fcurves:
            for key in curve.keyframe_points:key.interpolation='LINEAR'
    camera_cfg=deepcopy(s['camera'])
    if camera_cfg==defaults()['camera']:camera_cfg=dict(location=[.78,-1.58,1.29],target=[-.01,0,.89],lens_mm=58,focus_distance=1.86,fstop=16.0)
    s['camera']=camera_cfg
    bpy.ops.object.camera_add(location=camera_cfg['location']);camera=bpy.context.object;camera.data.lens=camera_cfg['lens_mm']
    camera.rotation_euler=(Vector(camera_cfg['target'])-camera.location).to_track_quat('-Z','Y').to_euler();scene.camera=camera
    if 'focus_distance' in camera_cfg:
        camera.data.dof.use_dof=True;camera.data.dof.focus_distance=camera_cfg['focus_distance'];camera.data.dof.aperture_fstop=camera_cfg['fstop']
    bpy.context.view_layer.update();camera_matrix=[list(row) for row in camera.matrix_world]
    # Preserve the original rigid projects' GT fields; slow-motion metadata is additive.
    gt=dict(schema_version=1,scene=data['scene'],fps=scene.render.fps,frame_start=1,frame_end=data['frame_end'],
        physics={key:value for key,value in data.items() if key!='frames'},scenario=s,
        objects={key:dict(meta,**({'object_name':objects[key].name} if key in objects else {}))
                 for key,meta in data['objects'].items()},
        camera=dict(object_name=camera.name,lens_mm=camera.data.lens,sensor_width_mm=camera.data.sensor_width,resolution=list(args.resolution)),
        sample_fps=data['sample_fps'],slow_motion=data['slow_motion'],physical_duration_sec=data['physical_duration_sec'],playback_duration_sec=data['playback_duration_sec'],
        frames=[dict(frame,camera_matrix_world=camera_matrix) for frame in data['frames']])
    (out/'ground_truth_transforms.json').write_text(json.dumps(gt,indent=2,ensure_ascii=False),encoding='utf-8')
    (out/'scenario_metadata.json').write_text(json.dumps(s,indent=2,ensure_ascii=False),encoding='utf-8')
    time=data['quality']['events'].get('first_ball_impact_sec',.2)+.17
    preview=args.preview_frame or min(scene.frame_end,round(time*data['sample_fps'])+1)
    if not 1<=preview<=scene.frame_end:raise ValueError('Preview frame outside cached trajectory')
    checked=sorted({1,preview,scene.frame_end});max_error=0
    for index in checked:
        scene.frame_set(index);bpy.context.view_layer.update()
        for key,obj in objects.items():
            state=data['frames'][index-1][key]
            if not state.get('present',True):continue
            expected=state['matrix_world']
            max_error=max(max_error,max(abs(obj.matrix_world[i][j]-expected[i][j]) for i in range(4) for j in range(4)))
    if max_error>1e-5:raise RuntimeError('Blender replay differs from simulated rigid poses')
    (out/'render_validation.json').write_text(json.dumps(dict(checked_frames=checked,objects_checked=len(objects),max_matrix_error=max_error,appearance_version=6,physics_changed=False)),encoding='utf-8')
    scene.frame_set(preview)
    prepare_eevee(bpy,scene,[*objects.values(),*(thread for pair in threads.values() for _,thread in pair)])
    bpy.ops.file.pack_all()
    scene.render.image_settings.file_format='PNG';scene.render.filepath=str(out/'preview.png');bpy.ops.render.render(write_still=True)
    if args.mode=='animation':
        scene.render.image_settings.file_format='FFMPEG';scene.render.ffmpeg.format='MPEG4';scene.render.ffmpeg.codec='H264';scene.render.ffmpeg.constant_rate_factor='HIGH'
        scene.render.filepath=str(out/'newtons_cradle.mp4');scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'newtons_cradle.blend'))
    if args.mode=='animation':
        bpy.ops.render.render(animation=True);shutil.copy2(out/'newtons_cradle.mp4',out/'video.mp4')

def main():
    p=argparse.ArgumentParser();p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--physics-json',type=Path);p.add_argument('--physics-python',type=Path)
    p.add_argument('--scenario-json',type=Path);p.add_argument('--scenario-overrides-json',type=Path)
    p.add_argument('--initial-height',type=float);p.add_argument('--restitution',type=float);p.add_argument('--fps',type=int);p.add_argument('--duration-sec',type=float);p.add_argument('--slow-motion',type=int,choices=(1,2,4,8))
    p.add_argument('--engine',choices=('eevee','cycles'),default='cycles');p.add_argument('--device',choices=('auto','cpu'),default='auto');p.add_argument('--samples',type=int,default=32);p.add_argument('--resolution',type=int,nargs=2,default=[960,540]);p.add_argument('--mode',choices=('preview','animation'),default='animation');p.add_argument('--preview-frame',type=int)
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:];render(parse_render_args(p, argv))

if __name__=='__main__':run_renderer(main, 'newtons_cradle')

"""Render the cached rigid ball over the exact terrain used for collision."""

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





import sys
from pathlib import Path
from pcve_blender_compat import (shader_socket, set_shader_input, eevee_engine, set_eevee_property, set_color_property)
from pathlib import Path
from copy import deepcopy
import argparse,json,sys,subprocess,shutil
import numpy as np
from scene_support.uneven_ground_ball.runtime_support import python_for
from scene_support.uneven_ground_ball.scene_config import TERRAIN_CAMERA
from scene_support.uneven_ground_ball.terrain_geometry import terrain_mesh,mesh_hash
from scene_support.uneven_ground_ball.scene_environment import ground_material,ball_material,build_environment,build_lighting,bake_terrain_shading,scatter_gravel

from pcve_scene_runtime import parse_render_args, run_renderer

def configure_renderer(scene,args):
    """EEVEE Next renders a smooth height field flat unless ray tracing, ambient
    occlusion and real shadow maps are switched on; they are all off by default.
    """
    if args.engine=='eevee':
        ee=scene.eevee
        ee.taa_render_samples=args.samples
        for name,value in (('use_shadows',True),('use_raytracing',True),('use_gtao',True),
                           ('shadow_resolution_scale',1.),('shadow_ray_count',2),('shadow_step_count',6),
                           ('fast_gi_ray_count',4),('gtao_distance',.45),('gtao_quality',1.25)):
            if hasattr(ee,name):
                try:setattr(ee,name,value)
                except (TypeError,ValueError):pass
        if hasattr(ee,'ray_tracing_options'):
            options=ee.ray_tracing_options
            for name,value in (('resolution_scale','1'),('use_denoise',True),('screen_trace_quality',.8),
                               ('screen_trace_thickness',.12),('trace_max_roughness',.6)):
                if hasattr(options,name):
                    try:setattr(options,name,value)
                    except (TypeError,ValueError):pass
    else:
        scene.cycles.samples=args.samples;scene.cycles.use_denoising=True
        from pcve_blender_compat import configure_cycles_device
        configure_cycles_device(__import__('bpy'),scene,args.device)

def configure_colour(scene):
    set_color_property(scene.view_settings, 'view_transform', 'AgX')
    try:set_color_property(scene.view_settings, 'look', 'AgX - Medium High Contrast')
    except TypeError:pass
    scene.view_settings.exposure=.35

def render(args):
    import bpy
    from mathutils import Vector
    out=args.out_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    physics=args.physics_json.resolve() if args.physics_json else out/'physics_transforms.json'
    keys=('scenario_json','scenario_overrides_json','ball_mass','ball_speed','ball_friction','rolling_friction','fps','duration_sec','slow_motion')
    if args.physics_json:
        if any(getattr(args,key) is not None for key in keys):raise ValueError('Resimulate to change physics or timing; cached trajectories cannot be edited in the renderer')
    else:
        command=[str(args.physics_python or python_for('physics')),str(Path(__file__).with_name('simulate_uneven_ground_ball.py')),'--out',str(physics)]
        for key in keys:
            value=getattr(args,key)
            if value is not None:command+=['--'+key.replace('_','-'),str(value)]
        subprocess.run(command,check=True)
    data=json.loads(physics.read_text(encoding='utf-8'));s=deepcopy(data['scenario']);c=s['physics']
    if data['scene']!='uneven_ground_ball' or not data['quality']['valid']:raise ValueError('Invalid terrain simulation; inspect simulation_metrics.json')
    archive=physics.parent/data['terrain']['geometry_file']
    with np.load(archive) as cached:vertices=cached['vertices'];faces=cached['faces']
    if mesh_hash(vertices,faces)!=data['terrain']['mesh_hash'] or mesh_hash(*terrain_mesh(c))!=data['terrain']['mesh_hash']:raise ValueError('Terrain cache differs from current geometry; resimulate')
    if physics!=out/'physics_transforms.json':shutil.copy2(physics,out/'physics_transforms.json')
    if archive!=out/'terrain_mesh.npz':shutil.copy2(archive,out/'terrain_mesh.npz')
    s['render'].update(resolution=list(args.resolution),samples=args.samples,engine=args.engine,mode=args.mode,view=args.view,surface_guide=args.surface_guide)
    if args.view=='terrain':s['camera']=deepcopy(TERRAIN_CAMERA)
    if args.camera_location:s['camera']['location']=list(args.camera_location)
    if args.camera_target:s['camera']['target']=list(args.camera_target)
    if args.camera_lens:s['camera']['lens_mm']=args.camera_lens
    bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene
    scene.render.engine=eevee_engine() if args.engine=='eevee' else 'CYCLES'
    configure_renderer(scene,args);configure_colour(scene)
    scene.render.resolution_x,scene.render.resolution_y=args.resolution;scene.render.resolution_percentage=100;scene.render.fps=data['playback_fps'];scene.frame_start=1;scene.frame_end=data['frame_end']
    scene.render.use_persistent_data=True  # keep scene data between frames; avoids per-frame resync/BVH rebuild
    scene.render.filter_size=1.2
    scene.world=bpy.data.worlds.new('Courtyard daylight');scene.world.use_nodes=True
    background=scene.world.node_tree.nodes['Background']
    background.inputs[0].default_value=(.40,.53,.72,1);background.inputs[1].default_value=.30
    mesh=bpy.data.meshes.new('Collision terrain surface');mesh.from_pydata(vertices.tolist(),[],faces.tolist());mesh.update()
    uv=mesh.uv_layers.new(name='World metres')
    for face in mesh.polygons:
        face.use_smooth=True
        for loop in face.loop_indices:uv.data[loop].uv=tuple(vertices[mesh.loops[loop].vertex_index,:2])
    bake_terrain_shading(mesh,vertices,c)
    terrain=bpy.data.objects.new('Uneven courtyard path',mesh);scene.collection.objects.link(terrain);terrain.data.materials.append(ground_material(bpy,c,args.surface_guide,args.ground_texture,args.grass_texture))
    build_environment(bpy,c);build_lighting(bpy,scene)
    gravel=scatter_gravel(bpy,c,data['frames'],args.path_half_width,args.gravel_count)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=64,ring_count=32,radius=c['ball_radius']);ball=bpy.context.object;ball.name='Rubber toy ball';ball.data.materials.append(ball_material(bpy))
    for face in ball.data.polygons:face.use_smooth=True
    for face in ball.data.polygons:face.use_smooth=True
    for frame in data['frames']:
        state=frame['ball'];ball.location=state['location'];ball.rotation_mode='QUATERNION';q=state['quaternion_xyzw'];ball.rotation_quaternion=(q[3],q[0],q[1],q[2])
        ball.keyframe_insert('location',frame=frame['frame_index']);ball.keyframe_insert('rotation_quaternion',frame=frame['frame_index'])
    for curve in ball.animation_data.action.fcurves:
        for key in curve.keyframe_points:key.interpolation='LINEAR'
    cfg=s['camera'];bpy.ops.object.camera_add(location=cfg['location']);camera=bpy.context.object;camera.data.lens=cfg['lens_mm'];camera.rotation_euler=(Vector(cfg['target'])-camera.location).to_track_quat('-Z','Y').to_euler();scene.camera=camera
    camera.data.dof.use_dof=bool(args.aperture)
    if args.aperture:
        camera.data.dof.focus_distance=float(np.linalg.norm(Vector(cfg['target'])-camera.location));camera.data.dof.aperture_fstop=args.aperture
    bpy.context.view_layer.update();camera_matrix=[list(row) for row in camera.matrix_world]
    gt=dict(schema_version=1,scene=data['scene'],fps=scene.render.fps,frame_start=1,frame_end=data['frame_end'],physics={k:v for k,v in data.items() if k!='frames'},scenario=s,
        objects={'ball':dict(data['objects']['ball'],object_name=ball.name)},terrain=data['terrain'],
        camera=dict(object_name=camera.name,lens_mm=camera.data.lens,sensor_width_mm=camera.data.sensor_width,resolution=list(args.resolution)),
        sample_fps=data['sample_fps'],slow_motion=data['slow_motion'],physical_duration_sec=data['physical_duration_sec'],playback_duration_sec=data['playback_duration_sec'],
        frames=[dict(frame,camera_matrix_world=camera_matrix) for frame in data['frames']])
    (out/'ground_truth_transforms.json').write_text(json.dumps(gt,indent=2,ensure_ascii=False),encoding='utf-8');(out/'scenario_metadata.json').write_text(json.dumps(s,indent=2,ensure_ascii=False),encoding='utf-8')
    preview=args.preview_frame or max(1,data['frame_end']//2)
    if not 1<=preview<=scene.frame_end:raise ValueError('Preview frame out of range')
    checked=sorted({1,preview,scene.frame_end});error=0
    for index in checked:
        scene.frame_set(index);bpy.context.view_layer.update();expected=data['frames'][index-1]['ball']['matrix_world']
        error=max(error,max(abs(ball.matrix_world[i][j]-expected[i][j]) for i in range(4) for j in range(4)))
    if error>1e-5:raise RuntimeError('Ball replay differs from simulation')
    (out/'render_validation.json').write_text(json.dumps(dict(checked_frames=checked,max_matrix_error=error,terrain_mesh_hash=data['terrain']['mesh_hash'])),encoding='utf-8')
    scene.frame_set(preview);scene.render.image_settings.file_format='PNG';scene.render.filepath=str(out/'preview.png');bpy.ops.render.render(write_still=True)
    if args.mode=='animation':
        scene.render.image_settings.file_format='FFMPEG';scene.render.ffmpeg.format='MPEG4';scene.render.ffmpeg.codec='H264';scene.render.ffmpeg.constant_rate_factor='HIGH';scene.render.filepath=str(out/'uneven_ground_ball.mp4');scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'uneven_ground_ball.blend'))
    if args.mode=='animation':bpy.ops.render.render(animation=True)
    if args.label:
        from scene_support.uneven_ground_ball.video_presentation import label_outputs
        label_outputs(out,gt,preview,animation=args.mode=='animation')

def main():
    p=argparse.ArgumentParser();p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--physics-json',type=Path);p.add_argument('--physics-python',type=Path);p.add_argument('--scenario-json',type=Path);p.add_argument('--scenario-overrides-json',type=Path)
    for name in ('ball-mass','ball-speed','ball-friction','rolling-friction'):p.add_argument('--'+name,type=float)
    p.add_argument('--fps',type=int);p.add_argument('--duration-sec',type=float);p.add_argument('--slow-motion',type=int,choices=(1,2,4,8));p.add_argument('--engine',choices=('eevee','cycles'),default='cycles');p.add_argument('--samples',type=int,default=32);p.add_argument('--resolution',type=int,nargs=2,default=[960,540]);p.add_argument('--mode',choices=('preview','animation'),default='animation');p.add_argument('--preview-frame',type=int);p.add_argument('--view',choices=('terrain','overview'),default='terrain');p.add_argument('--surface-guide',choices=('contours','none'),default='none')
    p.add_argument('--ground-texture',default='floor_pebbles_01');p.add_argument('--grass-texture',default='grass_ground')
    p.add_argument('--path-half-width',type=float,default=1.90);p.add_argument('--gravel-count',type=int,default=900);p.add_argument('--camera-location',type=float,nargs=3);p.add_argument('--camera-target',type=float,nargs=3);p.add_argument('--camera-lens',type=float);p.add_argument('--aperture',type=float,default=0.)
    p.set_defaults(label=False)
    p.add_argument('--label',dest='label',action='store_true',help='Add the optional presentation caption.')
    p.add_argument('--no-label',dest='label',action='store_false',help='Skip the caption bar used by the published videos.')
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:];render(parse_render_args(p, argv))

if __name__=='__main__':run_renderer(main, 'uneven_ground_ball')

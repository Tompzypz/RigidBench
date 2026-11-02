"""Render the simulated poses of the ball and every individual wooden block."""

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
import argparse,json,sys,subprocess,shutil
from copy import deepcopy
from scene_support.ball_block_building.runtime_support import python_for
from scene_support.ball_block_building.scene_config import defaults
from scene_support.ball_block_building.building_geometry import building_blocks
from scene_support.ball_block_building.scene_environment import build_room,material,wood,box,pbr_wood,textured_material,configure_lighting,ENVIRONMENT_THEME
from scene_support.ball_block_building.render_quality import configure_renderer,configure_color,prepare_eevee

MODELS=_PCVE_PROJECT_ROOT/'assets'/'models'
BALL_MODEL_SUFFIXES=('.glb','.gltf','.obj','.fbx','.stl')
# Scanned assets that replace the procedural stand-ins. Both are optional: if a
# file is missing the scene falls back to the modelled wooden ball and the
# coloured blocks, so the script keeps working on a bare checkout.
BALL_MODEL=next((p for p in (MODELS/'tennis_ball.glb',) if p.exists()),None)
BLOCK_MODEL=next((p for p in (MODELS/'building_block_building.glb',) if p.exists()),None)
# The kit is a whole toy-block set; these are its plain 1x1x2 timber bricks,
# in order of preference (the bevel block has the softest, most moulded edges).
BLOCK_PIECE_NAMES=('obj_bevel_block_m_unit_block_0','obj_bevel_block1_m_unit_block_0','obj_bevel_block5_m_unit_block_0')

from pcve_scene_runtime import parse_render_args, run_renderer

def tune_block_material(materials):
    """Turn the kit's clear-coated plastic finish into matte waxed timber.

    The downloaded material is a single wood atlas with a sharp 0.04 clearcoat,
    which is exactly the "too smooth" look this scene is trying to lose. The
    coat is nearly removed, roughness is raised and driven by the atlas
    luminance, and the grain itself gets a small bump so the blocks read as
    sawn wood rather than polished resin.
    """
    for mat in materials:
        if not mat or not mat.use_nodes:continue
        nodes=mat.node_tree.nodes;links=mat.node_tree.links;shader=nodes.get('Principled BSDF')
        if shader is None:continue
        for socket,value in (('Coat Weight',.04),('Coat Roughness',.35),('Specular IOR Level',.35)):
            if socket in shader.inputs:shader.inputs[socket].default_value=value
        base=shader.inputs['Base Color']
        if not base.is_linked:continue
        luma=nodes.new('ShaderNodeRGBToBW');links.new(base.links[0].from_socket,luma.inputs[0])
        rough=nodes.new('ShaderNodeMapRange');rough.inputs['From Min'].default_value=.08;rough.inputs['From Max'].default_value=.62
        rough.inputs['To Min'].default_value=.46;rough.inputs['To Max'].default_value=.70;rough.clamp=True
        links.new(luma.outputs[0],rough.inputs[0])
        for link in list(links):
            if link.to_socket==shader.inputs['Roughness']:links.remove(link)
        links.new(rough.outputs[0],shader.inputs['Roughness'])
        bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.10;bump.inputs['Distance'].default_value=.00035
        links.new(luma.outputs[0],bump.inputs['Height']);links.new(bump.outputs[0],shader.inputs['Normal'])

def tune_ball_material(materials):
    """Felt is diffuse: kill any leftover lacquer and add a faint sheen."""
    for mat in materials:
        if not mat or not mat.use_nodes:continue
        shader=mat.node_tree.nodes.get('Principled BSDF')
        if shader is None:continue
        for socket,value in (('Coat Weight',0.),('Metallic',0.)):
            if socket in shader.inputs:shader.inputs[socket].default_value=value
        for socket,value in (('Sheen Weight',.14),('Sheen Roughness',.55)):
            if socket in shader.inputs:shader.inputs[socket].default_value=value

def block_piece(bpy,path,names=BLOCK_PIECE_NAMES):
    """Import the downloaded block kit and return one plain brick, metres.

    The kit contains 23 pieces; the simulation still collides with an
    axis-aligned box, so only a plain 1x1x2 brick is reused and every block
    scales it to its own simulated box. The mesh is left parentless with its
    transform applied so a per-block scale can be baked into a copy without
    moving the origin off the block centre.
    """
    from mathutils import Matrix,Vector
    path=Path(path).resolve()
    if not path.exists():raise FileNotFoundError(f'Block model not found: {path}')
    bpy.ops.object.select_all(action='DESELECT')
    existing=set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported=[obj for obj in bpy.context.scene.objects if obj not in existing]
    meshes=[obj for obj in imported if obj.type=='MESH']
    if not meshes:raise ValueError(f'No mesh found inside {path.name}')
    lookup={obj.name:obj for obj in meshes};piece=None
    for name in names:
        if name in lookup:piece=lookup[name];break
    if piece is None:
        # Fall back to whatever brick is closest to the 1x1x2 proportions.
        def error(obj):
            dims=sorted(obj.dimensions);total=sum(dims) or 1.
            return abs(dims[0]/total-.25)+abs(dims[1]/total-.25)+abs(dims[2]/total-.5)
        piece=min(meshes,key=error)
    bpy.ops.object.select_all(action='DESELECT');piece.select_set(True);bpy.context.view_layer.objects.active=piece
    bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    bpy.context.view_layer.update()
    # The kit piece is laid out off-origin inside the set; re-centre its geometry
    # on the object origin so the origin can stand in for the block centre.
    corners=[Vector(corner) for corner in piece.bound_box]
    centre=sum(corners,Vector())/8
    piece.data.transform(Matrix.Translation(-centre))
    bpy.context.view_layer.update()
    for obj in imported:
        if obj is not piece:bpy.data.objects.remove(obj,do_unlink=True)
    tune_block_material(piece.data.materials)
    return piece

def create_block(bpy,piece,name,location,size):
    """Linked-material copy of the kit brick, stretched onto its collision box."""
    obj=piece.copy();obj.data=piece.data.copy();bpy.context.scene.collection.objects.link(obj)
    obj.name=name;obj.data.name=name+' timber'
    obj.scale=tuple(size[i]/piece.dimensions[i] for i in range(3))
    bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    obj.location=location
    return obj

def imported_ball(bpy,path,radius):
    """Load a downloaded ball mesh and bake it into a body frame of its own.

    The simulation only knows a sphere of ``radius``, so the mesh is centred on
    its own bounding box and scaled until its largest dimension equals the
    collision diameter. The result keeps the origin at the centre of the ball,
    which is what the cached pose matrices expect.
    """
    from mathutils import Vector
    path=Path(path).resolve()
    if not path.exists():raise FileNotFoundError(f'Ball model not found: {path}')
    suffix=path.suffix.lower()
    if suffix not in BALL_MODEL_SUFFIXES:raise ValueError(f'Unsupported ball model format {suffix}; expected one of {", ".join(BALL_MODEL_SUFFIXES)}')
    bpy.ops.object.select_all(action='DESELECT')
    if suffix in ('.glb','.gltf'):bpy.ops.import_scene.gltf(filepath=str(path))
    elif suffix=='.obj':bpy.ops.wm.obj_import(filepath=str(path))
    elif suffix=='.fbx':bpy.ops.import_scene.fbx(filepath=str(path))
    else:bpy.ops.wm.stl_import(filepath=str(path))
    meshes=[obj for obj in bpy.context.selected_objects if obj.type=='MESH']
    if not meshes:raise ValueError(f'No mesh found inside {path.name}')
    for obj in meshes:obj.select_set(True)
    bpy.context.view_layer.objects.active=meshes[0]
    # Keep world transforms but drop glTF/OBJ import parents, so the join and
    # the bake below work on a single parentless mesh.
    bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
    if len(meshes)>1:bpy.ops.object.join()
    ball=bpy.context.object;ball.name='Rolling ball'
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    corners=[Vector(corner) for corner in ball.bound_box]
    centre=sum(corners,Vector())/8
    extent=max(max(c[i] for c in corners)-min(c[i] for c in corners) for i in range(3))
    if extent<=0:raise ValueError(f'Ball model {path.name} has no size')
    factor=2*radius/extent
    for vertex in ball.data.vertices:vertex.co=(vertex.co-centre)*factor
    bpy.ops.object.mode_set(mode='OBJECT')
    return ball

def create_ball(bpy,radius,material,model=None):
    """Procedural wooden ball, or a downloaded mesh scaled to the same radius."""
    if model:
        ball=imported_ball(bpy,model,radius)
        if not ball.data.materials:ball.data.materials.append(material)
        for polygon in ball.data.polygons:polygon.use_smooth=True
        return ball
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48,ring_count=24,radius=radius)
    ball=bpy.context.object;ball.name='Orange wooden ball';ball.data.materials.append(material)
    for polygon in ball.data.polygons:polygon.use_smooth=True
    return ball

def render(args):
    import bpy
    from mathutils import Vector
    out=args.out_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    physics=args.physics_json.resolve() if args.physics_json else out/'physics_transforms.json'
    if args.physics_json:
        if any(getattr(args,key) is not None for key in ('scenario_json','scenario_overrides_json','ball_mass','ball_speed','fps','duration_sec','slow_motion')):
            raise ValueError('Resimulate to change physics/timing; cached trajectory cannot be edited by the renderer')
    else:
        command=[str(args.physics_python or python_for('physics')),str(Path(__file__).with_name('simulate_ball_block_building.py')),'--out',str(physics)]
        for key in ('scenario_json','scenario_overrides_json','ball_mass','ball_speed','fps','duration_sec','slow_motion'):
            value=getattr(args,key)
            if value is not None:command+=['--'+key.replace('_','-'),str(value)]
        subprocess.run(command,check=True)
    data=json.loads(physics.read_text(encoding='utf-8'));s=deepcopy(data['scenario']);c=s['physics']
    s['render'].update(resolution=list(args.resolution),samples=args.samples,engine=args.engine,mode=args.mode,appearance_version=22)
    if data['scene']!='ball_block_building' or not data['quality']['valid']:raise ValueError('Invalid physics cache')
    object_presence=data.get('object_presence',{'ball':True,**{block['object_id']:True for block in building_blocks(c)}})
    layout=[block for block in building_blocks(c) if object_presence.get(block['object_id'],True)]
    if set(data['objects'])!={'ball',*(block['object_id'] for block in layout)}:
        raise ValueError('Cached object presence differs from the requested stack layout; rerun simulation')
    if any(data['objects'][b['object_id']]['size']!=b['size'] for b in layout):
        raise ValueError('Cached block dimensions differ from current geometry; rerun simulation')
    if physics!=out/'physics_transforms.json':shutil.copy2(physics,out/'physics_transforms.json')
    bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene
    s['render']['device']=configure_renderer(bpy,scene,args)
    configure_color(scene)
    scene.render.resolution_x,scene.render.resolution_y=args.resolution;scene.render.resolution_percentage=100
    scene.render.fps=data['playback_fps'];scene.frame_start=1;scene.frame_end=data['frame_end']
    build_room(bpy,c);configure_lighting(bpy,scene)
    s['render']['environment_theme']=ENVIRONMENT_THEME
    colors=[(.56,.34,.16),(.16,.36,.38),(.59,.29,.23),(.70,.51,.26),(.25,.36,.48)]
    mats=[];piece=None
    if args.block_model:
        # Downloaded kit: one scanned timber brick shared by every block, so no
        # per-block colour tint is generated at all.
        piece=block_piece(bpy,args.block_model)
    else:
        for i,color in enumerate(colors):
            mat=pbr_wood(bpy,f'Scanned coloured timber {i}');nodes=mat.node_tree.nodes;links=mat.node_tree.links;shader=nodes.get('Principled BSDF')
            base_link=next(link for link in links if link.to_socket==shader.inputs['Base Color']);texture=base_link.from_socket;links.remove(base_link)
            luma=nodes.new('ShaderNodeRGBToBW');links.new(texture,luma.inputs[0])
            grain=nodes.new('ShaderNodeMapRange');grain.inputs['From Min'].default_value=.02;grain.inputs['From Max'].default_value=.55
            grain.inputs['To Min'].default_value=.70;grain.inputs['To Max'].default_value=1.10;grain.clamp=True;links.new(luma.outputs[0],grain.inputs[0])
            tint=nodes.new('ShaderNodeMixRGB');tint.blend_type='MULTIPLY';tint.inputs[0].default_value=1;tint.inputs[1].default_value=(*color,1)
            links.new(grain.outputs[0],tint.inputs[2]);links.new(tint.outputs[0],shader.inputs['Base Color'])
            for node in nodes:
                if node.bl_idname=='ShaderNodeNormalMap':node.inputs['Strength'].default_value=.12
            set_shader_input(shader, 'Coat Weight', 0.12);set_shader_input(shader, 'Coat Roughness', 0.35);mats.append(mat)
    objects={}
    for block in layout:
        if piece:objects[block['object_id']]=create_block(bpy,piece,block['object_id'],[0,0,0],block['size'])
        else:objects[block['object_id']]=box(bpy,block['object_id'],[0,0,0],block['size'],mats[block['color']],bevel=.0006)
    if piece:bpy.data.objects.remove(piece,do_unlink=True)
    ball_mat=wood(bpy,'Fine lacquered orange wood',(.52,.115,.018),(.33,.062,.009));shader=ball_mat.node_tree.nodes.get('Principled BSDF');shader.inputs['Roughness'].default_value=.24;set_shader_input(shader, 'Coat Weight', 0.38);set_shader_input(shader, 'Coat Roughness', 0.2)
    # Swap in a downloaded ball with --ball-model; the collision body stays the
    # sphere of radius ball_radius in the simulation cache.
    ball=create_ball(bpy,c['ball_radius'],ball_mat,args.ball_model)
    if args.ball_model:tune_ball_material(ball.data.materials)
    objects={'ball':ball,**objects}
    for frame in data['frames']:
        for key,obj in objects.items():
            state=frame[key];obj.location=state['location'];obj.rotation_mode='QUATERNION';q=state['quaternion_xyzw'];obj.rotation_quaternion=(q[3],q[0],q[1],q[2])
            obj.keyframe_insert('location',frame=frame['frame_index']);obj.keyframe_insert('rotation_quaternion',frame=frame['frame_index'])
    for obj in objects.values():
        for curve in obj.animation_data.action.fcurves:
            for key in curve.keyframe_points:key.interpolation='LINEAR'
    camera_cfg=s['camera'];bpy.ops.object.camera_add(location=camera_cfg['location']);camera=bpy.context.object;camera.data.lens=camera_cfg['lens_mm']
    camera.rotation_euler=(Vector(camera_cfg['target'])-camera.location).to_track_quat('-Z','Y').to_euler();scene.camera=camera
    bpy.context.view_layer.update();camera_matrix=[list(row) for row in camera.matrix_world]
    # Preserve the original rigid projects' GT fields; slow-motion metadata is additive.
    gt=dict(schema_version=1,scene=data['scene'],fps=scene.render.fps,frame_start=1,frame_end=data['frame_end'],
        physics={key:value for key,value in data.items() if key!='frames'},scenario=s,object_presence=object_presence,
        objects={key:dict(meta,object_name=objects[key].name) for key,meta in data['objects'].items()},
        camera=dict(object_name=camera.name,lens_mm=camera.data.lens,sensor_width_mm=camera.data.sensor_width,resolution=list(args.resolution)),
        sample_fps=data['sample_fps'],slow_motion=data['slow_motion'],physical_duration_sec=data['physical_duration_sec'],playback_duration_sec=data['playback_duration_sec'],
        frames=[dict(frame,camera_matrix_world=camera_matrix) for frame in data['frames']])
    (out/'ground_truth_transforms.json').write_text(json.dumps(gt,indent=2,ensure_ascii=False),encoding='utf-8')
    (out/'scenario_metadata.json').write_text(json.dumps(s,indent=2,ensure_ascii=False),encoding='utf-8')
    # 0.75 s after the first contact the pile has visibly separated; a shorter
    # offset lands on the frame where the upper block still overlaps the base.
    time=data['quality']['events'].get('first_block_impact_sec',.3)+.75
    preview=args.preview_frame or min(scene.frame_end,round(time*data['sample_fps'])+1)
    if not 1<=preview<=scene.frame_end:raise ValueError('Preview frame outside cached trajectory')
    checked=sorted({1,preview,scene.frame_end});max_error=0
    for index in checked:
        scene.frame_set(index);bpy.context.view_layer.update()
        for key,obj in objects.items():
            expected=data['frames'][index-1][key]['matrix_world']
            max_error=max(max_error,max(abs(obj.matrix_world[i][j]-expected[i][j]) for i in range(4) for j in range(4)))
    if max_error>1e-5:raise RuntimeError('Blender replay differs from simulated rigid poses')
    (out/'render_validation.json').write_text(json.dumps(dict(checked_frames=checked,objects_checked=len(objects),max_matrix_error=max_error,appearance_version=s['render']['appearance_version'],physics_changed=False)),encoding='utf-8')
    scene.frame_set(preview)
    prepare_eevee(bpy,scene,[*objects.values()])
    bpy.ops.file.pack_all()
    scene.render.image_settings.file_format='PNG'
    if args.mode=='sampled':
        if not 2<=args.frame_count<=scene.frame_end:raise ValueError('Frame count must be between 2 and trajectory length')
        indices=[1+round(i*(scene.frame_end-1)/(args.frame_count-1)) for i in range(args.frame_count)]
        for index in indices:
            scene.frame_set(index);scene.render.filepath=str(out/f'frame_{index:04d}.png');bpy.ops.render.render(write_still=True)
        (out/'sampled_frames.json').write_text(json.dumps(dict(frame_indices=indices,frame_end=scene.frame_end)),encoding='utf-8')
    else:
        scene.render.filepath=str(out/'preview.png');bpy.ops.render.render(write_still=True)
    if args.mode=='animation':
        scene.render.image_settings.file_format='FFMPEG';scene.render.ffmpeg.format='MPEG4';scene.render.ffmpeg.codec='H264';scene.render.ffmpeg.constant_rate_factor='HIGH'
        scene.render.filepath=str(out/'ball_block_building.mp4');scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'ball_block_building.blend'))
    if args.mode=='animation':
        bpy.ops.render.render(animation=True);shutil.copy2(out/'ball_block_building.mp4',out/'video.mp4')

def main():
    p=argparse.ArgumentParser();p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--physics-json',type=Path);p.add_argument('--physics-python',type=Path)
    p.add_argument('--scenario-json',type=Path);p.add_argument('--scenario-overrides-json',type=Path)
    p.add_argument('--ball-mass',type=float);p.add_argument('--ball-speed',type=float);p.add_argument('--fps',type=int);p.add_argument('--duration-sec',type=float);p.add_argument('--slow-motion',type=int,choices=(1,2,4,8))
    p.add_argument('--engine',choices=('eevee','cycles'),default='cycles');p.add_argument('--device',choices=('auto','cpu'),default='auto');p.add_argument('--samples',type=int,default=32);p.add_argument('--resolution',type=int,nargs=2,default=[960,540]);p.add_argument('--mode',choices=('preview','animation','sampled'),default='animation');p.add_argument('--preview-frame',type=int);p.add_argument('--frame-count',type=int,default=6)
    p.add_argument('--ball-model',type=Path,default=BALL_MODEL,help='Downloaded ball mesh (.glb/.gltf/.obj/.fbx/.stl); scaled to the simulated radius. Defaults to assets/models/tennis_ball.glb when present.')
    p.add_argument('--block-model',type=Path,default=BLOCK_MODEL,help='Downloaded toy-block kit (.glb/.gltf/.obj/.fbx/.stl); one plain brick is stretched onto every simulated block box. Defaults to assets/models/building_block_building.glb when present.')
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:];render(parse_render_args(p, argv))

if __name__=='__main__':run_renderer(main, 'ball_block_building')

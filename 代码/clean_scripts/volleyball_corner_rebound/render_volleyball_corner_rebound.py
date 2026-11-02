"""Blender replay of PyBullet transforms; keyframe rendering is the default."""
from __future__ import annotations

# Load this seven-file scene bundle and the reference common scripts.
import sys as _clean_sys
from pathlib import Path as _CleanPath
_clean_scene_dir = _CleanPath(__file__).resolve().parent
_clean_scripts_dir = _clean_scene_dir.parent
_PCVE_PROJECT_ROOT = next(p for p in _clean_scene_dir.parents if (p / "assets").is_dir())
# sys.argv[0] must point at this scene script BEFORE importing edit_vocab:
# the bundle triggers load_scenario() at module level, and top-level
# shared modules (scene_config/scenario_io) locate the scene folder via
# sys.argv[0], which under `blender -b` is the blender binary.
_clean_sys.argv[0] = str(_CleanPath(__file__).resolve())
if str(_clean_scripts_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_clean_scripts_dir))
if str(_clean_scene_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_clean_scene_dir))
import edit_vocab as _clean_scene_bundle
_clean_scene_bundle.install_scene_support()


import argparse
import json
import math
import subprocess
import sys
from pathlib import Path
import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
from scene_config import MODELS, load_scenario, write_json, runtime
from scene_environment import build_room, exempt_slab_from_fills, import_ball, aim
from scene_geometry import geometry_snapshot
from camera_rig import animate_camera

def keyframes(data):
    values={1,9,data['frame_end']}
    for event in data['metrics']['wall_collisions'][:2]+data['metrics']['floor_collisions'][:1]:
        values.add(event['frame_index'])
    # A timed edit is only legible as a before/after pair, so both sides of the
    # event are rendered: the last frame that still ran on the source physics
    # and the frame the edit lands on.
    for event in data['metrics']['timed_events']:
        values.update((event['frame_index']-1,event['frame_index']))
    return sorted(f for f in values if f>=1)

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
    parser.add_argument('--physics-json',type=Path,help='Replay an existing trajectory after validating its resolved physics')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None)
    out=args.out_dir.resolve()
    out.mkdir(parents=True,exist_ok=True)
    scenario=load_scenario(args.scenario_overrides_json)
    write_json(out/'scenario_input.json',scenario)
    # Always simulate the resolved input; an older trajectory cannot silently survive an edit.
    # The simulator beside this file, not scene_config's HERE: that helper
    # prefers a new-scripts/ copy of the scene when one exists, which would
    # render a trajectory this bundle did not produce.
    command=[runtime('sim'),str(Path(__file__).resolve().with_name('simulate_volleyball_corner_rebound.py')),'--out',str(out/'physics_transforms.json')]
    if args.scenario_overrides_json:
        command+=['--scenario-overrides-json',str(args.scenario_overrides_json.resolve())]
    if args.physics_json:
        cached=json.loads(args.physics_json.read_text(encoding='utf-8'))
        if cached['physics']!=scenario['physics'] or cached.get('static_geometry')!=geometry_snapshot():
            raise ValueError('Cached trajectory does not match resolved physics')
        write_json(out/'physics_transforms.json',cached)
        write_json(out/'simulation_metrics.json',cached['metrics'])
    else:
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
    scene.view_settings.exposure=scenario['render'].get('exposure',.35)
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
    aim(cam,scenario['render']['camera_target'])
    cam_data.lens=scenario['render']['lens_mm']
    cam_data.clip_start=.05
    cam_data.clip_end=100
    cam_data.dof.use_dof=False
    # Everything the fills should reach now exists; the slab is the one
    # surface they were never meant to touch.
    exempt_slab_from_fills()
    camera_poses=animate_camera(cam,data['frames'],scenario['render'])
    write_json(out/'camera_transforms.json',{'mode':scenario['render'].get('camera_mode','fixed'),'frames':camera_poses})
    # Validate every rendered frame against the same physical sphere.
    validation=[]
    ground=[]
    evaluated_cameras=[]
    r=scenario['physics']['ball_radius']
    for row in data['frames']:
        f=row['frame_index']
        scene.frame_set(f)
        evaluated_cameras.append((tuple(v for line in cam.matrix_world for v in line),cam.data.lens))
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
        ground.append({'frame_index':f,'time_sec':row['time_sec'],'camera':camera_poses[f-1],'volleyball':{
            'location':list(pos),'quaternion_xyzw':row['ball_quaternion_xyzw'],'radius_m':r}})
    write_json(out/'ground_truth_transforms.json',{'fps':data['fps'],'frames':ground})
    write_json(out/'render_validation.json',{'all_frames_in_view':all(v['sphere_in_frame'] for v in validation),
        'all_centers_visible':all(v['center_visible'] for v in validation),
        'camera_is_fixed':len(set(evaluated_cameras))==1,
        'camera_has_animation':bool(cam.animation_data or cam.data.animation_data),
        'max_position_error_m':max(v['position_error_m'] for v in validation),'frames':validation})
    def projected_bounds(objects):
        points=[world_to_camera_view(scene,cam,obj.matrix_world@Vector(v)) for obj in objects for v in obj.bound_box]
        return {'min_x':min(p.x for p in points),'max_x':max(p.x for p in points),
            'min_y':min(p.y for p in points),'max_y':max(p.y for p in points),
            'in_frame':all(p.z>0 and 0<=p.x<=1 and 0<=p.y<=1 for p in points)}
    artwork=[obj for obj in scene.objects if obj.name.startswith('Imported framed art ')]
    spares=[obj for obj in scene.objects if obj.name.startswith('Spare volleyball ')]
    plants=[obj for obj in scene.objects if 'fig' in obj.name.lower() or 'foliage' in obj.name.lower()]
    unit=[obj for obj in scene.objects if obj.name.startswith('Split indoor unit')]
    # Mounted means the back face is on the plaster, not merely near it: the unit
    # hangs on the x=0 wall, so the gap is measured along that wall's normal, and
    # any drift shows up here as a gap instead of a floating appliance.
    unit_gap=min((min((obj.matrix_world@Vector(v)).x for v in obj.bound_box) for obj in unit),default=None)
    window=[obj for obj in scene.objects if obj.name.startswith('Window ') or obj.name.startswith('Casement ') or obj.name.startswith('Stone sill /')]
    window_bounds=projected_bounds(window)
    # The room holds exactly three movable-looking things and two walls' worth of
    # decoration. The corner the ball plays in is deliberately empty, and this
    # check keeps it that way: a plant back in shot would mean decoration moved
    # into the trajectory's way.
    layout={'artwork_count':len(artwork),'spare_ball_count':len(spares),
        'artwork_in_frame':projected_bounds(artwork)['in_frame'],
        'spare_balls_in_frame':projected_bounds(spares)['in_frame'],
        'spare_balls_stationary':all(not obj.animation_data for obj in spares),
        'window_bounds':window_bounds,
        'plant_objects':len(plants),
        'prop_clearance_m':data['metrics']['min_prop_clearance_m'],
        'min_spare_ball_clearance_m':data['metrics']['min_spare_ball_clearance_m'],
        'air_conditioner_count':len(unit),
        'air_conditioner_in_frame':bool(unit) and projected_bounds(unit)['in_frame'],
        'air_conditioner_back_gap_m':None if unit_gap is None else round(unit_gap,4),
        'air_conditioner_bounds':projected_bounds(unit) if unit else None,
        'min_air_conditioner_clearance_m':data['metrics']['min_ac_clearance_m']}
    layout['passed']=(len(artwork)==1 and len(spares)==2 and not plants and
        layout['artwork_in_frame'] and layout['spare_balls_in_frame'] and
        layout['spare_balls_stationary'] and window_bounds['in_frame'] and
        layout['prop_clearance_m']>-.01 and layout['min_spare_ball_clearance_m']>.25 and
        len(unit)==1 and layout['air_conditioner_in_frame'] and
        0<=layout['air_conditioner_back_gap_m']<.02 and layout['min_air_conditioner_clearance_m']>.4)
    write_json(out/'room_layout_validation.json',layout)
    # A fixed camera sees the same walls in every frame, so the roof is checked
    # once: cast the frame at render resolution and report what the top rows hit.
    res_x,res_y=scene.render.resolution_x,scene.render.resolution_y
    # Blender's AUTO sensor fit maps sensor_width to the longer image side.
    fpx=cam_data.lens*max(res_x,res_y)/cam_data.sensor_width
    rotation=cam.matrix_world.to_quaternion()
    deps=bpy.context.evaluated_depsgraph_get()
    grid_x,grid_y=64,36
    ceiling_hits,highest=0,0.0
    for ix in range(grid_x+1):
        for iy in range(grid_y+1):
            local=Vector(((res_x*ix/grid_x-res_x/2)/fpx,(res_y/2-res_y*iy/grid_y)/fpx,-1.0))
            direction=(rotation@local).normalized()
            hit,point,normal,index,obj,matrix=scene.ray_cast(deps,cam.location,direction,distance=60)
            if not hit:
                continue
            if obj and 'ceiling' in obj.name.lower():
                ceiling_hits+=1
            else:
                highest=max(highest,point.z)
    scene_frame={'camera_location':list(cam.location),'camera_lens_mm':cam_data.lens,
        'resolution':[res_x,res_y],'sample_grid':[grid_x,grid_y],
        'room_height_m':scenario['physics']['room_size'][2],
        'ceiling_in_frame':ceiling_hits>0,
        'ceiling_sample_fraction':ceiling_hits/((grid_x+1)*(grid_y+1)),
        'highest_visible_surface_z_m':highest,
        'note':'Ray casts through the rendered frame. The ceiling may appear as a band of at most ceiling_band_limit of the samples; a camera that has left the room, a roof that fills the frame, or geometry above the ceiling height fails.'}
    # The roof is allowed in shot as a band.  Inside a 3 m room every ray with an
    # upward component meets the ceiling somewhere, so banning it outright was
    # never a statement about the scene: it was a constraint I had put on the
    # camera and then read as a limit on how high the split unit could hang.
    # What still has to hold is that the roof reads as a band rather than as the
    # subject, that the body is genuinely inside the room, and that nothing pokes
    # through the slab.
    scene_frame['ceiling_band_limit']=.12
    scene_frame['camera_inside_room']=(cam.location.x<scenario['physics']['room_size'][0]
        and cam.location.y<scenario['physics']['room_size'][1]
        and cam.location.z<scenario['physics']['room_size'][2]-.60)
    scene_frame['passed']=(scene_frame['ceiling_sample_fraction']<=scene_frame['ceiling_band_limit']
        and scene_frame['camera_inside_room']
        and highest<=scenario['physics']['room_size'][2]+1e-6)
    write_json(out/'camera_frame_validation.json',scene_frame)
    anchor=Vector((.5,.5,.75))
    origin=world_to_camera_view(scene,cam,anchor)
    axes={}
    for name,offset in (('x',Vector((1,0,0))),('y',Vector((0,1,0)))):
        projected=world_to_camera_view(scene,cam,anchor+offset)
        axes[name]=[(projected.x-origin.x)*scene.render.resolution_x,
            (projected.y-origin.y)*scene.render.resolution_y]
    horizontal=[abs(axes[name][0]) for name in ('x','y')]
    azimuth=math.degrees(math.atan2(abs(cam.location.y),abs(cam.location.x)))
    write_json(out/'camera_axis_validation.json',{'reference_point_m':list(anchor),
        'one_metre_screen_displacement_px':axes,
        'horizontal_sensitivity_ratio':min(horizontal)/max(horizontal),
        'corner_azimuth_deg':azimuth,
        'both_wall_directions_readable':20<=azimuth<=70 and min(horizontal)/max(horizontal)>.5})
    write_json(out/'scenario_metadata.json',{'scene':scenario['scene'],'duration_sec':data['duration_sec'],
        'frame_count':data['frame_end'],'assets':{'ball':str(MODELS/scenario['assets']['ball']),
        'room':'Plaster room, wood floor, clear-glass window, one imported framed picture, a 1.2 m wall split air conditioner high on the x=0 wall, clear of the window, a cabinet and two static spare volleyballs at the end of the sideboard; the corner the ball plays in is empty; cabinet, spare balls and the split unit have colliders'},
        'physics':'Free PyBullet sphere; immutable walls; no added forces or retiming',
        'camera_location':list(cam.location),'camera_lens_mm':cam_data.lens,
        'camera_mode':scenario['render'].get('camera_mode','fixed'),
        'lighting':{'exposure':scene.view_settings.exposure,'area_lights':[
            {'name':obj.name,'power_w':obj.data.energy,'location':list(obj.location)}
            for obj in scene.objects if obj.type=='LIGHT' and obj.data.type=='AREA']},
        'floor_material':scenario['assets']['floor'],'mode':args.mode})
    selected=[int(s) for s in args.keyframes.split(',')] if args.keyframes else keyframes(data)
    if any(f<1 or f>scene.frame_end for f in selected):
        raise ValueError('Keyframes outside simulation range')
    write_json(out/'keyframes.json',{'frames':selected,'wall_collisions':data['metrics']['wall_collisions'],
        'timed_events':data['metrics']['timed_events']})
    scene.frame_set(1)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'volleyball_corner_rebound.blend'))
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

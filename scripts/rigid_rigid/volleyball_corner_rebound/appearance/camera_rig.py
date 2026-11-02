"""Camera setup shared by every case; fixed mode has no camera animation."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import bpy
import math
from mathutils import Vector

def animate_camera(camera, rows, config):
    camera.animation_data_clear()
    camera.data.animation_data_clear()
    camera.location=config['camera_location']
    camera.data.lens=config['lens_mm']
    camera.rotation_mode='QUATERNION'
    if config.get('camera_mode','fixed')=='fixed':
        # Clear both object and lens actions so an older tracking setup cannot
        # survive a switch to the locked camera, even in a saved Blender file.
        focus=Vector(config['camera_target'])
        rotation=(focus-camera.location).to_track_quat('-Z','Y')
        camera.rotation_quaternion=rotation
        return [{'frame_index':row['frame_index'],'location':list(camera.location),
            'quaternion_xyzw':[rotation.x,rotation.y,rotation.z,rotation.w],
            'focus':list(focus),'lens_mm':camera.data.lens} for row in rows]
    alpha=float(config.get('tracking_smoothing',.65))
    if not 0<alpha<=1:
        raise ValueError('tracking_smoothing must be in (0,1]')
    focus=None
    poses=[]
    previous=None
    speed=math.hypot(*rows[0].get('ball_linear_velocity',[0,0,0]))
    reference=float(config.get('tracking_speed_reference',5.85))
    time_scale=min(1,reference/max(speed,.001))
    for row in rows:
        if config.get('camera_mode','fixed')=='tracking':
            x,y,z=row['ball_location']
            moving=Vector((x,y,max(.25,z-.15)))
            hold=float(config.get('tracking_hold_sec',0))*time_scale
            blend=max(.001,float(config.get('tracking_blend_sec',.45))*time_scale)
            weight=max(0,min(1,(row['time_sec']-hold)/blend))
            weight=weight*weight*(3-2*weight)
            desired=Vector(config['camera_target']).lerp(moving,weight)
            focus=desired if focus is None else focus.lerp(desired,alpha)
        else:
            focus=Vector(config['camera_target'])
        rotation=(focus-camera.location).to_track_quat('-Z','Y')
        if previous is not None and rotation.dot(previous)<0:
            rotation.negate()
        camera.rotation_quaternion=rotation
        if config.get('adaptive_lens',False):
            distance=(Vector(row['ball_location'])-camera.location).length
            camera.data.lens=max(30,min(70,.055*36*distance/.21))
            camera.data.keyframe_insert('lens',frame=row['frame_index'])
        camera.keyframe_insert('rotation_quaternion',frame=row['frame_index'])
        poses.append({'frame_index':row['frame_index'],'location':list(camera.location),
            'quaternion_xyzw':[rotation.x,rotation.y,rotation.z,rotation.w],
            'focus':list(focus),'lens_mm':camera.data.lens})
        previous=rotation.copy()
    for curve in camera.animation_data.action.fcurves:
        for point in curve.keyframe_points:
            point.interpolation='LINEAR'
    if camera.data.animation_data:
        for curve in camera.data.animation_data.action.fcurves:
            for point in curve.keyframe_points:
                point.interpolation='LINEAR'
    return poses

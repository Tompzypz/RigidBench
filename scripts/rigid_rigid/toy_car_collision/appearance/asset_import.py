"""Evaluated GLB baking and wheel rig, adapted from scripts/toy_car_bottle."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import bpy
from mathutils import Vector

def world_bounds(objects):
    points=[obj.matrix_world@Vector(v) for obj in objects for v in obj.bound_box]
    lo=Vector([min(p[i] for p in points) for i in range(3)])
    hi=Vector([max(p[i] for p in points) for i in range(3)])
    return lo,hi


def bake_parts(path):
    """Import a GLB and bake every mesh to world space as a standalone object."""
    previous=set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported=[o for o in bpy.data.objects if o not in previous]
    # Some GLBs carry turntable/NLA animations. Remove them before baking:
    # otherwise imported scale keys override the metric size during playback.
    for imported_obj in imported:
        imported_obj.animation_data_clear()
        if imported_obj.data is not None and hasattr(imported_obj.data,'animation_data_clear'):
            imported_obj.data.animation_data_clear()
    bpy.context.view_layer.update()
    # Bake evaluated geometry, including the Hot Wheels armature's rest pose.
    # Removing its rig before evaluating would collapse/skew skinned meshes.
    depsgraph=bpy.context.evaluated_depsgraph_get()
    parts=[]
    for source in imported:
        if source.type!='MESH' or not len(source.data.materials):
            continue
        evaluated=source.evaluated_get(depsgraph)
        data=bpy.data.meshes.new_from_object(evaluated,preserve_all_data_layers=True,depsgraph=depsgraph)
        data.transform(source.matrix_world)
        part=bpy.data.objects.new(source.name+'_part',data)
        bpy.context.collection.objects.link(part)
        parts.append(part)
    for source in imported:
        if source.name in bpy.data.objects:
            bpy.data.objects.remove(source,do_unlink=True)
    return parts


def join_parts(parts,name):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in parts:
        obj.select_set(True)
    bpy.context.view_layer.objects.active=parts[0]
    bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    if len(parts)>1:
        bpy.ops.object.join()
    obj=bpy.context.view_layer.objects.active
    obj.name=name
    bpy.context.view_layer.update()
    return obj


def set_origin_to_centre(obj):
    """Move the origin to the object's bounding-box centre, leaving the mesh in place."""
    lo,hi=world_bounds([obj])
    bpy.context.scene.cursor.location=(lo+hi)/2
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active=obj
    bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
    bpy.context.view_layer.update()
    return lo,hi


def import_asset(path,name,target_axis=None,target_size=None):
    obj=join_parts(bake_parts(path),name)
    if target_axis is not None:
        # Only metric-scaled assets get re-centred. Re-centring a background like the
        # room moves its origin to the bbox centre, and the caller then sets location
        # to room_offset, which would silently shift the whole room by -centre.
        lo,hi=set_origin_to_centre(obj)
        obj.location=(0,0,0)
        factor=target_size/(hi-lo)[target_axis]
        obj.scale=(factor,)*3
        bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    bpy.context.view_layer.update()
    return obj


WHEEL_AXLE=(1,0,0)      # GLB width axis; the car's nose is local -Y, so this is the axle
WHEEL_SLACK=0.02        # tolerance used to recognise a wheel pair from its bounds alone


def import_car(path,name,target_axis,target_size):
    """Import the toy car, keep the wheel pairs as separate objects and return a rig.

    The rigid body in the simulation is a sliding box, so nothing here changes the
    trajectory: the wheels are spun afterwards purely so the car does not read as
    having its brakes locked on. Returns (rig, [(wheel_object, wheel_radius_metres)]).
    """
    parts=bake_parts(path)
    lo,hi=world_bounds(parts)
    size=hi-lo
    wheels,body=[],[]
    for part in parts:
        plo,phi=world_bounds([part])
        ps=phi-plo
        # A wheel pair is round in the two non-axle axes, nearly spans the car's width
        # and sits at the bottom of the model.
        circular=abs(ps[1]-ps[2])<=WHEEL_SLACK*max(ps[1],ps[2])
        if circular and ps[0]>=.8*size[0] and plo[2]<=lo[2]+.15*size[2]:
            wheels.append(part)
        else:
            body.append(part)
    # The Beetle has separate tyre, rim and hub meshes for each axle.
    # Merge coaxial pieces so each complete axle rotates about one shared pivot.
    if len(wheels)>2:
        groups=[]
        for part in wheels:
            plo,phi=world_bounds([part]);center=(plo+phi)/2
            group=next((g for g in groups if abs(g[0]-center.y)<size.y*.025),None)
            if group is None:groups.append([center.y,[part]])
            else:group[1].append(part)
        if len(groups)==2:
            wheels=[join_parts(g[1],name+'_axle_'+str(i)) for i,g in enumerate(groups)]
    if len(wheels)!=2:
        # Unknown asset layout: fall back to a single mesh with no wheel spin.
        for part in parts:
            data=part.data
            bpy.data.objects.remove(part,do_unlink=True)
            bpy.data.meshes.remove(data)
        return import_asset(path,name,target_axis,target_size),[]
    car=join_parts(body,name)
    radii=[]
    for wheel in wheels:
        wlo,whi=set_origin_to_centre(wheel)
        radii.append((whi-wlo)[2]/2)
    rig=bpy.data.objects.new(name+'_rig',None)
    rig.empty_display_size=size[target_axis]*.6
    bpy.context.collection.objects.link(rig)
    rig.location=(lo+hi)/2
    rig.rotation_mode='QUATERNION'
    bpy.context.view_layer.update()
    # Parent with keep-transform by hand: the rig may later carry location,
    # rotation and a uniform scale, all of which must not distort the wheels.
    inverse=rig.matrix_world.inverted()
    for obj in [car]+wheels:
        obj.parent=rig
        obj.matrix_parent_inverse=inverse
    factor=target_size/size[target_axis]
    rig.location=(0,0,0)
    rig.scale=(factor,)*3
    bpy.context.view_layer.update()
    return rig,[(wheel,radius*factor) for wheel,radius in zip(wheels,radii)]


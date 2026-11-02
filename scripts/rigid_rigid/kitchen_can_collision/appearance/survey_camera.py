"""Low-cost camera survey using the existing verified scene."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import json
from pathlib import Path
import bpy
from mathutils import Vector,Matrix
from bpy_extras.object_utils import world_to_camera_view

ROOT=_PCVE_ROOT
SOURCE=ROOT/'renders/pcve_kitchen_can_collision_suite'
OUT=ROOT/'renders/kitchen_can_camera_survey'
OUT.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(SOURCE/'cases/kitchen_can_collision_baseline/kitchen_can_collision.blend'))
s=bpy.context.scene;c=s.camera
s.render.resolution_x=640;s.render.resolution_y=360;s.render.resolution_percentage=100
s.cycles.samples=8;s.cycles.adaptive_threshold=.04
s.render.image_settings.file_format='PNG'
print('ROOM BOUNDS',flush=True)
for o in s.objects:
    if o.type=='MESH' and any(w in o.name.lower() for w in ('structure','window','stool','floor')):
        points=[o.matrix_world@Vector(v) for v in o.bound_box]
        print(o.name,[round(min(p[i] for p in points),2) for i in range(3)],
              [round(max(p[i] for p in points),2) for i in range(3)],flush=True)
poses=[f[k] for p in (SOURCE/'cases').glob('*/physics_transforms.json')
       for f in json.loads(p.read_text(encoding='utf-8'))['frames']
       for k in ('rolling_can','upright_can') if f[k]['present']]
presets=[('side_right',[1.25,-1.35,1.65],[.16,.05,1.015],38),
         ('reverse_window',[-1.10,1.55,1.65],[.16,.05,1.015],38),
         ('side_left',[-1.4,-1.15,1.75],[.16,.05,1.015],38)]
for name,loc,target,lens in presets:
    c.location=loc;c.rotation_euler=(Vector(target)-c.location).to_track_quat('-Z','Y').to_euler();c.data.lens=lens
    c.data.dof.focus_distance=(Vector(target)-c.location).length
    bpy.context.view_layer.update()
    uvs=[world_to_camera_view(s,c,Matrix(p['matrix_world'])@Vector((x,y,z)))
         for p in poses for x in (-.033,.033) for y in (-.033,.033) for z in (-.064,.064)]
    margin=min(min(v.x,1-v.x,v.y,1-v.y) for v in uvs)
    print('CAMERA',name,'margin',margin,flush=True)
    s.frame_set(22);s.render.filepath=str(OUT/f'{name}.png');bpy.ops.render.render(write_still=True)

"""Locally copied assets, thin PET walls, felt detail and daylight oak interior."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math,random
from pathlib import Path
from scene_geometry import BALL_RADIUS,BOTTLE_HEIGHT,BOTTLE_RADIUS,COM_HEIGHT,KEYS
MODELS=_PCVE_ROOT/'assets'/'models'
APPEARANCE_VERSION=2

def material(bpy,name,color,roughness=.5):
 m=bpy.data.materials.new(name);m.use_nodes=True;m.diffuse_color=(*color,1)
 bs=m.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(*color,1)
 bs.inputs['Roughness'].default_value=roughness;return m

def bake_asset(bpy,name):
 from mathutils import Matrix
 old=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str(MODELS/name))
 imported=[o for o in bpy.data.objects if o not in old]
 for o in imported:o.animation_data_clear()
 bpy.context.view_layer.update();deps=bpy.context.evaluated_depsgraph_get();result=[]
 for o in imported:
  if o.type!='MESH':continue
  mesh=bpy.data.meshes.new_from_object(o.evaluated_get(deps),preserve_all_data_layers=True,depsgraph=deps)
  mesh.transform(o.matrix_world);ob=bpy.data.objects.new(o.name+'_baked',mesh)
  bpy.context.collection.objects.link(ob);result.append(ob)
 for o in imported:bpy.data.objects.remove(o,do_unlink=True)
 return result

def bounds(parts):
 from mathutils import Vector
 pts=[v.co for o in parts for v in o.data.vertices]
 return Vector([min(v[i] for v in pts) for i in range(3)]),Vector([max(v[i] for v in pts) for i in range(3)])

def join(bpy,parts,name):
 bpy.ops.object.select_all(action='DESELECT')
 for o in parts:o.select_set(True)
 bpy.context.view_layer.objects.active=parts[0]
 if len(parts)>1:bpy.ops.object.join()
 o=bpy.context.object;o.name=name;return o

def make_empty_bottle(bpy):
 from mathutils import Vector
 from empty_bottle_geometry import shell_mesh
 from scene_geometry import EMPTY_BOTTLE_PROPERTIES
 parts=bake_asset(bpy,'plastic_water_bottle.glb');lo,hi=bounds(parts)
 from mathutils import Matrix
 transform=Matrix.Diagonal((2*BOTTLE_RADIUS/(hi.x-lo.x),2*BOTTLE_RADIUS/(hi.y-lo.y),BOTTLE_HEIGHT/(hi.z-lo.z),1))@Matrix.Translation(Vector((-(lo.x+hi.x)/2,-(lo.y+hi.y)/2,-lo.z)))
 cap_parts=[]
 for o in parts:
  o.data.transform(transform)
  is_cap=all(not m or not m.use_nodes or m.node_tree.nodes.get('Principled BSDF').inputs['Transmission Weight'].default_value<.5 for m in o.data.materials)
  if is_cap:cap_parts.append(o)
  else:bpy.data.objects.remove(o,do_unlink=True)
 if not cap_parts:raise RuntimeError('Expected original blue cap')
 lo,hi=bounds(cap_parts);cx=(lo.x+hi.x)/2;cy=(lo.y+hi.y)/2
 cap_radius=max(math.hypot(v.co.x-cx,v.co.y-cy) for o in cap_parts for v in o.data.vertices)
 for o in cap_parts:
  for v in o.data.vertices:
   v.co.x=(v.co.x-cx)*(.0177/cap_radius);v.co.y=(v.co.y-cy)*(.0177/cap_radius);v.co.z-=COM_HEIGHT
  for poly in o.data.polygons:poly.use_smooth=True
  for mat in o.data.materials:
   if not mat or not mat.use_nodes:continue
   bs=mat.node_tree.nodes.get('Principled BSDF')
   bs.inputs['Base Color'].default_value=(.012,.17,.27,1);bs.inputs['Metallic'].default_value=0;bs.inputs['Roughness'].default_value=.32
 vertices,faces=shell_mesh(EMPTY_BOTTLE_PROPERTIES['nominal_sidewall_thickness_m'])
 vertices=[(x,y,z-COM_HEIGHT) for x,y,z in vertices]
 mesh=bpy.data.meshes.new('PET outer and inner walls - air cavity and open neck')
 mesh.from_pydata(vertices,[],faces);mesh.update()
 body=bpy.data.objects.new('Empty PET body - no liquid or water-level surface',mesh);bpy.context.collection.objects.link(body)
 pet=material(bpy,'Clear empty PET - air inside',(.985,.995,1.),.055)
 n=pet.node_tree.nodes;l=pet.node_tree.links;bs=n.get('Principled BSDF')
 bs.inputs['IOR'].default_value=1.575;bs.inputs['Transmission Weight'].default_value=1.
 bs.inputs['Metallic'].default_value=0.;bs.inputs['Alpha'].default_value=1.
 # Transmitted daylight through thin PET: avoid opaque glass-like shadowing.
 output=n.get('Material Output');lightpath=n.new('ShaderNodeLightPath')
 transparent=n.new('ShaderNodeBsdfTransparent');mix=n.new('ShaderNodeMixShader')
 l.new(lightpath.outputs['Is Shadow Ray'],mix.inputs[0]);l.new(bs.outputs['BSDF'],mix.inputs[1]);l.new(transparent.outputs[0],mix.inputs[2]);l.new(mix.outputs[0],output.inputs['Surface'])
 mesh.materials.append(pet)
 for p in mesh.polygons:p.use_smooth=True
 body['contents']='air only';body['has_liquid']=False;body['shell_mass_kg']=EMPTY_BOTTLE_PROPERTIES['body_mass_kg']
 body['wall_thickness_m']=EMPTY_BOTTLE_PROPERTIES['nominal_sidewall_thickness_m']
 bottle=join(bpy,[body,*cap_parts],'bottle_left')
 bottle['contents']='air only';bottle['has_liquid']=False;bottle['reference_empty_mass_kg']=EMPTY_BOTTLE_PROPERTIES['total_mass_kg']
 return bottle

def make_objects(bpy):
 from mathutils import Vector,Matrix
 bottle=make_empty_bottle(bpy);result={'bottle_left':bottle}
 for k in ('bottle_right','bottle_added'):
  o=bottle.copy();o.data=bottle.data;bpy.context.collection.objects.link(o);o.name=k;result[k]=o
 parts=bake_asset(bpy,'tennis_ball.glb');lo,hi=bounds(parts);center=(lo+hi)/2
 radius=max((v.co-center).length for o in parts for v in o.data.vertices)
 for o in parts:
  for v in o.data.vertices:v.co=(v.co-center)*(BALL_RADIUS/radius)
  for poly in o.data.polygons:poly.use_smooth=True
  for mat in o.data.materials:
   if not mat or not mat.use_nodes:continue
   bs=mat.node_tree.nodes.get('Principled BSDF');n=mat.node_tree.nodes;l=mat.node_tree.links
   for socket,value in [('Metallic',0.),('Roughness',.87)]:
    for link in list(bs.inputs[socket].links):l.remove(link)
    bs.inputs[socket].default_value=value
   if bs.inputs.get('Sheen Weight'):bs.inputs['Sheen Weight'].default_value=.36
   coord=n.new('ShaderNodeTexCoord');noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=390
   l.new(coord.outputs['Generated'],noise.inputs['Vector']);bump=n.new('ShaderNodeBump')
   bump.inputs['Strength'].default_value=.24;bump.inputs['Distance'].default_value=.00010
   l.new(noise.outputs['Fac'],bump.inputs['Height'])
   if bs.inputs['Normal'].is_linked:l.new(bs.inputs['Normal'].links[0].from_socket,bump.inputs['Normal'])
   l.new(bump.outputs['Normal'],bs.inputs['Normal'])
 ball=join(bpy,parts,'tennis_ball');sub=ball.modifiers.new('Smooth felt silhouette','SUBSURF');sub.levels=2;sub.render_levels=2
 result['tennis_ball']=ball
 return result

def oak_floor(bpy):
 rng=random.Random(42);mats=[]
 for i in range(8):
  tone=rng.uniform(.88,1.12);m=material(bpy,'Natural oak board '+str(i),(.28*tone,.18*tone,.09*tone),.43)
  n=m.node_tree.nodes;l=m.node_tree.links;bs=n.get('Principled BSDF')
  coord=n.new('ShaderNodeTexCoord');mapping=n.new('ShaderNodeVectorMath');mapping.operation='MULTIPLY';mapping.inputs[1].default_value=(2,150,8)
  l.new(coord.outputs['Object'],mapping.inputs[0]);noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=1.;noise.inputs['Detail'].default_value=3.;noise.inputs['Roughness'].default_value=.7
  l.new(mapping.outputs['Vector'],noise.inputs['Vector']);ramp=n.new('ShaderNodeValToRGB')
  ramp.color_ramp.elements[0].color=(.14*tone,.073*tone,.030*tone,1);ramp.color_ramp.elements[1].color=(.43*tone,.28*tone,.14*tone,1)
  l.new(noise.outputs['Fac'],ramp.inputs[0]);l.new(ramp.outputs[0],bs.inputs['Base Color'])
  bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.18;bump.inputs['Distance'].default_value=.00012
  l.new(noise.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs[0],bs.inputs['Normal']);mats.append(m)
 verts=[];faces=[];ids=[]
 for row in range(59):
  y=-3+row*.14
  for col in range(9):
   x=-4.3+col*1.18+(row%3)*.3933
   dx=1.18-.0007;dy=.14-.0006;start=len(verts)
   verts.extend([(x,y,-.018),(x+dx,y,-.018),(x+dx,y+dy,-.018),(x,y+dy,-.018),
                 (x,y,0),(x+dx,y,0),(x+dx,y+dy,0),(x,y+dy,0)])
   faces.extend([tuple(start+i for i in f) for f in [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]])
   ids.extend([rng.randrange(8)]*6)
 mesh=bpy.data.meshes.new('Oak parquet boards');mesh.from_pydata(verts,[],faces);mesh.update()
 ob=bpy.data.objects.new('Level oak floor - matches physical plane',mesh);bpy.context.collection.objects.link(ob)
 for m in mats:mesh.materials.append(m)
 mesh.polygons.foreach_set('material_index',ids)
 mod=ob.modifiers.new('Fine board edge highlights','BEVEL');mod.width=.0003;mod.segments=2
 ob.modifiers.new('Floor normals','WEIGHTED_NORMAL')

def build_environment(bpy,scene):
 from mathutils import Matrix,Vector
 parts=bake_asset(bpy,'cloe_room.glb')
 transform=Matrix.Translation((.5,4.3,-.027491))@Matrix.Scale(.1,4)
 for o in parts:
  o.data.transform(transform)
  if o.name.startswith(('floor_','clo_','papers_')):o.hide_render=True;o.hide_viewport=True
  for mat in o.data.materials:
   if not mat or not mat.use_nodes:continue
   bs=mat.node_tree.nodes.get('Principled BSDF')
   if bs:
    bs.inputs['Metallic'].default_value=0
    if not bs.inputs['Roughness'].is_linked:bs.inputs['Roughness'].default_value=max(.4,bs.inputs['Roughness'].default_value)
    if bs.inputs.get('Emission Strength'):bs.inputs['Emission Strength'].default_value=0
 oak_floor(bpy)
 world=bpy.data.worlds.new('Soft blue daylight');world.use_nodes=True
 world.node_tree.nodes.get('Background').inputs['Color'].default_value=(.66,.76,.91,1)
 world.node_tree.nodes.get('Background').inputs['Strength'].default_value=.22;scene.world=world
 def area(name,loc,target,power,size,color,shape='DISK',size_y=None):
  light=bpy.data.lights.new(name,'AREA');light.energy=power;light.size=size;light.color=color;light.shape=shape
  if size_y:light.size_y=size_y
  ob=bpy.data.objects.new(name,light);scene.collection.objects.link(ob);ob.location=loc
  ob.rotation_euler=(Vector(target)-ob.location).to_track_quat('-Z','Y').to_euler()
 area('Broad daylight through right window',(2.0,.4,2.5),(0,0,.1),290,1.6,(1.,.90,.76))
 area('Soft ceiling bounce',(-1.,.7,2.6),(.1,0,.1),100,2.,(.75,.85,1.))
 area('Tall window reflection in PET',(-1.3,-.5,1.2),(0,0,.12),48,.3,(.82,.91,1.),'RECTANGLE',1.5)
 area('Gentle camera side fill',(.5,-2.,1.8),(0,0,.1),35,1.4,(1.,.94,.86))

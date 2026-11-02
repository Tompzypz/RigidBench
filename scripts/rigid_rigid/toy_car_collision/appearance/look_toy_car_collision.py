"""Locally copied furnished room and independently tinted die-cast toy cars."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math
from pathlib import Path
from scene_geometry import DIMENSIONS
MODELS=_PCVE_ROOT/'assets'/'models'
APPEARANCE_VERSION='desk-bed-clear-lane-two-distinct-toys-v2'
ROOM_ASSET='futuristic_room.glb'
CAR_ASSET='hotwheels_technetium__www.vecarz.com.glb'
RECEIVER_ASSET='cartoonish_toy_car.glb'
CAR_ASSETS=(CAR_ASSET,RECEIVER_ASSET)
ROOM_ORIGIN=(-2.0,.82,.05)
ROOM_YAW=0.

def build_environment(bpy,scene):
    from mathutils import Vector,Matrix
    transform=Matrix.Rotation(ROOM_YAW,4,'Z')@Matrix.Translation(-Vector(ROOM_ORIGIN))
    before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str(MODELS/ROOM_ASSET))
    bpy.context.view_layer.update()
    for o in set(bpy.data.objects)-before:
        o.animation_data_clear()
        if o.type in ('LIGHT','CAMERA') or o.name.startswith(('Ammobox','Books.001_','Books.006_','ChineseSoldier','OfficeChair_')):
            bpy.data.objects.remove(o,do_unlink=True);continue
        if o.parent is None:o.matrix_world=transform@o.matrix_world
    for m in bpy.data.materials:
        if not m.use_nodes:continue
        for n in m.node_tree.nodes:
            if n.type=='BSDF_PRINCIPLED' and n.inputs.get('Emission Strength'):n.inputs['Emission Strength'].default_value=0
    world=bpy.data.worlds.new('Soft apartment ambient');world.use_nodes=True;scene.world=world
    world.node_tree.nodes['Background'].inputs['Color'].default_value=(.45,.55,.7,1)
    world.node_tree.nodes['Background'].inputs['Strength'].default_value=.22
    for name,loc,power,size,color in [('Broad window',(-.4,-.9,2.4),180,2.,(1.,.91,.78)),('Cool room bounce',(2.,1.,2.2),120,1.8,(.78,.86,1.))]:
        bpy.ops.object.light_add(type='AREA',location=loc);o=bpy.context.object;o.name=name
        o.data.energy=power;o.data.shape='DISK';o.data.size=size;o.data.color=color
        o.rotation_euler=(Vector((.7,0,0))-o.location).to_track_quat('-Z','Y').to_euler()

def make_cars(bpy,present):
    from asset_import import import_car
    objects={};wheels={}
    for i,key in enumerate(('car_a','car_b')):
        if not present[i]:continue
        root,spin=import_car(MODELS/CAR_ASSETS[i],key,1,DIMENSIONS[i][0])
        physics=bpy.data.objects.new(key+'_physics',None);bpy.context.collection.objects.link(physics)
        root.parent=physics;root.rotation_mode='XYZ';root.rotation_euler=(0,0,math.pi/2)
        for part in root.children_recursive:
            if part.type!='MESH':continue
            for slot in part.material_slots:
                m=slot.material
                if not m:continue
                if i==1:
                    if m.use_nodes:
                        shader=m.node_tree.nodes.get('Principled BSDF')
                        if shader and 'Material.002' in m.name:
                            shader.inputs['Base Color'].default_value=(.025,.22,.31,1)
                            shader.inputs['Roughness'].default_value=.3
                            if shader.inputs.get('Coat Weight'):shader.inputs['Coat Weight'].default_value=.35
                    continue
                if 'Livery' not in m.name:continue
                mat=m.copy();mat.name=key+'_paint';slot.material=mat
                n=mat.node_tree.nodes;l=mat.node_tree.links;bs=n.get('Principled BSDF');base=bs.inputs['Base Color'];links=list(base.links)
                if links:
                    source=links[0].from_socket;l.remove(links[0]);mix=n.new('ShaderNodeMixRGB');mix.blend_type='MULTIPLY'
                    mix.inputs[0].default_value=.78;mix.inputs[2].default_value=((.95,.15,.045,1) if i==0 else (.07,.36,.95,1))
                    l.new(source,mix.inputs[1]);l.new(mix.outputs[0],base)
                bs.inputs['Metallic'].default_value=.72;bs.inputs['Roughness'].default_value=.24
                if bs.inputs.get('Coat Weight'):bs.inputs['Coat Weight'].default_value=.35
        objects[key]=physics;wheels[key]=spin
    return objects,wheels

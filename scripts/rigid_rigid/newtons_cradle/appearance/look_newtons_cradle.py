"""A private library study (no window); appearance only, physics lives in scene_geometry."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)

import sys
from pathlib import Path
sys.path.insert(0, str(_PCVE_ROOT / 'scripts'))
from pcve_blender_compat import (shader_socket, set_shader_input, eevee_engine, set_eevee_property, set_color_property)
from pathlib import Path
import math,random
ASSETS=_PCVE_ROOT/'assets'/'polyhaven'/'newtons_cradle'

def material(bpy,name,color,metal=0,roughness=.5):
    mat=bpy.data.materials.new(name);mat.diffuse_color=(*color,1);mat.use_nodes=True
    shader=mat.node_tree.nodes.get('Principled BSDF');shader.inputs['Base Color'].default_value=(*color,1);shader.inputs['Metallic'].default_value=metal;shader.inputs['Roughness'].default_value=roughness
    return mat

def wood(bpy,name,light=(.40,.24,.115),dark=(.20,.095,.038)):
    mat=material(bpy,name,light,roughness=.42);nodes=mat.node_tree.nodes;links=mat.node_tree.links
    coords=nodes.new('ShaderNodeTexCoord');scale=nodes.new('ShaderNodeVectorMath');scale.operation='MULTIPLY';scale.inputs[1].default_value=(2,65,4)
    links.new(coords.outputs['Generated'],scale.inputs[0]);noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=2.5;noise.inputs['Detail'].default_value=3
    links.new(scale.outputs[0],noise.inputs['Vector']);ramp=nodes.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].color=(*dark,1);ramp.color_ramp.elements[1].color=(*light,1)
    links.new(noise.outputs['Fac'],ramp.inputs[0]);shader=nodes.get('Principled BSDF');links.new(ramp.outputs['Color'],shader.inputs['Base Color'])
    bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.08;bump.inputs['Distance'].default_value=.00025
    links.new(noise.outputs['Fac'],bump.inputs['Height']);links.new(bump.outputs[0],shader.inputs['Normal']);return mat

def pbr_wood(bpy,name,floor=False):
    mat=material(bpy,name,(.28,.14,.06),roughness=.42);nodes=mat.node_tree.nodes;links=mat.node_tree.links;shader=nodes.get('Principled BSDF')
    tex=nodes.new('ShaderNodeTexCoord');mapping=nodes.new('ShaderNodeMapping');mapping.inputs['Scale'].default_value=(1.0,1.0,1.0)
    links.new(tex.outputs['Object'],mapping.inputs['Vector'])
    stem='wood_floor_worn' if floor else 'wood_table'
    for suffix,color_space,socket in [('diff','sRGB','Base Color'),('rough','Non-Color','Roughness'),('nor_gl','Non-Color',None)]:
        path=ASSETS/f'{stem}_{suffix}_2k.jpg'
        if not path.exists():
            if suffix=='diff':raise FileNotFoundError(f'{path}: run fetch_visual_assets.py once')
            continue
        img=bpy.data.images.load(str(path),check_existing=True);img.colorspace_settings.name=color_space
        node=nodes.new('ShaderNodeTexImage');node.image=img;node.projection='BOX';node.projection_blend=.18
        links.new(mapping.outputs['Vector'],node.inputs['Vector'])
        if socket:links.new(node.outputs['Color'],shader.inputs[socket])
        else:
            normal=nodes.new('ShaderNodeNormalMap');normal.inputs['Strength'].default_value=.24
            links.new(node.outputs['Color'],normal.inputs['Color']);links.new(normal.outputs['Normal'],shader.inputs['Normal'])
    set_shader_input(shader, 'Coat Weight', 0.16);set_shader_input(shader, 'Coat Roughness', 0.28)
    return mat

def textured_material(bpy,name,color,roughness=.5,metal=0,scale=160,bump_distance=.00012):
    mat=material(bpy,name,color,metal,roughness);nodes=mat.node_tree.nodes;links=mat.node_tree.links;shader=nodes.get('Principled BSDF')
    noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=scale;noise.inputs['Detail'].default_value=2
    rough=nodes.new('ShaderNodeMapRange');rough.inputs['From Min'].default_value=0;rough.inputs['From Max'].default_value=1
    rough.inputs['To Min'].default_value=roughness*.85;rough.inputs['To Max'].default_value=min(.95,roughness*1.15)
    links.new(noise.outputs['Fac'],rough.inputs[0]);links.new(rough.outputs[0],shader.inputs['Roughness'])
    bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.12;bump.inputs['Distance'].default_value=bump_distance
    links.new(noise.outputs['Fac'],bump.inputs['Height']);links.new(bump.outputs[0],shader.inputs['Normal']);return mat

def marble(bpy,name,base=(.26,.26,.29),vein=(.12,.12,.14),glint=(.36,.36,.39)):
    mat=material(bpy,name,base,roughness=.30);nodes=mat.node_tree.nodes;links=mat.node_tree.links;shader=nodes.get('Principled BSDF')
    coords=nodes.new('ShaderNodeTexCoord');mapping=nodes.new('ShaderNodeMapping');mapping.inputs['Scale'].default_value=(2.5,2.5,2.5)
    links.new(coords.outputs['Object'],mapping.inputs['Vector'])
    # Thin meandering veins follow the noise iso-contour at 0.5; broad tone drift underneath.
    noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=2.0;noise.inputs['Detail'].default_value=8
    noise.inputs['Roughness'].default_value=.72;noise.inputs['Distortion'].default_value=1.1
    links.new(mapping.outputs[0],noise.inputs['Vector'])
    ramp=nodes.new('ShaderNodeValToRGB');cr=ramp.color_ramp
    cr.elements[0].position=0.0;cr.elements[0].color=(*base,1)
    cr.elements[1].position=.475;cr.elements[1].color=(*base,1)
    v1=cr.elements.new(.50);v1.color=(*vein,1)
    v2=cr.elements.new(.525);v2.color=(*base,1)
    e=cr.elements.new(1.0);e.color=(*glint,1)
    links.new(noise.outputs['Fac'],ramp.inputs[0])
    drift=nodes.new('ShaderNodeTexNoise');drift.inputs['Scale'].default_value=.7;drift.inputs['Detail'].default_value=3
    links.new(mapping.outputs[0],drift.inputs['Vector'])
    mix=nodes.new('ShaderNodeMixRGB');mix.blend_type='MULTIPLY';mix.inputs[0].default_value=.22
    links.new(ramp.outputs['Color'],mix.inputs[1]);links.new(drift.outputs['Fac'],mix.inputs[2])
    links.new(mix.outputs['Color'],shader.inputs['Base Color'])
    rough=nodes.new('ShaderNodeMapRange');rough.inputs['From Min'].default_value=0;rough.inputs['From Max'].default_value=1
    rough.inputs['To Min'].default_value=.24;rough.inputs['To Max'].default_value=.42
    links.new(noise.outputs['Fac'],rough.inputs[0]);links.new(rough.outputs[0],shader.inputs['Roughness'])
    bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.15;bump.inputs['Distance'].default_value=.0004
    links.new(noise.outputs['Fac'],bump.inputs['Height']);links.new(bump.outputs[0],shader.inputs['Normal']);return mat

def box(bpy,name,location,size,mat,pitch=0,bevel=0):
    bpy.ops.mesh.primitive_cube_add(size=1,location=location);obj=bpy.context.object;obj.name=name;obj.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);obj.rotation_euler[1]=pitch;obj.data.materials.append(mat)
    if bevel:
        mod=obj.modifiers.new('Manufactured edge','BEVEL');mod.width=bevel;mod.segments=3;obj.modifiers.new('Weighted normals','WEIGHTED_NORMAL')
    return obj

def cylinder(bpy,name,location,radius,depth,mat,vertices=40):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices,radius=radius,depth=depth,location=location);obj=bpy.context.object;obj.name=name;obj.data.materials.append(mat)
    for poly in obj.data.polygons:poly.use_smooth=True
    bevel=obj.modifiers.new('Soft rim','BEVEL');bevel.width=min(.003,radius*.08);bevel.segments=3;obj.modifiers.new('Weighted normals','WEIGHTED_NORMAL');return obj

def rod(bpy,name,start,end,radius,mat):
    from mathutils import Vector
    a,b=Vector(start),Vector(end);v=b-a;obj=cylinder(bpy,name,(a+b)/2,radius,v.length,mat,20);obj.rotation_euler=v.to_track_quat('Z','Y').to_euler();return obj

def plant(bpy,name,location,size=1):
    from mathutils import Vector
    x,y,z=location;terracotta=textured_material(bpy,name+' ceramic',(.25,.09,.047),.78)
    bpy.ops.mesh.primitive_cone_add(vertices=48,radius1=.073*size,radius2=.092*size,depth=.16*size,location=[x,y,z+.08*size]);pot=bpy.context.object;pot.name=name+' planter';pot.data.materials.append(terracotta)
    for poly in pot.data.polygons:poly.use_smooth=True
    cylinder(bpy,name+' pot lip',[x,y,z+.156*size],.094*size,.016*size,terracotta)
    soil=material(bpy,name+' soil',(.033,.02,.012),roughness=.95);cylinder(bpy,name+' soil',[x,y,z+.16*size],.079*size,.004*size,soil)
    leaf_mats=[material(bpy,name+f' leaf {i}',color,roughness=.44) for i,color in enumerate(((.045,.11,.025),(.085,.17,.04),(.14,.22,.06)))]
    rng=random.Random(28)
    for i in range(13):
        angle=i*2.4;length=rng.uniform(.22,.42)*size;stem_start=Vector([x,y,z+.16*size]);end=stem_start+Vector([math.cos(angle)*.10*size,math.sin(angle)*.10*size,length])
        rod(bpy,name+' stem',stem_start,end,.002*size,leaf_mats[0])
        direction=Vector([math.cos(angle)*.7,math.sin(angle)*.7,.45]);bpy.ops.mesh.primitive_uv_sphere_add(segments=16,ring_count=8,location=end)
        leaf=bpy.context.object;leaf.name=name+' tapered leaf';leaf.scale=(.035*size,.008*size,.13*size);leaf.rotation_euler=direction.to_track_quat('Z','Y').to_euler();leaf.data.materials.append(leaf_mats[i%3])
        for poly in leaf.data.polygons:poly.use_smooth=True

def book(bpy,name,location,size,color,lean=0):
    cover=material(bpy,name+' cover',color,roughness=.6);pages=textured_material(bpy,name+' paper',(.40,.34,.24),.86,scale=220)
    x,y,z=location;w,d,h=size;c,s=math.cos(lean),math.sin(lean)
    def part(suffix,ox,oy,oz,sz,mat,bevel):
        rx,rz=ox*c+oz*s,-ox*s+oz*c
        return box(bpy,name+suffix,[x+rx,y+oy,z+rz],sz,mat,pitch=lean,bevel=bevel)
    part(' page block',0,0,0,[w*.87,d*.93,h*.98],pages,.001)
    for side in (-1,1):part(' bound cover',side*w*.46,0,0,[.008,d,h],cover,.002)
    part(' spine',0,-d/2,0,[w,.009,h],cover,.002)
    foil=material(bpy,name+' spine lettering',(.54,.40,.19),metal=.55)
    for shift in (-.33,.28):part(' spine bands',0,-d/2-.005,h*shift,[w*.78,.001,.004],foil,0)

BOOKSHELF_GLB=_PCVE_ROOT/'assets'/'models'/'bookshelf.glb'

def load_bookshelf_template(bpy):
    """Import the textured GLB bookcase once; bake world transforms into mesh data
    and keep the meshes as an unlinked template for instancing."""
    from mathutils import Matrix
    before=set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(BOOKSHELF_GLB))
    fresh=[o for o in bpy.data.objects if o not in before]
    for o in fresh:
        if o.type=='MESH':
            o.data.transform(o.matrix_world);o.parent=None;o.matrix_world=Matrix.Identity(4)
    meshes=[o for o in fresh if o.type=='MESH']
    for o in fresh:
        if o.type!='MESH':bpy.data.objects.remove(o,do_unlink=True)
    for o in meshes:
        for coll in list(o.users_collection):coll.objects.unlink(o)
    return meshes

def place_bookshelf(bpy,template,name,cx,back_y=1.52):
    """Instance the GLB bookcase against the back wall. Model space: front faces +X,
    5.01 wide x 1.24 deep x 3.82 tall. Uniform 0.54 scale gives h 2.06 / w 2.71;
    depth is squashed to ~0.42 m so the unit reads as normal furniture. Rotated so
    the front faces -Y (toward the camera)."""
    root=bpy.data.objects.new(name,None);bpy.context.scene.collection.objects.link(root)
    root.scale=(0.339,0.54,0.54);root.rotation_euler=(0,0,-math.pi/2)
    root.location=(cx-1.306,back_y+0.001,0)
    for o in template:
        c=o.copy();bpy.context.scene.collection.objects.link(c);c.parent=root
    return root

ENVIRONMENT_THEME='private_library'

def build_room(bpy,c):
    from scene_geometry import table_parts
    # --- Materials -----------------------------------------------------------
    walnut=pbr_wood(bpy,'Single slab dark walnut cabinet')
    shader=walnut.node_tree.nodes.get('Principled BSDF');shader.inputs['Roughness'].default_value=.34;set_shader_input(shader, 'Coat Weight', 0.28)
    floor=pbr_wood(bpy,'Dark stained study floor',floor=True)
    shader=floor.node_tree.nodes.get('Principled BSDF');nodes=floor.node_tree.nodes;links=floor.node_tree.links
    link=next(v for v in links if v.to_socket==shader.inputs['Base Color']);color=link.from_socket;links.remove(link)
    tint=nodes.new('ShaderNodeMixRGB');tint.blend_type='MULTIPLY';tint.inputs[0].default_value=1;tint.inputs[2].default_value=(.30,.25,.21,1)
    links.new(color,tint.inputs[1]);links.new(tint.outputs[0],shader.inputs['Base Color'])
    green=textured_material(bpy,'Deep library green walls',(.075,.145,.110),.94,scale=8,bump_distance=.0003)
    nodes=green.node_tree.nodes;links=green.node_tree.links;shader=nodes.get('Principled BSDF')
    blotch=nodes.new('ShaderNodeTexNoise');blotch.inputs['Scale'].default_value=2.4;blotch.inputs['Detail'].default_value=5;blotch.inputs['Roughness'].default_value=.7
    coordsg=nodes.new('ShaderNodeTexCoord');links.new(coordsg.outputs['Object'],blotch.inputs['Vector'])
    mixg=nodes.new('ShaderNodeMixRGB');mixg.inputs[1].default_value=(.062,.118,.092,1);mixg.inputs[2].default_value=(.094,.170,.130,1)
    links.new(blotch.outputs['Fac'],mixg.inputs[0]);links.new(mixg.outputs['Color'],shader.inputs['Base Color'])
    bookwood=wood(bpy,'Dark stained bookshelf',(.13,.06,.025),(.04,.015,.006))
    brass=material(bpy,'Library brass hardware',(.36,.23,.08),metal=.85,roughness=.28)
    stone=marble(bpy,'Grey marble fireplace')
    firebox=material(bpy,'Sooted firebox',(.012,.012,.014),roughness=.96)
    # --- Shell: floor + two closed walls (no window) -------------------------
    box(bpy,'Dark timber floor',[0,0,-.04],[14,14,.08],floor)
    back=1.55
    box(bpy,'Library back wall',[0,back,1.55],[7.0,.10,3.1],green)
    box(bpy,'Library side wall',[-3,0,1.55],[.10,4,3.1],green)
    box(bpy,'Walnut skirting',[.3,back-.07,.06],[6.4,.035,.12],walnut,bevel=.004)
    # --- Textured GLB bookcases flanking the central fireplace ----------------
    template=load_bookshelf_template(bpy)
    place_bookshelf(bpy,template,'GLB bookcase left',-2.03)
    place_bookshelf(bpy,template,'GLB bookcase right',2.03)
    # --- Central fireplace ---------------------------------------------------
    box(bpy,'Fireplace hearth',[0,1.34,.07],[1.30,.28,.14],stone,bevel=.008)
    box(bpy,'Fireplace surround',[0,1.32,.52],[1.22,.24,.76],stone,bevel=.01)
    box(bpy,'Fireplace opening',[0,1.16,.34],[.68,.10,.46],firebox)
    # Embers and logs sit inside the firebox mouth so the fire reads as a
    # live fire rather than a glowing panel; the glow lights the marble surround.
    coal=material(bpy,'Glowing coal',(.32,.10,.03),roughness=.8)
    coal_shader=coal.node_tree.nodes.get('Principled BSDF')
    set_shader_input(coal_shader, 'Emission Color', (1, 0.18, 0.02, 1));coal_shader.inputs['Emission Strength'].default_value=4.5
    rngc=random.Random(5)
    for i in range(12):
        cxp=rngc.uniform(-.26,.26);czp=rngc.uniform(.38,.51);r=rngc.uniform(.026,.044)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12,ring_count=6,radius=r,location=[cxp,1.13,czp])
        chunk=bpy.context.object;chunk.name=f'Fireplace coal {i}';chunk.scale=(1,.7,.55);chunk.data.materials.append(coal)
        for poly in chunk.data.polygons:poly.use_smooth=True
    logwood=wood(bpy,'Birch logs',(.46,.33,.17),(.24,.15,.065))
    for i,(lx,lz,tilt) in enumerate([(-.13,.38,-.12),(.12,.42,.10),(-.01,.46,.02)]):
        log=cylinder(bpy,f'Fireplace log {i}',[lx,1.105,lz],.042,.42,logwood,24)
        log.rotation_euler=(0,math.pi/2,tilt)
    box(bpy,'Fireplace mantel',[0,1.24,.93],[1.44,.34,.05],walnut,bevel=.008)
    # A framed artwork above the mantel replaces the heavy chimney, keeping the
    # wall behind the cradle legible; wide enough to enter the default framing.
    frame_wood=wood(bpy,'Picture frame timber',(.12,.05,.02),(.038,.015,.005))
    box(bpy,'Framed artwork',[0,1.44,1.46],[1.30,.07,.72],frame_wood,bevel=.006)
    box(bpy,'Artwork canvas',[0,1.40,1.46],[1.14,.02,.58],textured_material(bpy,'Artwork canvas',(.16,.20,.18),.82,scale=400,bump_distance=.00008))
    clock=wood(bpy,'Mantel clock timber',(.30,.17,.05),(.14,.07,.02))
    box(bpy,'Mantel clock',[.18,1.24,1.005],[.14,.09,.10],clock,bevel=.004)
    box(bpy,'Mantel clock face',[.18,1.185,.995],[.09,.002,.07],material(bpy,'Clock face ivory',(.72,.68,.58),roughness=.4))
    for sx,sz in ((-.58,.12),(.40,.10)):
        cylinder(bpy,'Candlestick',[sx,1.24,.955+sz/2],.012,sz,brass)
    # --- Wall sconces on the -X side wall ------------------------------------
    for z in (1.35,1.90):
        rod(bpy,f'Brass sconce arm {z}',[-2.86,0,z],[-2.70,0,z],.006,brass)
        bpy.ops.mesh.primitive_cone_add(vertices=32,radius1=.035,radius2=.015,depth=.05,location=[-2.68,0,z+.015]);obj=bpy.context.object;obj.name=f'Sconce shade {z}';obj.data.materials.append(material(bpy,f'Sconce shade {z}',(.35,.30,.18),roughness=.4))
        bpy.ops.object.light_add(type='POINT',location=[-2.66,0,z+.01]);bpy.context.object.data.energy=5.0;bpy.context.object.data.shadow_soft_size=.03;bpy.context.object.data.color=(1,.72,.42)
    # --- Display cabinet + front panel detailing -----------------------------
    for part in table_parts(c):
        box(bpy,part['name'],part['location'],part['size'],walnut,bevel=.008)
    for dx in (-.30,.30):
        box(bpy,'Cabinet door seam',[dx,-.256,.355],[.004,.002,.59],bookwood,bevel=.001)
        rod(bpy,'Cabinet pull',[dx,-.23,.36],[dx,-.262,.36],.006,brass)
    book(bpy,'Cabinet book lower',[-.55,.02,c['table_height']+.011],[.16,.22,.022],(.30,.10,.06))
    book(bpy,'Cabinet book upper',[-.53,.01,c['table_height']+.032],[.15,.21,.020],(.12,.14,.22),lean=.10)
    # --- Corner plant keeps the room alive -----------------------------------
    plant(bpy,'Corner library plant',[-1.05,.30,0],.6)
    return walnut


def configure_lighting(bpy,scene):
    from mathutils import Vector
    world=bpy.data.worlds.new('Library evening lighting');scene.world=world;world.use_nodes=True
    nodes=world.node_tree.nodes;links=world.node_tree.links;tex=nodes.new('ShaderNodeTexEnvironment')
    path=ASSETS/'wooden_lounge_2k.hdr'
    if not path.exists():raise FileNotFoundError(f'{path}: run fetch_visual_assets.py once')
    tex.image=bpy.data.images.load(str(path),check_existing=True)
    mapping=nodes.new('ShaderNodeMapping');mapping.inputs['Rotation'].default_value[2]=1.2;coords=nodes.new('ShaderNodeTexCoord')
    links.new(coords.outputs['Generated'],mapping.inputs['Vector']);links.new(mapping.outputs['Vector'],tex.inputs['Vector'])
    background=nodes.get('Background');background.inputs['Strength'].default_value=.44;links.new(tex.outputs['Color'],background.inputs['Color'])
    # Museum key light: a warm overhead spot isolates the cradle on the cabinet.
    bpy.ops.object.light_add(type='SPOT',location=[.28,-1.05,2.55]);spot=bpy.context.object;spot.name='Museum key spot';spot.data.energy=420;spot.data.spot_size=.62;spot.data.spot_blend=.40;spot.data.color=(1,.93,.82)
    spot.rotation_euler=(Vector([-.01,0,.85])-spot.location).to_track_quat('-Z','Y').to_euler()
    # Soft fill from the camera side keeps the cabinet from falling to black.
    bpy.ops.object.light_add(type='AREA',location=[1.0,-1.8,1.6]);fill=bpy.context.object;fill.name='Camera warm fill';fill.data.energy=85;fill.data.shape='DISK';fill.data.size=2.0;fill.data.color=(.72,.84,1.0)
    fill.rotation_euler=(Vector([0,0,.85])-fill.location).to_track_quat('-Z','Y').to_euler()
    # Warm wash keeps the bookcase wall legible instead of a dark murk.
    for sx in (-1,1):
        bpy.ops.object.light_add(type='AREA',location=[sx*1.05,-.35,1.85]);wash=bpy.context.object;wash.name=f'Bookcase warm wash {sx}';wash.data.energy=60;wash.data.shape='DISK';wash.data.size=1.2;wash.data.color=(1,.85,.68)
        wash.rotation_euler=(Vector([sx*1.9,1.2,1.15])-wash.location).to_track_quat('-Z','Y').to_euler()
    # Fireplace glow rising from the hearth.
    bpy.ops.object.light_add(type='POINT',location=[0,1.22,.48]);glow=bpy.context.object;glow.name='Fireplace glow';glow.data.energy=30.0;glow.data.shadow_soft_size=.12;glow.data.color=(1,.52,.20)
    # A low warm sun keeps a hint of direction without any window in view.
    bpy.ops.object.light_add(type='SUN',location=[-3,2,5]);sun=bpy.context.object;sun.name='Soft warm sun';sun.data.energy=.45;sun.data.angle=.15;sun.data.color=(1,.90,.74)
    sun.rotation_euler=(Vector([.5,-.5,.72])-sun.location).to_track_quat('-Z','Y').to_euler()

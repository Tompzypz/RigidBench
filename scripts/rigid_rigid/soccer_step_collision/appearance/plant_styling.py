"""Integrate the supplied fig scan with neutral ceramics and room lighting."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math
import bpy

def ceramic_planter(base,material_factory):
    clay=material_factory('Warm greige matte stoneware',(.30,.27,.22),.76,.0007)
    # A hollow tapered sleeve surrounds the original small scanned pot.
    profile=[(.126,0),(.131,.009),(.176,.260),(.180,.270),(.180,.280),
             (.176,.285),(.169,.283),(.165,.271),(.122,.028)]
    n=80; vertices=[]; faces=[]
    for radius,z in profile:
        vertices.extend([(radius*math.cos(i*math.tau/n),radius*math.sin(i*math.tau/n),z) for i in range(n)])
    for j in range(len(profile)-1):
        for i in range(n):
            a=j*n+i; b=j*n+(i+1)%n; c=(j+1)*n+(i+1)%n; d=(j+1)*n+i
            faces.append((a,b,c,d))
    faces.append(tuple(reversed(range(n))))
    faces.append(tuple((len(profile)-1)*n+i for i in range(n)))
    mesh=bpy.data.meshes.new('Closed hollow stoneware profile'); mesh.from_pydata(vertices,[],faces); mesh.update()
    obj=bpy.data.objects.new('Matte ceramic outer planter',mesh); bpy.context.collection.objects.link(obj)
    obj.location=base; mesh.materials.append(clay)
    for f in mesh.polygons: f.use_smooth=len(f.vertices)==4
    soil=material_factory('Dark potting soil',(.025,.018,.009),.97,.003)
    bpy.ops.mesh.primitive_cylinder_add(vertices=80,radius=.164,depth=.016,location=(base.x,base.y,base.z+.252))
    bpy.context.object.name='Recessed potting soil'; bpy.context.object.data.materials.append(soil)
    return obj

def integrate_scan(plant,height):
    """Remove the scan's cyan cast while retaining its original UV and leaf detail."""
    for mat in plant.data.materials:
        if not mat or not mat.use_nodes: continue
        images=[node.image for node in mat.node_tree.nodes if node.type=='TEX_IMAGE' and node.image]
        if not images: raise ValueError('Fiddle Leaf Fig material has no albedo texture')
        albedo=images[0]; nodes,links=mat.node_tree.nodes,mat.node_tree.links
        nodes.clear()
        tex=nodes.new('ShaderNodeTexImage'); tex.image=albedo
        luminance=nodes.new('ShaderNodeRGBToBW'); links.new(tex.outputs['Color'],luminance.inputs[0])
        tonal=nodes.new('ShaderNodeMapRange'); tonal.inputs['From Min'].default_value=.025
        tonal.inputs['From Max'].default_value=.60
        links.new(luminance.outputs[0],tonal.inputs['Value'])
        green=nodes.new('ShaderNodeValToRGB')
        green.color_ramp.elements[0].color=(.025,.065,.012,1)
        green.color_ramp.elements[1].color=(.24,.36,.065,1)
        green.color_ramp.elements.new(.45).color=(.075,.155,.024,1)
        links.new(tonal.outputs[0],green.inputs[0])
        blend=nodes.new('ShaderNodeMixRGB'); blend.inputs[0].default_value=.68
        links.new(tex.outputs['Color'],blend.inputs[1]); links.new(green.outputs[0],blend.inputs[2])
        leaf=nodes.new('ShaderNodeBsdfPrincipled')
        leaf.inputs['Roughness'].default_value=.64
        leaf.inputs['Specular IOR Level'].default_value=.25
        leaf.inputs['Subsurface Weight'].default_value=.025
        links.new(blend.outputs[0],leaf.inputs['Base Color'])
        brown=nodes.new('ShaderNodeValToRGB')
        brown.color_ramp.elements[0].color=(.018,.010,.005,1)
        brown.color_ramp.elements[1].color=(.18,.10,.035,1)
        links.new(tonal.outputs[0],brown.inputs[0])
        stem=nodes.new('ShaderNodeBsdfPrincipled'); stem.inputs['Roughness'].default_value=.85
        links.new(brown.outputs[0],stem.inputs['Base Color'])
        coord=nodes.new('ShaderNodeTexCoord'); xyz=nodes.new('ShaderNodeSeparateXYZ')
        links.new(coord.outputs['Object'],xyz.inputs[0])
        mask=nodes.new('ShaderNodeMapRange'); mask.inputs['From Min'].default_value=height*.43
        mask.inputs['From Max'].default_value=height*.55
        links.new(xyz.outputs['Z'],mask.inputs['Value'])
        mix=nodes.new('ShaderNodeMixShader'); links.new(mask.outputs[0],mix.inputs[0])
        links.new(stem.outputs[0],mix.inputs[1]); links.new(leaf.outputs[0],mix.inputs[2])
        out=nodes.new('ShaderNodeOutputMaterial'); links.new(mix.outputs[0],out.inputs['Surface'])

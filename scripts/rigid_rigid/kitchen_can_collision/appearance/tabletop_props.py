"""Static breakfast and food-preparation props, measured inside the real island."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math
from scene_geometry import COUNTER_Z


def add_tabletop_props(bpy,oak,material,ceramic,lathe,cube):
    from mathutils import Matrix,Vector
    before=set(bpy.data.objects)
    z=COUNTER_Z
    board_top=z+.0142
    cube(bpy,'Inset oak fruit cutting board',(.93,.165,z+.0072),(.30,.12,.014),oak,.006)
    coffee_start=set(bpy.data.objects)

    # A thin, visibly woven tea towel with a flat support patch below the cup.
    linen=material(bpy,'Natural flax woven tea towel',(.60,.54,.42),.94)
    stripe=material(bpy,'Rust red woven towel stripe',(.24,.055,.025),.92)
    nodes=linen.node_tree.nodes;links=linen.node_tree.links;bs=nodes.get('Principled BSDF')
    noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=1500
    bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.26;bump.inputs['Distance'].default_value=.00018
    links.new(noise.outputs['Fac'],bump.inputs['Height']);links.new(bump.outputs[0],bs.inputs['Normal'])
    n=48;verts=[]
    for j in range(n+1):
        v=j/n
        for i in range(n+1):
            u=i/n;dx=(u-.5)*.28;dy=(v-.5)*.17
            fade=min(1.,max(0.,(math.hypot(dx,dy)-.05)/.035))
            fold=.002*(1+math.sin(u*math.pi*9))*(.25+.75*v)*fade
            verts.append((-.76+dx,-.245+dy,z+.0018+fold))
    faces=[(j*(n+1)+i,j*(n+1)+i+1,(j+1)*(n+1)+i+1,(j+1)*(n+1)+i) for j in range(n) for i in range(n)]
    mesh=bpy.data.meshes.new('Fine folded tea towel mesh');mesh.from_pydata(verts,[],faces);mesh.update()
    towel=bpy.data.objects.new('Inset folded striped linen',mesh);bpy.context.collection.objects.link(towel)
    mesh.materials.append(linen);mesh.materials.append(stripe)
    for poly in mesh.polygons:
        poly.use_smooth=True
        if poly.index%n in (4,5,9):poly.material_index=1
    solid=towel.modifiers.new('Soft linen thickness','SOLIDIFY');solid.thickness=.0015

    cupmat=ceramic(bpy,'Warm ivory coffee cup glaze',(.61,.55,.43))
    cup=lathe(bpy,'Ivory stoneware coffee mug',[(0,0),(.023,0),(.027,.002),(.028,.007),
        (.038,.014),(.041,.083),(.0405,.089),(.0385,.091),(.0365,.089),(.0365,.084),
        (.034,.017),(.027,.012),(0,.012)],cupmat,128)
    cup.location=(-.76,-.245,z+.0018)
    bpy.ops.mesh.primitive_torus_add(major_radius=.027,minor_radius=.006,major_segments=64,minor_segments=16,
        location=(-.76+.046,-.245,z+.0018+.052),rotation=(math.pi/2,0,0))
    handle=bpy.context.object;handle.name='Coffee mug curved ceramic handle';handle.data.materials.append(cupmat)
    for poly in handle.data.polygons:poly.use_smooth=True
    coffee=material(bpy,'Fresh black coffee',(.018,.008,.003),.16)
    liquid=lathe(bpy,'Coffee surface and curved meniscus',[(0,.078),(.034,.078),(.036,.079),(.0365,.080)],coffee,128)
    liquid.location=cup.location

    steel=material(bpy,'Brushed stainless teaspoon',(.52,.55,.57),.24,.92)
    def ellipsoid(name,location,scale,mat):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=48,ring_count=24,location=location)
        obj=bpy.context.object;obj.name=name;obj.scale=scale;obj.data.materials.append(mat)
        for poly in obj.data.polygons:poly.use_smooth=True
        return obj
    ellipsoid('Teaspoon oval bowl',(-.652,-.215,z+.006),(.010,.016,.0025),steel)
    ellipsoid('Teaspoon slim handle',(-.652,-.255,z+.005),(.003,.031,.0018),steel)
    # Bring the breakfast setting into the visible foreground of the diagonal camera.
    for obj in set(bpy.data.objects)-coffee_start:obj.location.x+=.42

    def fruit_material(name,low,high,roughness):
        mat=material(bpy,name,high,roughness);nt=mat.node_tree;n=nt.nodes;l=nt.links;bs=n.get('Principled BSDF')
        coord=n.new('ShaderNodeTexCoord');noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=4
        l.new(coord.outputs['Generated'],noise.inputs['Vector'])
        ramp=n.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].color=(*low,1);ramp.color_ramp.elements[1].color=(*high,1)
        l.new(noise.outputs['Fac'],ramp.inputs[0]);l.new(ramp.outputs[0],bs.inputs['Base Color'])
        micro=n.new('ShaderNodeTexNoise');micro.inputs['Scale'].default_value=145;micro.inputs['Detail'].default_value=2
        l.new(coord.outputs['Generated'],micro.inputs['Vector'])
        bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.22;bump.inputs['Distance'].default_value=.0002
        l.new(micro.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs[0],bs.inputs['Normal'])
        if bs.inputs.get('Coat Weight'):bs.inputs['Coat Weight'].default_value=.22
        return mat
    red=fruit_material('Natural mottled red apple skin',(.14,.010,.004),(.48,.055,.014),.29)
    yellow=fruit_material('Fine textured lemon peel',(.40,.24,.008),(.83,.61,.025),.43)
    segments=96;rings=48;verts=[]
    for j in range(rings+1):
        t=math.pi*j/rings
        for i in range(segments):
            a=2*math.pi*i/segments
            r=.0365*math.sin(t)*(1+.025*math.cos(5*a)*math.sin(t)**2)
            r*=1+.08*math.exp(-((t-.65)/.4)**2)
            height=.035*math.cos(t)-.005*math.exp(-(t/.28)**2)+.002*math.exp(-((math.pi-t)/.3)**2)
            verts.append((r*math.cos(a),r*.95*math.sin(a),height))
    bottom=min(v[2] for v in verts);verts=[(x,y,h-bottom) for x,y,h in verts]
    faces=[(j*segments+i,(j+1)*segments+i,(j+1)*segments+(i+1)%segments,j*segments+(i+1)%segments)
           for j in range(rings) for i in range(segments)]
    mesh=bpy.data.meshes.new('Apple organic lobes and stem dimple');mesh.from_pydata(verts,[],faces);mesh.update()
    apple=bpy.data.objects.new('Red apple resting on cutting board',mesh);bpy.context.collection.objects.link(apple)
    apple.location=(.862,.165,board_top);mesh.materials.append(red)
    for poly in mesh.polygons:poly.use_smooth=True
    stemmat=material(bpy,'Fruit woody stem',(.09,.035,.010),.78)
    bpy.ops.mesh.primitive_cylinder_add(vertices=16,radius=.0014,depth=.012,location=(.862,.165,board_top+.067))
    stem=bpy.context.object;stem.name='Apple short woody stem';stem.rotation_euler.y=.23;stem.data.materials.append(stemmat)
    lemon=ellipsoid('Whole lemon resting on cutting board',(1.002,.163,board_top+.0255),(.037,.0245,.0255),yellow)
    for v in lemon.data.vertices:v.co.x*=1+.10*abs(v.co.x)**8
    lemon.rotation_euler.z=-.17

    sage=ceramic(bpy,'Sage glazed fruit bowl',(.16,.26,.18))
    bowl=lathe(bpy,'Low sage bowl of mandarins',[(0,0),(.030,0),(.034,.002),(.035,.006),
        (.052,.013),(.067,.026),(.074,.035),(.073,.039),(.069,.039),(.066,.031),
        (.050,.015),(.032,.008),(0,.008)],sage,128)
    bowl.location=(.66,-.235,z+.0002)
    orange=fruit_material('Dimpled mandarin orange peel',(.46,.085,.003),(.85,.26,.012),.39)
    green=material(bpy,'Mandarin small stem dimple',(.045,.105,.012),.68)
    for i,(dx,dy) in enumerate(((-.027,-.013),(.027,-.013),(0,.033))):
        fruit=ellipsoid(f'Mandarin {i+1} in fruit bowl',(.66+dx,-.235+dy,z+.041),(.025,.0245,.023),orange)
        ellipsoid(f'Mandarin {i+1} stem dimple',(.66+dx,-.235+dy,z+.0635),(.0026,.0026,.0006),green)

    # Small green-glass oil bottle with a separate liquid, label and screw cap.
    glass=material(bpy,'Tinted olive glass bottle',(.27,.35,.12),.15)
    bs=glass.node_tree.nodes.get('Principled BSDF');bs.inputs['Transmission Weight'].default_value=1.;bs.inputs['IOR'].default_value=1.47
    bottle=lathe(bpy,'Green glass olive oil bottle',[(0,0),(.022,0),(.027,.003),(.029,.009),(.029,.119),
        (.027,.133),(.014,.151),(.0125,.174),(.0125,.181),(.0105,.181),(.0105,.173),
        (.012,.152),(.025,.131),(.026,.118),(.026,.010),(.021,.006),(0,.006)],glass,128)
    bottle.location=(.49,.19,z+.0002)
    oil=material(bpy,'Golden olive oil',(.62,.43,.085),.08)
    bs=oil.node_tree.nodes.get('Principled BSDF');bs.inputs['Transmission Weight'].default_value=.90;bs.inputs['IOR'].default_value=1.46
    oilbody=lathe(bpy,'Olive oil fill',[(0,.008),(.024,.008),(.025,.012),(.025,.116),(.021,.130),(0,.130)],oil,96)
    oilbody.location=bottle.location
    capmat=material(bpy,'Dark olive bottle screw cap',(.028,.035,.014),.32,.35)
    cap=lathe(bpy,'Olive oil bottle cap',[(0,.178),(.0135,.178),(.0135,.194),(.012,.196),(0,.196)],capmat,96)
    cap.location=bottle.location
    paper=material(bpy,'Warm paper olive oil label',(.70,.64,.49),.78)
    angle=math.atan2(-1.15-.19,-1.4-.49);n=48
    verts=[(.02925*math.cos(angle+(i/n-.5)*2.1),.02925*math.sin(angle+(i/n-.5)*2.1),h)
           for h in (.038,.104) for i in range(n+1)]
    faces=[(i,i+1,i+n+2,i+n+1) for i in range(n)]
    mesh=bpy.data.meshes.new('Curved paper bottle label');mesh.from_pydata(verts,[],faces);mesh.update()
    label=bpy.data.objects.new('Olive oil paper label',mesh);bpy.context.collection.objects.link(label);label.location=bottle.location;mesh.materials.append(paper)
    for poly in mesh.polygons:poly.use_smooth=True
    ink=material(bpy,'Olive oil label print',(.035,.045,.018),.75)
    normal=Vector((math.cos(angle),math.sin(angle),0));tangent=Vector((-normal.y,normal.x,0))
    rotation=Matrix((tangent,Vector((0,0,1)),normal)).transposed().to_4x4()
    text=bpy.data.curves.new('Olive oil label lettering','FONT');text.body='OLIVE\nOIL';text.align_x='CENTER';text.align_y='CENTER';text.size=.009;text.space_line=1.15
    obj=bpy.data.objects.new('Olive oil bottle lettering',text);bpy.context.collection.objects.link(obj)
    obj.matrix_world=rotation;obj.location=bottle.location+normal*.0297+Vector((0,0,.071));text.materials.append(ink)
    for obj in set(bpy.data.objects)-before:obj['island_prop']=True


def validate_island_props(bpy):
    """Ray-check the real countertop under every prop footprint; retain a safety inset."""
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    bpy.context.view_layer.update()
    counter=next(o for o in bpy.context.scene.objects if o.name.startswith('Counters_'))
    # import_kitchen bakes this mesh to identity world space.
    tree=BVHTree.FromObject(counter,bpy.context.evaluated_depsgraph_get())
    safe=(-1.45,1.45,-.425,.24);records=[]
    for obj in bpy.context.scene.objects:
        if not obj.get('island_prop'):continue
        pts=[obj.matrix_world@Vector(c) for c in obj.bound_box]
        xmin,xmax=min(p.x for p in pts),max(p.x for p in pts)
        ymin,ymax=min(p.y for p in pts),max(p.y for p in pts)
        if not(safe[0]<=xmin<=xmax<=safe[1] and safe[2]<=ymin<=ymax<=safe[3]):
            raise RuntimeError(f'Prop not sufficiently inset from the actual counter: {obj.name}, {xmin,xmax,ymin,ymax}')
        for x in (xmin,(xmin+xmax)/2,xmax):
            for y in (ymin,(ymin+ymax)/2,ymax):
                hit=tree.ray_cast(Vector((x,y,COUNTER_Z+.3)),Vector((0,0,-1)),.6)[0]
                if hit is None or abs(hit.z-COUNTER_Z)>.002:raise RuntimeError(f'Prop outside actual stone surface: {obj.name}')
        records.append(dict(object_name=obj.name,xy_bounds=[xmin,xmax,ymin,ymax]))
    return dict(valid=True,actual_island_y_bounds=[-.495,.310],required_rear_inset_m=.070,props=records)

"""Manufacturing detail meshes and carton markings; no physics overrides."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math,random
from look_u_track_ball import box,material,textured_material

def continuous_rails(bpy,c,mat):
    from track_geometry import surface
    n=c['segments_per_branch'];xs=[-c['drive_length']+c['drive_length']*i/n for i in range(n)]+[c['exit_length']*i/n for i in range(n+1)]
    for side in (-1,1):
        vertices=[];faces=[]
        for x in xs:
            z,slope=surface(x,c);angle=math.atan(slope)
            for y,offset in ((side*(c['track_width']/2),0),(side*(c['track_width']/2+.018),0),(side*(c['track_width']/2),.07),(side*(c['track_width']/2+.018),.07)):
                vertices.append([x-offset*math.sin(angle),y,z+offset*math.cos(angle)])
        for i in range(len(xs)-1):
            a=4*i;b=a+4
            faces.extend([(a,b,b+1,a+1),(a+2,a+3,b+3,b+2),(a,a+2,b+2,b),(a+1,b+1,b+3,a+3)])
        faces.extend([(0,1,3,2),(len(vertices)-4,len(vertices)-2,len(vertices)-1,len(vertices)-3)])
        if side>0:faces=[tuple(reversed(face)) for face in faces]
        mesh=bpy.data.meshes.new('Continuous rail skin');mesh.from_pydata(vertices,[],faces);mesh.update()
        obj=bpy.data.objects.new(f'Continuous satin side rail {side}',mesh);bpy.context.scene.collection.objects.link(obj);obj.data.materials.append(mat)
        for face in mesh.polygons:face.use_smooth=True
        mesh.set_sharp_from_angle(angle=.5)
        bevel=obj.modifiers.new('Rolled rail edge','BEVEL');bevel.width=.0016;bevel.segments=4;bevel.limit_method='ANGLE';bevel.angle_limit=.5
        normal=obj.modifiers.new('Rail surface normals','WEIGHTED_NORMAL');normal.keep_sharp=True

def carton_details(bpy,target,c):
    w,d,h=c['box_size'];paper=textured_material(bpy,'Shipping label paper',(.76,.74,.66),.86,scale=280,bump_distance=.00005)
    ink=material(bpy,'Carton charcoal ink',(.018,.024,.022),roughness=.87)
    def attach(name,pos,size,mat):
        obj=box(bpy,name,pos,size,mat);obj.parent=target;return obj
    attach('Shipping label',[0,-d/2-.00035,.01],[w*.72,.00055,h*.40],paper)
    rng=random.Random(42)
    for i in range(20):
        x=-w*.26+i*w*.026
        attach('Barcode bar',[x,-d/2-.00070,.005],[w*rng.uniform(.005,.013),.0002,h*.10],ink)
    for z in (.031,.025):attach('Printed address line',[-w*.055,-d/2-.00075,z],[w*.43,.0002,.0018],ink)
    bpy.ops.object.text_add(location=[-.051,-d/2-.0008,-.020],rotation=[math.pi/2,0,0]);text=bpy.context.object;text.name='Handle with care label';text.data.body='HANDLE WITH CARE';text.data.size=.009;text.data.extrude=0;text.data.materials.append(ink);text.parent=target
    tape=textured_material(bpy,'Matte paper packing tape',(.39,.25,.12),.60,scale=240,bump_distance=.00008)
    attach('Top packing tape',[0,0,h/2+.00065],[w,.032,.0012],tape)
    attach('Front tape fold',[0,-d/2-.0004,h/2-.018],[.032,.0008,.036],tape)
    crease=material(bpy,'Fold seams',(.13,.08,.035),roughness=.9)
    attach('Box flap seam',[0,0,h/2+.0002],[.00065,d,.0003],crease)
    # Fine fluting at the upper edge communicates corrugated board thickness.
    for i in range(24):attach('Corrugation edge',[-w/2+.003+i*(w-.006)/24,-d/2-.00015,h/2-.002],[.0008,.0004,.002],crease)

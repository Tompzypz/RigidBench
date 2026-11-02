"""Closed hollow PET material only: open neck, connected inner/outer walls, no liquid."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math

BODY_MASS=.024
CAP_MASS=.002
PET_DENSITY=1380.
CAP_RADIUS=.0177
CAP_HEIGHT=.016727
CAP_Z=.2216365
SEGMENTS=128

def outer_profile():
    p=[(0.,.003),(.025,0.),(.034,.0018),(.039,.008),(.0405,.015),(.0405,.030)]
    for z in (.041,.061,.081,.101,.121,.141):
        p += [(.0405,z-.003),(.04095,z-.0015),(.04095,z+.0015),(.0405,z+.003)]
    p += [(.0405,.153),(.0385,.165),(.032,.180),(.022,.194),(.016,.202),(.0158,.210),(.0158,.222)]
    return p

def thickness_factor(z):
    if z<.012:return 1.+1.8*(1.-z/.012)
    if z>.194:return 1.+3.5*min(1.,(z-.194)/.016)
    return 1.

def shell_mesh(thickness,segments=SEGMENTS):
    outer=outer_profile();inner=[]
    for i,(r,z) in enumerate(outer):
        prev=outer[max(0,i-1)];nxt=outer[min(len(outer)-1,i+1)]
        dr,dz=nxt[0]-prev[0],nxt[1]-prev[1];length=math.hypot(dr,dz)
        t=thickness*thickness_factor(z)
        inner.append((max(0.,r-t*dz/length),z+t*dr/length))
    inner[0]=(0.,outer[0][1]+thickness*thickness_factor(outer[0][1]))
    profile=outer+list(reversed(inner))
    vertices=[];rings=[];faces=[]
    for r,z in profile:
        ids=[]
        for j in range(1 if r==0 else segments):
            theta=j*math.tau/segments
            # Five shallow base feet; no geometry crosses the support plane.
            foot=.00065*(1-math.cos(5*theta))*.5*max(0.,1-z/.012) if r>0 else 0.
            ids.append(len(vertices));vertices.append((r*math.cos(theta),r*math.sin(theta),z+foot))
        rings.append(ids)
    for a,b in zip(rings,rings[1:]):
        for j in range(segments):
            k=(j+1)%segments
            if len(a)==1:faces.append((a[0],b[k],b[j]))
            elif len(b)==1:faces.append((a[j],a[k],b[0]))
            else:
                faces.append((a[j],a[k],b[k]));faces.append((a[j],b[k],b[j]))
    return vertices,faces

def integrals(vertices,faces,second=False):
    volume=0.;first=[0.,0.,0.];squares=[0.,0.,0.]
    for ia,ib,ic in faces:
        a,b,c=vertices[ia],vertices[ib],vertices[ic]
        v=(a[0]*(b[1]*c[2]-b[2]*c[1])+a[1]*(b[2]*c[0]-b[0]*c[2])+a[2]*(b[0]*c[1]-b[1]*c[0]))/6.
        volume+=v
        if second:
            for i in range(3):
                first[i]+=v*(a[i]+b[i]+c[i])/4.
                squares[i]+=v*(a[i]*a[i]+b[i]*b[i]+c[i]*c[i]+a[i]*b[i]+a[i]*c[i]+b[i]*c[i])/10.
    sign=1 if volume>=0 else -1
    return abs(volume),[x*sign for x in first],[x*sign for x in squares]

def properties():
    low,high=.00004,.0006
    for _ in range(26):
        t=(low+high)/2;verts,faces=shell_mesh(t)
        volume,_,_=integrals(verts,faces)
        if volume*PET_DENSITY>BODY_MASS:high=t
        else:low=t
    thickness=(low+high)/2;verts,faces=shell_mesh(thickness)
    volume,first,second=integrals(verts,faces,True)
    body_com=[v/volume for v in first];total=BODY_MASS+CAP_MASS
    com_z=(BODY_MASS*body_com[2]+CAP_MASS*CAP_Z)/total
    # Axisymmetric shell + cap, about the composite centre of mass.
    raw=[PET_DENSITY*(second[1]+second[2]),PET_DENSITY*(second[0]+second[2]),PET_DENSITY*(second[0]+second[1])]
    cap_transverse=CAP_MASS*(3*CAP_RADIUS**2+CAP_HEIGHT**2)/12.
    ixx=raw[0]+cap_transverse+CAP_MASS*CAP_Z**2-total*com_z**2
    iyy=raw[1]+cap_transverse+CAP_MASS*CAP_Z**2-total*com_z**2
    izz=raw[2]+.5*CAP_MASS*CAP_RADIUS**2
    return dict(schema_version=1,contents='air only; no liquid',body_mass_kg=BODY_MASS,cap_mass_kg=CAP_MASS,
        total_mass_kg=total,pet_density_kg_m3=PET_DENSITY,body_material_volume_m3=volume,
        nominal_sidewall_thickness_m=thickness,base_thickness_factor=2.8,neck_thickness_factor=4.5,
        body_com_z_m=body_com[2],com_height_m=com_z,inertia_diagonal_kg_m2=[ixx,iyy,izz],
        mesh_vertices=len(verts),mesh_triangles=len(faces),
        mass_basis='24 g comparable PET bottle body + approximately 2 g closure; estimated, not a measurement of the mesh asset',
        sources=['https://petform.lk/Products/get_product_details/51','https://ckpetpackaging.co.za/closures-2/'])

if __name__=='__main__':
    import json
    from pathlib import Path
    data=properties()
    _PCVE_ROOT.joinpath('assets','scenarios','tennis_bottle_collision','empty_bottle_properties.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    print(json.dumps(data,indent=2))

"""One geometry definition for Bullet collision and Blender rendering."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math

def surface(x,c):
    length=c['drive_length'] if x<0 else c['exit_length']
    height=c['drive_height'] if x<0 else c['exit_height']
    return c['track_bottom']+height*(x/length)**2,2*height*x/length**2

def initial_state(c):
    """Place the ball at the requested centre X, clear of the collision mesh.

    Use the finite piecewise-linear track, including its end points, rather
    than shifting X along an analytic surface normal. This also supports
    release positions whose nearest contact is the drive branch's end point.
    """
    x=c['initial_position'];radius=c['ball_radius']+.0005
    n=c['segments_per_branch']
    xs=[-c['drive_length']+c['drive_length']*i/n for i in range(n)]+[c['exit_length']*i/n for i in range(n+1)]
    candidates=[]
    for x0,x1 in zip(xs,xs[1:]):
        if x1<x-radius or x0>x+radius:continue
        z0,_=surface(x0,c);z1,_=surface(x1,c)
        slope=(z1-z0)/(x1-x0)
        contact_x=min(x1,max(x0,x+radius*slope/math.sqrt(1+slope*slope)))
        dx=contact_x-x
        if abs(dx)>radius:continue
        height=z0+slope*(contact_x-x0)+math.sqrt(max(0,radius*radius-dx*dx))
        candidates.append((height,slope))
    if not candidates:raise ValueError('Initial ball position is outside the finite track')
    z,slope=max(candidates);angle=math.atan(slope)
    return [x,0,z], [c['initial_speed']*math.cos(angle),0,c['initial_speed']*math.sin(angle)]


def track_parts(c):
    parts=[];n=c['segments_per_branch'];thickness=c['track_thickness']
    for branch,(start,end) in enumerate(((-c['drive_length'],0),(0,c['exit_length']))):
        for i in range(n):
            x0=start+(end-start)*i/n;x1=start+(end-start)*(i+1)/n
            z0,_=surface(x0,c);z1,_=surface(x1,c)
            angle=math.atan2(z1-z0,x1-x0);length=math.hypot(x1-x0,z1-z0)
            centre=[(x0+x1)/2+thickness/2*math.sin(angle),0,(z0+z1)/2-thickness/2*math.cos(angle)]
            parts.append(dict(name=f'Track bed {branch}-{i}',location=centre,size=[length+.00015,c['track_width'],thickness],pitch=-angle,kind='track'))
            for sign in (-1,1):
                # Raised side rails prevent sideways escape without guiding along X.
                rail=[(x0+x1)/2-.035*math.sin(angle),sign*(c['track_width']/2+.009),(z0+z1)/2+.035*math.cos(angle)]
                parts.append(dict(name=f'Side rail {branch}-{i}-{sign}',location=rail,size=[length+.00015,.018,.07],pitch=-angle,kind='rail'))
    return parts

def table_parts(c):
    parts=[dict(name='Oak worktable',location=[.4,0,c['table_height']-.045],size=[3.4,1.1,.09],pitch=0,kind='wood')]
    for x in (-1.,1.8):
        for y in (-.43,.43): parts.append(dict(name='Table leg',location=[x,y,(c['table_height']-.09)/2],size=[.07,.07,c['table_height']-.09],pitch=0,kind='wood'))
    return parts

def track_mesh(c):
    """Continuous closed trough, avoiding artificial collision edges between boxes."""
    n=c['segments_per_branch'];xs=[-c['drive_length']+c['drive_length']*i/n for i in range(n)]+[c['exit_length']*i/n for i in range(n+1)]
    vertices=[];faces=[];w=c['track_width']/2;t=c['track_thickness']
    for x in xs:
        z,slope=surface(x,c);angle=math.atan(slope)
        for y,offset in ((-w,0),(w,0),(-w,-t),(w,-t)):
            vertices.append([x-offset*math.sin(angle),y,z+offset*math.cos(angle)])
    for i in range(len(xs)-1):
        a=4*i;b=a+4
        for quad in ((a,b,b+1,a+1),(a+2,a+3,b+3,b+2),(a,a+2,b+2,b),(a+1,b+1,b+3,a+3)):
            faces.extend([(quad[0],quad[1],quad[2]),(quad[0],quad[2],quad[3])])
    for quad in ((0,1,3,2),(4*(len(xs)-1),4*(len(xs)-1)+2,4*(len(xs)-1)+3,4*(len(xs)-1)+1)):
        faces.extend([(quad[0],quad[1],quad[2]),(quad[0],quad[2],quad[3])])
    return vertices,faces

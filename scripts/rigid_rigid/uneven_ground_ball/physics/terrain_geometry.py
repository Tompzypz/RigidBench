"""A continuous terrain mesh shared by collision, rendering and diagnostics.

The height field is the single source of truth: the collision mesh handed to
pybullet, the render mesh and the ground-truth archive are all built from it, so
what the camera sees is exactly what the ball touches.

Relief is layered on purpose:
  * a global grade along +x (the path falls away as the ball travels),
  * named features (wheel ruts, a crown between them, mounds, a pothole) whose
    footprint is several times the 5 cm mesh spacing, so the mesh represents
    them faithfully,
  * a fractal octave stack for the irregular small undulation of packed earth.

Anything finer than roughly two mesh cells cannot be represented by vertices and
is deliberately left to the material's normal/displacement maps, which change
shading only and never move the collision surface.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import numpy as np
import hashlib

# wavelength (m), amplitude (m), azimuth (deg), phase (rad).
# The ratios are deliberately irrational so the sum does not read as corrugation.
# Most of the energy sits between 0.2 m and 1 m: that is the band a 0.10 m ball
# actually feels and the band a camera at 3 m actually sees.
OCTAVES=((2.30,.0210,12,.31),(1.35,.0200,64,2.05),(.86,.0240,29,4.13),
         (.55,.0170,101,1.62),(.34,.0110,47,5.07),(.21,.0062,139,3.41))

def _fractal(x,y,roughness):
    """Domain-warped octave stack: irregular, deterministic, no RNG."""
    z=np.zeros_like(np.asarray(x,dtype=float))
    for wavelength,amplitude,azimuth,phase in OCTAVES:
        k=2*np.pi/wavelength;theta=np.radians(azimuth);kx,ky=k*np.cos(theta),k*np.sin(theta)
        warp=np.sin(.61*kx*x-1.27*ky*y+.87)
        z=z+amplitude*np.sin(kx*x+ky*y+phase+warp)
    return roughness*z

def height(x,y,c):
    x=np.asarray(x,dtype=float);y=np.asarray(y,dtype=float)
    z=c['terrain_base_height']+c['terrain_slope']*x
    for cx,cy,amplitude,sx,sy in c['bumps']:
        z=z+amplitude*np.exp(-.5*(((x-cx)/sx)**2+((y-cy)/sy)**2))
    return z+_fractal(x,y,c['terrain_roughness'])

def normal(x,y,c):
    eps=1e-4;dx=(height(x+eps,y,c)-height(x-eps,y,c))/(2*eps);dy=(height(x,y+eps,c)-height(x,y-eps,c))/(2*eps)
    n=np.array([-float(dx),-float(dy),1.]);return n/np.linalg.norm(n)

def curvature(x,y,c,h=.05):
    """Laplacian of the height field: negative in hollows, positive on crests.

    Used by the ground material to settle dust into dips and wear the crests,
    which is what makes relief readable long before lighting does.
    """
    lap=height(x+h,y,c)+height(x-h,y,c)+height(x,y+h,c)+height(x,y-h,c)-4*height(x,y,c)
    return lap/(h*h)

def terrain_mesh(c):
    lo,hi=c['terrain_bounds'];nx,ny=c['terrain_cells'];xs=np.linspace(lo[0],hi[0],nx+1);ys=np.linspace(lo[1],hi[1],ny+1)
    x,y=np.meshgrid(xs,ys,indexing='ij');v=np.column_stack((x.ravel(),y.ravel(),height(x,y,c).ravel()))
    faces=[]
    for i in range(nx):
        for j in range(ny):
            a=i*(ny+1)+j;b=a+ny+1
            faces.extend([(a,b,b+1),(a,b+1,a+1)])
    f=np.asarray(faces,dtype=np.int32)
    return v,f

def mesh_hash(v,f):return hashlib.sha256(np.asarray(v,dtype=np.float64).tobytes()+np.asarray(f,dtype=np.int32).tobytes()).hexdigest()

def initial_state(c):
    x,y=c['ball_start_xy'];n=normal(x,y,c);pos=np.array([x,y,float(height(x,y,c))])+(c['ball_radius']+.0015)*n
    direction=np.array([1.,0,0]);direction-=np.dot(direction,n)*n;direction/=np.linalg.norm(direction)
    velocity=c['ball_speed']*direction;omega=np.cross(n,velocity)/c['ball_radius']
    return pos,velocity,omega

def environment_boxes(c):
    parts=[]
    def add(name,location,size,kind):parts.append(dict(name=name,location=location,size=size,kind=kind))
    h=float(height(.3,2.62,c))
    add('Garden bench seat',[.3,2.62,h+.44],[1.4,.42,.07],'wood')
    add('Garden bench back',[.3,2.81,h+.70],[1.4,.05,.30],'wood')
    for x in (-.24,.84):
        for y in (2.48,2.76):
            foot=float(height(x,y,c));length=h+.405-foot
            add('Bench leg',[x,y,foot+length/2],[.055,.055,length],'wood')
    for x in (-1.9,2.9):
        z=float(height(x,2.55,c));add('Terracotta planter',[x,2.55,z+.16],[.38,.36,.32],'pot')
    for x in np.linspace(-2.8,6.6,40):
        z=float(height(x,3.1,c));add('Garden fence slat',[float(x),3.1,z+.40],[.15,.035,.80],'wood')
    return parts

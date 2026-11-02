"""PyBullet pendulums with ideal planar joints and sphere contacts, no scripted motion."""
# PCVE_UNIFIED_ENTRY_BEGIN

# Resolve the shared scripts directory, then this scene's module folders.
import sys as _clean_sys
from pathlib import Path as _CleanPath
_clean_scene_dir = _CleanPath(__file__).resolve().parent
_scripts_dir = _clean_scene_dir.parents[1]
_PCVE_PROJECT_ROOT = next(p for p in _clean_scene_dir.parents if (p / "assets").is_dir())
if str(_scripts_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_scripts_dir))
if str(_clean_scene_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_clean_scene_dir))
# Shared modules live in scripts/; scene-local modules live in this directory and
# its physics/, appearance/ and tools/ subdirectories.
for _scene_sub in ("", "physics", "appearance", "tools"):
    _scene_sub_dir = _clean_scene_dir / _scene_sub if _scene_sub else _clean_scene_dir
    if _scene_sub_dir.is_dir() and str(_scene_sub_dir) not in _clean_sys.path:
        _clean_sys.path.insert(1, str(_scene_sub_dir))
# PCVE_UNIFIED_ENTRY_END


from pathlib import Path
import argparse,json,sys,math
import runtime_support
import pybullet as p
from scene_config import defaults,merge,validate
from scene_geometry import pivots

def simulate(s):
    validate(s);c=s['physics'];r=s['render'];fps=r['fps']*r['slow_motion'];dt=1/c['physics_hz'];steps=c['physics_hz']//fps
    radius=c['ball_radius'];length=c['pendulum_length'];mass=4/3*math.pi*radius**3*c['ball_density'];anchors=pivots(c)
    presence=c.get('ball_presence',[1]*5)
    if len(presence)!=5 or any(v not in (0,1,False,True) for v in presence):raise ValueError('Invalid ball presence mask')
    total_frames=round(fps*r['duration_sec']);timed_by_frame={}
    for entry in c.get('timed_edits') or []:
        frame=entry.get('frame');params=entry.get('params')
        if not isinstance(frame,int) or not 2<=frame<=total_frames or not isinstance(params,dict) or set(params)!={'restitution'}:
            raise ValueError(f'Unsupported or invalid timed event: {entry!r}')
        value=float(params['restitution'])
        if not math.isfinite(value) or not 0<=value<=1:raise ValueError('Timed restitution must be finite and within 0..1')
        timed_by_frame.setdefault(frame,[]).append(value)
    client=p.connect(p.DIRECT)
    try:
        p.setGravity(*c['gravity'],physicsClientId=client);p.setTimeStep(dt,physicsClientId=client)
        p.setPhysicsEngineParameter(numSolverIterations=c['solver_iterations'],restitutionVelocityThreshold=0,contactSlop=0,contactERP=0,deterministicOverlappingPairs=1,physicsClientId=client)
        shape=p.createCollisionShape(p.GEOM_SPHERE,radius=radius,collisionFramePosition=[0,0,-length],physicsClientId=client)
        bodies={};objects={}
        for i,anchor in enumerate(anchors):
            key=f'ball_{i:02d}'
            if not presence[i]:
                # A deleted slot exists only as an absent marker: no body is
                # built, no contact can involve it, and every frame carries
                # ``present: False`` for it.
                objects[key]=dict(radius=radius,mass=mass,pivot=anchor,pendulum_length=length,present=False)
                continue
            body=p.createMultiBody(baseMass=0,basePosition=anchor,linkMasses=[mass],linkCollisionShapeIndices=[shape],linkVisualShapeIndices=[-1],
                linkPositions=[[0,0,0]],linkOrientations=[[0,0,0,1]],linkInertialFramePositions=[[0,0,-length]],linkInertialFrameOrientations=[[0,0,0,1]],
                linkParentIndices=[0],linkJointTypes=[p.JOINT_REVOLUTE],linkJointAxis=[[0,-1,0]],physicsClientId=client)
            # Bullet multiplies the two bodies' restitution values: sqrt(e) gives the requested pair e.
            p.changeDynamics(body,0,restitution=math.sqrt(c['restitution']),lateralFriction=0,linearDamping=0,angularDamping=0,
                jointDamping=c['joint_damping'],localInertiaDiagonal=[.4*mass*radius**2]*3,physicsClientId=client)
            p.setJointMotorControl2(body,0,p.VELOCITY_CONTROL,targetVelocity=0,force=0,physicsClientId=client)
            angle=-math.acos(1-c['initial_height']/length) if i==0 else 0
            p.resetJointState(body,0,angle,0,physicsClientId=client);bodies[key]=body
            objects[key]=dict(radius=radius,mass=mass,pivot=anchor,pendulum_length=length,present=True)
        frames=[];events={};hits=set();max_energy=0;max_overlap=0;timed_events=[]
        pair_restitution=c['restitution']
        def snapshot(body):
            state=p.getLinkState(body,0,computeLinkVelocity=1,computeForwardKinematics=1,physicsClientId=client);pos,q,v,w=state[0],state[1],state[6],state[7];rot=p.getMatrixFromQuaternion(q)
            angle=p.getJointState(body,0,physicsClientId=client)[0]
            return dict(present=True,location=list(pos),quaternion_xyzw=list(q),matrix_world=[[rot[3*i+j] for j in range(3)]+[pos[i]] for i in range(3)]+[[0,0,0,1]],
                linear_velocity=list(v),angular_velocity=list(w),speed=math.sqrt(sum(a*a for a in v)),pendulum_angle_rad=angle,height_m=length*(1-math.cos(angle)))
        for i in range(round(fps*r['duration_sec'])):
            if i:
                frame_index=i+1
                for value in timed_by_frame.get(frame_index,[]):
                    # A timed edit fires at the top of its frame: the new pair
                    # restitution is written into every live pendulum and the
                    # run continues from the state it had reached.
                    previous=pair_restitution;pair_restitution=float(value)
                    for body in bodies.values():
                        p.changeDynamics(body,0,restitution=math.sqrt(pair_restitution),physicsClientId=client)
                    timed_events.append(dict(frame=frame_index,time_sec=i/fps,parameter='restitution',
                        from_value=previous,to_value=pair_restitution,applied_in_simulation=True))
                for k in range(steps):
                    p.stepSimulation(physicsClientId=client);t=((i-1)*steps+k+1)*dt
                    for contact in p.getContactPoints(physicsClientId=client):
                        max_overlap=max(max_overlap,-contact[8]);pair=tuple(sorted((contact[1],contact[2])))
                        if contact[9]>0:
                            hits.add(pair);events.setdefault('first_ball_impact_sec',t)
            frame=dict(frame_index=i+1,time_sec=i/fps,playback_time_sec=i/r['fps'])
            for index in range(5):
                key=f'ball_{index:02d}'
                frame[key]=snapshot(bodies[key]) if key in bodies else dict(present=False)
            energy=sum(mass*9.81*frame[key]['height_m']+.5*mass*frame[key]['speed']**2+.5*.4*mass*radius**2*sum(w*w for w in frame[key]['angular_velocity']) for key in bodies)
            max_energy=max(max_energy,energy);frames.append(frame)
        initial_energy=mass*9.81*c['initial_height'];final_energy=sum(mass*9.81*frames[-1][key]['height_m']+.5*mass*frames[-1][key]['speed']**2+.5*.4*mass*radius**2*sum(w*w for w in frames[-1][key]['angular_velocity']) for key in bodies)
        peak=max(f['ball_04']['height_m'] for f in frames if f['ball_04'].get('present',True))
        finite=all(math.isfinite(v) for f in frames for key in bodies for v in f[key]['location']+f[key]['linear_velocity'])
        quality=dict(valid=finite and max_overlap<.001 and (initial_energy==0 or max_energy<initial_energy*1.05),events=events,
            contact_pairs=len(hits),last_ball_peak_height_m=peak,max_overlap_m=max_overlap,initial_energy_j=initial_energy,max_energy_j=max_energy,final_energy_j=final_energy,
            transmission_observed=peak>.005,energy_retained_fraction=final_energy/initial_energy if initial_energy else 0,
            present_objects=sorted(key for key in (f'ball_{i:02d}' for i in range(5)) if key in bodies),
            deleted_objects=sorted(key for key in (f'ball_{i:02d}' for i in range(5)) if key not in bodies),
            timed_events=timed_events)
        if not quality['valid']:raise RuntimeError(f'Invalid pendulum simulation: {quality}')
        return dict(schema_version=2,scene='newtons_cradle',simulator='pybullet',constraint_model='Fixed-length planar revolute pendulums; render twin suspension lines',scenario=s,objects=objects,frames=frames,quality=quality,
            timed_events=timed_events,
            fps=fps,sample_fps=fps,playback_fps=r['fps'],slow_motion=r['slow_motion'],frame_start=1,frame_end=len(frames),duration_sec=r['duration_sec'],
            physical_duration_sec=r['duration_sec'],playback_duration_sec=r['duration_sec']*r['slow_motion'],physics_dt=dt,substeps_per_frame=steps)
    finally:p.disconnect(client)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);parser.add_argument('--scenario-json',type=Path);parser.add_argument('--scenario-overrides-json',type=Path)
    parser.add_argument('--initial-height',type=float);parser.add_argument('--restitution',type=float);parser.add_argument('--fps',type=int);parser.add_argument('--duration-sec',type=float);parser.add_argument('--slow-motion',type=int,choices=(1,2,4,8))
    args=parser.parse_args();s=json.loads(args.scenario_json.read_text(encoding='utf-8')) if args.scenario_json else defaults()
    if args.scenario_overrides_json:s=merge(s,json.loads(args.scenario_overrides_json.read_text(encoding='utf-8')))
    for name in ('initial_height','restitution'):
        if getattr(args,name) is not None:s['physics'][name]=getattr(args,name)
    for name in ('fps','duration_sec','slow_motion'):
        if getattr(args,name) is not None:s['render'][name]=getattr(args,name)
    data=simulate(s);args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    args.out.with_name('simulation_metrics.json').write_text(json.dumps(data['quality'],indent=2),encoding='utf-8');print(json.dumps(data['quality']))
if __name__=='__main__':main()


# Load this seven-file scene bundle and the reference common scripts.
import sys as _clean_sys
from pathlib import Path as _CleanPath
_clean_scene_dir = _CleanPath(__file__).resolve().parent
_clean_scripts_dir = _clean_scene_dir.parent
_PCVE_PROJECT_ROOT = next(p for p in _clean_scene_dir.parents if (p / "assets").is_dir())
if str(_clean_scripts_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_clean_scripts_dir))
if str(_clean_scene_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_clean_scene_dir))
import edit_vocab as _clean_scene_bundle
_clean_scene_bundle.install_scene_support()




from pathlib import Path
import argparse,json,sys,math
from scene_support.u_track_ball import runtime_support  # Windows DLL directories before Bullet.
import pybullet as p
from scene_support.u_track_ball.scene_config import defaults,merge,validate
from scene_support.u_track_ball.track_geometry import track_parts,table_parts,initial_state,track_mesh

def simulate(s):
    validate(s);c=s['physics'];r=s['render'];sample_fps=r['fps']*r['slow_motion']
    # Constant integration step across all slow-motion choices.
    dt=1/(r['fps']*c['substeps']);steps=c['substeps']//r['slow_motion']
    if steps*r['slow_motion']!=c['substeps']: raise ValueError('Substeps must divide slow motion')
    client=p.connect(p.DIRECT)
    try:
        p.setGravity(*c['gravity'],physicsClientId=client);p.setTimeStep(dt,physicsClientId=client)
        p.setPhysicsEngineParameter(numSolverIterations=c['solver_iterations'],deterministicOverlappingPairs=1,physicsClientId=client)
        def body(part,mass=0):
            shape=p.createCollisionShape(p.GEOM_BOX,halfExtents=[v/2 for v in part['size']],physicsClientId=client)
            obj=p.createMultiBody(mass,shape,basePosition=part['location'],baseOrientation=p.getQuaternionFromEuler([0,part.get('pitch',0),0]),physicsClientId=client)
            return obj
        vertices,faces=track_mesh(c)
        shape=p.createCollisionShape(p.GEOM_MESH,vertices=vertices,indices=[i for f in faces for i in f],flags=p.GEOM_FORCE_CONCAVE_TRIMESH,physicsClientId=client)
        track=[p.createMultiBody(0,shape,physicsClientId=client)]
        p.changeDynamics(track[0],-1,lateralFriction=c['friction'],restitution=0,physicsClientId=client)
        for part in track_parts(c):
            if part['kind']=='track':continue
            obj=body(part);track.append(obj)
            p.changeDynamics(obj,-1,lateralFriction=c['friction'],restitution=0,physicsClientId=client)
        for part in table_parts(c):
            obj=body(part);p.changeDynamics(obj,-1,lateralFriction=c['table_friction'],restitution=0,physicsClientId=client)
        floor=body(dict(location=[0,0,-.04],size=[20,20,.08]))
        p.changeDynamics(floor,-1,lateralFriction=.6,restitution=0,physicsClientId=client)
        presence=c.get('box_presence',[1])
        if not isinstance(presence,list) or len(presence)!=1 or presence[0] not in (0,1):raise ValueError('Invalid box presence mask')
        box=body(dict(location=c['box_position'],size=c['box_size']),c['box_mass']) if presence[0] else None
        if box is not None:p.changeDynamics(box,-1,lateralFriction=.45,restitution=c['restitution'],linearDamping=0,angularDamping=0,physicsClientId=client)
        pos,vel=initial_state(c)
        shape=p.createCollisionShape(p.GEOM_SPHERE,radius=c['ball_radius'],physicsClientId=client)
        ball=p.createMultiBody(c['ball_mass'],shape,basePosition=pos,physicsClientId=client)
        p.changeDynamics(ball,-1,lateralFriction=c['ball_friction'],rollingFriction=c['rolling_friction'],spinningFriction=.0001,restitution=c['restitution'],linearDamping=0,angularDamping=0,physicsClientId=client)
        p.resetBaseVelocity(ball,linearVelocity=vel,physicsClientId=client)
        frames=[];events={};count=round(sample_fps*r['duration_sec'])
        # A timed DELETE lands partway through: the clip runs with the carton up
        # to that frame, the body is removed from the live simulation there, and
        # the ball carries on from the state it had reached.
        timed_by_frame={};timed_events=[]
        for event in c.get('timed_edits',[]):
            frame=event.get('frame');params=event.get('params')
            if not isinstance(frame,int) or not 2<=frame<=count or not isinstance(params,dict) or set(params)!={'box_presence'}:
                raise ValueError(f'Unsupported or invalid timed event: {event!r}')
            if params['box_presence']!=[0]:raise ValueError('Timed box_presence must be [0]')
            timed_by_frame.setdefault(frame,[]).append(params)
        def snapshot(obj):
            if obj is None:return dict(present=False)
            pos,q=p.getBasePositionAndOrientation(obj,physicsClientId=client);v,w=p.getBaseVelocity(obj,physicsClientId=client)
            rot=p.getMatrixFromQuaternion(q)
            matrix=[[rot[3*a+b] for b in range(3)]+[pos[a]] for a in range(3)]+[[0,0,0,1]]
            speed=math.sqrt(sum(value*value for value in v))
            return dict(present=True,location=list(pos),quaternion_xyzw=list(q),linear_velocity=list(v),angular_velocity=list(w),speed=speed,moving=speed>.01,matrix_world=matrix)
        for index in range(count):
            if index:
                for params in timed_by_frame.get(index+1,[]):
                    if box is not None:
                        p.removeBody(box,physicsClientId=client);box=None
                        timed_events.append(dict(frame=index+1,time_sec=index/sample_fps,parameter='box_presence',
                            before=[1],after=[0],applied_in_simulation=True,effective_from_frame=index+1))
                for k in range(steps):
                    p.stepSimulation(physicsClientId=client)
                    physical_time=((index-1)*steps+k+1)*dt
                    ball_pos=p.getBasePositionAndOrientation(ball,physicsClientId=client)[0]
                    if ball_pos[0]>c['exit_length']+c['ball_radius']:
                        events.setdefault('cleared_exit_sec',physical_time)
                    contact=p.getContactPoints(ball,box,physicsClientId=client) if box is not None else []
                    if contact:
                        events.setdefault('box_impact_sec',physical_time)
                        events['peak_box_contact_force_n']=max(events.get('peak_box_contact_force_n',0),max(point[9] for point in contact))
            ball_data=snapshot(ball);box_data=snapshot(box)
            for obj_data in (ball_data,box_data):
                if obj_data['present'] and not all(math.isfinite(v) for v in obj_data['location']+obj_data['linear_velocity']): raise RuntimeError('Nonfinite physics state')
            frames.append(dict(frame_index=index+1,time_sec=index/sample_fps,playback_time_sec=index/r['fps'],ball=ball_data,box=box_data))
        displacement=math.dist(frames[-1]['box']['location'],c['box_position']) if box is not None else 0.
        quality=dict(valid=True,cleared_exit='cleared_exit_sec' in events,hit_box='box_impact_sec' in events,box_final_displacement_m=displacement,events=events,
            timed_events=timed_events,present_objects=sorted(['ball']+['box'] if box is not None else ['ball']),timed_removal_frame=timed_events[0]['frame'] if timed_events else None)
        return dict(schema_version=2,scene='u_track_ball',simulator='pybullet',scenario=s,fps=sample_fps,sample_fps=sample_fps,playback_fps=r['fps'],slow_motion=r['slow_motion'],frame_start=1,frame_end=count,duration_sec=r['duration_sec'],physical_duration_sec=r['duration_sec'],playback_duration_sec=r['duration_sec']*r['slow_motion'],physics_dt=dt,substeps_per_frame=steps,objects=dict(ball=dict(radius=c['ball_radius'],mass=c['ball_mass'],initial_location=pos),box=dict(size=c['box_size'],mass=c['box_mass'],initial_location=c['box_position'])),quality=quality,frames=frames,timed_events=timed_events)
    finally: p.disconnect(client)

def main():
    parser=argparse.ArgumentParser(description='Asymmetric U track: gravity, rolling/sliding, ballistic exit and box collision')
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--scenario-json',type=Path)
    parser.add_argument('--scenario-overrides-json',type=Path)
    parser.add_argument('--friction',type=float);parser.add_argument('--initial-speed',type=float);parser.add_argument('--initial-position',type=float)
    parser.add_argument('--rolling-friction',type=float);parser.add_argument('--fps',type=int);parser.add_argument('--duration-sec',type=float);parser.add_argument('--slow-motion',type=int,choices=(1,2,4,8))
    args=parser.parse_args();s=json.loads(args.scenario_json.read_text(encoding='utf-8')) if args.scenario_json else defaults()
    if args.scenario_overrides_json:s=merge(s,json.loads(args.scenario_overrides_json.read_text(encoding='utf-8')))
    for name in ('friction','initial_speed','initial_position','rolling_friction'):
        if getattr(args,name) is not None:s['physics'][name]=getattr(args,name)
    for name in ('fps','duration_sec','slow_motion'):
        if getattr(args,name) is not None:s['render'][name]=getattr(args,name)
    data=simulate(s);args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    args.out.with_name('simulation_metrics.json').write_text(json.dumps(data['quality'],indent=2),encoding='utf-8')
    print(json.dumps(data['quality']))

if __name__=='__main__':main()

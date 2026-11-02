
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
import numpy as np
from scene_support.uneven_ground_ball import runtime_support
import pybullet as p
from scene_support.uneven_ground_ball.scene_config import defaults,merge,validate
from scene_support.uneven_ground_ball.terrain_geometry import terrain_mesh,mesh_hash,initial_state,normal,environment_boxes

def simulate(s):
    validate(s);c=s['physics'];r=s['render'];fps=r['fps']*r['slow_motion'];dt=1/(r['fps']*c['substeps']);steps=c['substeps']//r['slow_motion']
    vertices,faces=terrain_mesh(c);client=p.connect(p.DIRECT)
    try:
        p.setGravity(*c['gravity'],physicsClientId=client);p.setTimeStep(dt,physicsClientId=client)
        p.setPhysicsEngineParameter(numSolverIterations=c['solver_iterations'],deterministicOverlappingPairs=1,physicsClientId=client)
        # Split the same continuous surface into index-limited collision chunks.
        # No triangles are removed or moved at chunk boundaries.
        grounds=set()
        for start in range(0,len(faces),30000):
            chunk=faces[start:start+30000];used,indices=np.unique(chunk.ravel(),return_inverse=True)
            shape=p.createCollisionShape(p.GEOM_MESH,vertices=vertices[used].tolist(),indices=indices.tolist(),flags=p.GEOM_FORCE_CONCAVE_TRIMESH,physicsClientId=client)
            ground=p.createMultiBody(0,shape,physicsClientId=client);grounds.add(ground)
            p.changeDynamics(ground,-1,lateralFriction=c['ground_friction'],restitution=0,physicsClientId=client)
        for part in environment_boxes(c):
            shape=p.createCollisionShape(p.GEOM_BOX,halfExtents=[value/2 for value in part['size']],physicsClientId=client)
            body=p.createMultiBody(0,shape,basePosition=part['location'],physicsClientId=client);p.changeDynamics(body,-1,lateralFriction=.6,restitution=0,physicsClientId=client)
        floor_shape=p.createCollisionShape(p.GEOM_BOX,halfExtents=[30,30,.04],physicsClientId=client)
        floor=p.createMultiBody(0,floor_shape,basePosition=[0,0,-.19],physicsClientId=client)
        shape=p.createCollisionShape(p.GEOM_SPHERE,radius=c['ball_radius'],physicsClientId=client)
        pos,velocity,omega=initial_state(c);ball=p.createMultiBody(c['ball_mass'],shape,basePosition=pos.tolist(),physicsClientId=client)
        p.changeDynamics(ball,-1,lateralFriction=c['ball_friction'],rollingFriction=c['ball_rolling_friction'],restitution=c['ball_restitution'],
            localInertiaDiagonal=[c['ball_inertia_factor']*c['ball_mass']*c['ball_radius']**2]*3,linearDamping=0,angularDamping=0,physicsClientId=client)
        p.resetBaseVelocity(ball,linearVelocity=velocity.tolist(),angularVelocity=omega.tolist(),physicsClientId=client)
        # A timed friction edit lands partway through: the clip runs on the
        # baseline dynamics up to that frame, the new coefficients are written
        # into the live ball there, and the run carries on from that state.
        # The live coefficients are kept in a copy so the reported scenario
        # stays exactly the one that was requested.
        live=dict(c);total_frames=round(fps*r['duration_sec']);timed_by_frame={};timed_events=[]
        for event in c.get('timed_edits',[]):
            frame=event.get('frame');params=event.get('params')
            if not isinstance(frame,int) or not 2<=frame<=total_frames or not isinstance(params,dict) \
                    or not params or set(params)-{'ball_friction','ball_rolling_friction'}:
                raise ValueError(f'Unsupported or invalid timed event: {event!r}')
            for value in params.values():
                if not math.isfinite(value) or value<0:raise ValueError('Timed friction must be finite and nonnegative')
            timed_by_frame.setdefault(frame,[]).append(params)
        frames=[];outside=False;floor_hit=False;min_distance=0
        for i in range(round(fps*r['duration_sec'])):
            if i:
                for params in timed_by_frame.get(i+1,[]):
                    before={key:live[key] for key in params};live.update(params)
                    p.changeDynamics(ball,-1,lateralFriction=live['ball_friction'],rollingFriction=live['ball_rolling_friction'],physicsClientId=client)
                    timed_events.append(dict(frame=i+1,time_sec=i/fps,parameter='+'.join(sorted(params)),before=before,
                        after={key:live[key] for key in params},applied_in_simulation=True,effective_from_frame=i+1))
                for _ in range(steps):p.stepSimulation(physicsClientId=client)
            pos,q=p.getBasePositionAndOrientation(ball,physicsClientId=client);v,w=p.getBaseVelocity(ball,physicsClientId=client);rot=p.getMatrixFromQuaternion(q)
            if not all(math.isfinite(a) for a in list(pos)+list(v)+list(w)):raise RuntimeError('Nonfinite ball state')
            contacts=[point for point in p.getContactPoints(bodyA=ball,physicsClientId=client) if point[2] in grounds]
            if contacts:min_distance=min(min_distance,min(point[8] for point in contacts))
            lo,hi=c['terrain_bounds'];outside|=not all(a<=value<=b for a,b,value in zip(lo,hi,pos[:2]))
            floor_hit|=bool(p.getContactPoints(ball,floor,physicsClientId=client))
            n=np.array(contacts[0][7]) if contacts else normal(pos[0],pos[1],c)
            slip=np.array(v)+np.cross(np.array(w),-c['ball_radius']*n);slip-=np.dot(slip,n)*n
            state=dict(present=True,location=list(pos),quaternion_xyzw=list(q),matrix_world=[[rot[3*a+b] for b in range(3)]+[pos[a]] for a in range(3)]+[[0,0,0,1]],
                linear_velocity=list(v),angular_velocity=list(w),speed=float(np.linalg.norm(v)),ground_contact=bool(contacts),contact_slip_speed_m_s=float(np.linalg.norm(slip)) if contacts else None)
            frames.append(dict(frame_index=i+1,time_sec=i/fps,playback_time_sec=i/r['fps'],ball=state))
        positions=np.array([f['ball']['location'] for f in frames]);distances=np.linalg.norm(np.diff(positions,axis=0),axis=1)
        quality=dict(valid=not outside and not floor_hit and min_distance>-.005,rolling_contact_fraction=sum(f['ball']['ground_contact'] for f in frames)/len(frames),
            min_sampled_contact_distance_m=min_distance,left_terrain=outside,fallback_floor_contact=floor_hit,path_length_m=float(distances.sum()),
            final_location=positions[-1].tolist(),max_lateral_deviation_m=float(np.max(np.abs(positions[:,1]-positions[0,1]))),
            final_speed_m_s=frames[-1]['ball']['speed'],max_speed_m_s=max(f['ball']['speed'] for f in frames),
            timed_events=timed_events,
            note='Rigid sphere with Coulomb friction and rolling resistance; the trajectory is mass-independent, so speed and resistance edits drive the visible differences.')
        return dict(schema_version=2,scene='uneven_ground_ball',simulator='pybullet',scenario=s,objects={'ball':dict(radius=c['ball_radius'],mass=c['ball_mass'],initial_location=positions[0].tolist())},
            terrain=dict(geometry_file='terrain_mesh.npz',mesh_hash=mesh_hash(vertices,faces),vertex_count=len(vertices),triangle_count=len(faces),collision_chunks=len(grounds)),quality=quality,frames=frames,timed_events=timed_events,
            fps=fps,sample_fps=fps,playback_fps=r['fps'],slow_motion=r['slow_motion'],frame_start=1,frame_end=len(frames),duration_sec=r['duration_sec'],
            physical_duration_sec=r['duration_sec'],playback_duration_sec=r['duration_sec']*r['slow_motion'],physics_dt=dt,substeps_per_frame=steps),(vertices,faces)
    finally:p.disconnect(client)

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--scenario-json',type=Path);p.add_argument('--scenario-overrides-json',type=Path)
    for name in ('ball-mass','ball-speed','ball-friction','rolling-friction'):p.add_argument('--'+name,type=float)
    p.add_argument('--fps',type=int);p.add_argument('--duration-sec',type=float);p.add_argument('--slow-motion',type=int,choices=(1,2,4,8))
    args=p.parse_args();s=json.loads(args.scenario_json.read_text(encoding='utf-8')) if args.scenario_json else defaults()
    if args.scenario_overrides_json:s=merge(s,json.loads(args.scenario_overrides_json.read_text(encoding='utf-8')))
    for key in ('ball_mass','ball_speed'):
        if getattr(args,key) is not None:s['physics'][key]=getattr(args,key)
    if args.ball_friction is not None:
        previous=s['physics']['ball_friction'];s['physics']['ball_rolling_friction']*=args.ball_friction/previous if previous>0 else 1
        s['physics']['ball_friction']=args.ball_friction
    if args.rolling_friction is not None:s['physics']['ball_rolling_friction']=args.rolling_friction
    for key in ('fps','duration_sec','slow_motion'):
        if getattr(args,key) is not None:s['render'][key]=getattr(args,key)
    data,(v,f)=simulate(s);args.out.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(args.out.parent/'terrain_mesh.npz',vertices=v,faces=f)
    args.out.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8');args.out.with_name('simulation_metrics.json').write_text(json.dumps(data['quality'],indent=2),encoding='utf-8');print(json.dumps(data['quality']))

if __name__=='__main__':main()

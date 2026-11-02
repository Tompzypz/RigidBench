"""Ball rolls across the tabletop into a stacked block pile.

The ball is never launched: it starts in rolling contact with the tabletop and
the simulation gives it the no-slip spin, so mass and speed edits change how far
the pile is nudged rather than how violently a projectile smashes through it.
"""
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
from building_geometry import building_blocks,table_parts

def simulate(s):
    validate(s);c=s['physics'];r=s['render'];fps=r['fps']*r['slow_motion']
    dt=1/(r['fps']*c['substeps']);steps=c['substeps']//r['slow_motion'];client=p.connect(p.DIRECT)
    try:
        gravity=c['gravity'];gravity_norm=math.sqrt(sum(value*value for value in gravity))
        gravity_strength=float(c.get('gravity_strength',gravity_norm))
        if not math.isfinite(gravity_strength) or gravity_strength<0 or gravity_norm==0:raise ValueError('Invalid gravity magnitude or direction')
        def gravity_vector(strength):
            return [value*strength/gravity_norm for value in gravity]
        p.setGravity(*gravity_vector(gravity_strength),physicsClientId=client);p.setTimeStep(dt,physicsClientId=client)
        p.setPhysicsEngineParameter(numSolverIterations=c['solver_iterations'],deterministicOverlappingPairs=1,physicsClientId=client)
        def box(location,size,mass=0,angle=0):
            shape=p.createCollisionShape(p.GEOM_BOX,halfExtents=[v/2 for v in size],physicsClientId=client)
            return p.createMultiBody(mass,shape,basePosition=location,baseOrientation=p.getQuaternionFromEuler([0,0,angle]),physicsClientId=client)
        for part in table_parts(c):
            obj=box(part['location'],part['size']);p.changeDynamics(obj,-1,lateralFriction=c['table_friction'],restitution=0,physicsClientId=client)
        floor=box([0,0,-.04],[20,20,.08]);p.changeDynamics(floor,-1,lateralFriction=.6,restitution=0,physicsClientId=client)
        blocks=building_blocks(c);presence=c.get('block_presence',[1]*len(blocks))
        if len(presence)!=len(blocks) or any(value not in (0,1,False,True) for value in presence):raise ValueError('Invalid block presence mask')
        active_blocks=[block for index,block in enumerate(blocks) if presence[index]]
        bodies={}
        for block in active_blocks:
            obj=box(block['location'],block['size'],block['mass'],block['angle']);bodies[block['object_id']]=obj
            p.changeDynamics(obj,-1,lateralFriction=c['block_friction'],restitution=c['block_restitution'],linearDamping=.01,angularDamping=.01,physicsClientId=client)
        for _ in range(round(c['settle_sec']/dt)):p.stepSimulation(physicsClientId=client)
        def snapshot(obj):
            pos,q=p.getBasePositionAndOrientation(obj,physicsClientId=client);v,w=p.getBaseVelocity(obj,physicsClientId=client);rot=p.getMatrixFromQuaternion(q)
            return dict(present=True,location=list(pos),quaternion_xyzw=list(q),matrix_world=[[rot[3*i+j] for j in range(3)]+[pos[i]] for i in range(3)]+[[0,0,0,1]],linear_velocity=list(v),angular_velocity=list(w),speed=math.sqrt(sum(a*a for a in v)))
        settled={key:snapshot(obj) for key,obj in bodies.items()}
        settle_drift=max(math.dist(settled[b['object_id']]['location'],b['location']) for b in active_blocks)
        settle_speed=max(v['speed'] for v in settled.values())
        if settle_drift>.005 or settle_speed>.03:raise RuntimeError(f'Stack unstable before release: drift={settle_drift:g}, speed={settle_speed:g}')
        shape=p.createCollisionShape(p.GEOM_SPHERE,radius=c['ball_radius'],physicsClientId=client)
        ball=p.createMultiBody(c['ball_mass'],shape,basePosition=c['ball_initial_location'],physicsClientId=client)
        p.changeDynamics(ball,-1,lateralFriction=c['ball_friction'],rollingFriction=c['ball_rolling_friction'],restitution=c['ball_restitution'],linearDamping=0,angularDamping=0,physicsClientId=client)
        # Rolling without slipping on the tabletop: w_y = v_x / r for a +X roll.
        p.resetBaseVelocity(ball,linearVelocity=[c['ball_speed'],0,0],
            angularVelocity=[0,c['ball_speed']/c['ball_radius'],0],physicsClientId=client)
        bodies={'ball':ball,**bodies};frames=[];events={};impacted=set();timed_events=[]
        reverse={obj:key for key,obj in bodies.items()}
        total_frames=round(fps*r['duration_sec']);timed_by_frame={}
        for event in c.get('timed_edits',[]):
            frame=event.get('frame');params=event.get('params')
            if not isinstance(frame,int) or not 2<=frame<=total_frames or not isinstance(params,dict) or set(params)!={'gravity_strength'}:
                raise ValueError(f'Unsupported or invalid timed event: {event!r}')
            if not math.isfinite(params['gravity_strength']) or params['gravity_strength']<0:raise ValueError('Timed gravity must be finite and nonnegative')
            timed_by_frame.setdefault(frame,[]).append(params)
        object_presence={'ball':True,**{block['object_id']:block['object_id'] in bodies for block in blocks}}
        for i in range(total_frames):
            frame_index=i+1
            if i:
                for params in timed_by_frame.get(frame_index,[]):
                    previous=gravity_strength;gravity_strength=float(params['gravity_strength'])
                    p.setGravity(*gravity_vector(gravity_strength),physicsClientId=client)
                    timed_events.append(dict(frame=frame_index,time_sec=i/fps,parameter='gravity_strength',from_value=previous,
                        to_value=gravity_strength,applied_in_simulation=True))
                for k in range(steps):
                    p.stepSimulation(physicsClientId=client);t=((i-1)*steps+k+1)*dt
                    for contact in p.getContactPoints(bodyA=ball,physicsClientId=client):
                        key=reverse.get(contact[2])
                        if key and key!='ball':
                            events.setdefault('first_block_impact_sec',t);impacted.add(key)
            frame=dict(frame_index=frame_index,time_sec=i/fps,playback_time_sec=i/r['fps'],presence=dict(object_presence))
            for key,obj in bodies.items():
                state=snapshot(obj)
                if not all(math.isfinite(v) for v in state['location']+state['linear_velocity']):raise RuntimeError('Nonfinite rigid state')
                frame[key]=state
            frames.append(frame)
        def tilt_deg(state):
            rotation=state['matrix_world'];up=rotation[2][2]
            return math.degrees(math.acos(max(-1.,min(1.,up))))
        displacements={key:max(math.dist(f[key]['location'],settled[key]['location']) for f in frames) for key in settled}
        def group_drop(group):
            keys=[b['object_id'] for b in active_blocks if b['group']==group]
            if not keys:return None
            return max(settled[key]['location'][2]-min(f[key]['location'][2] for f in frames) for key in keys)
        def group_tilt(group):
            keys=[b['object_id'] for b in active_blocks if b['group']==group]
            if not keys:return None
            return max(tilt_deg(f[key]) for key in keys for f in frames)
        pillar=next((b['object_id'] for b in active_blocks if b['group']=='base'),None)
        pillar_slide=(max(f[pillar]['location'][0] for f in frames)-settled[pillar]['location'][0]) if pillar else None
        top_drop=group_drop('top')
        collapse=bool(impacted) and pillar_slide is not None and top_drop is not None and pillar_slide>.03 and top_drop>.10
        events['timed_edits']=timed_events
        quality=dict(valid=True,hit_building=bool(impacted),directly_impacted_blocks=sorted(impacted),events=events,
            timed_events=timed_events,present_objects=sorted(key for key,value in object_presence.items() if value),
            deleted_objects=sorted(key for key,value in object_presence.items() if not value),
            max_settle_drift_m=settle_drift,max_settle_speed_m_s=settle_speed,
            collapse_observed=collapse,max_top_drop_m=top_drop,max_top_tilt_deg=group_tilt('top'),base_tilt_deg=group_tilt('base'),
            pillar_slide_m=pillar_slide,remaining_block_count=len(active_blocks),
            displaced_blocks_over_3cm=sum(v>.03 for v in displacements.values()),max_block_displacement_m=max(displacements.values(),default=0.),
            note='Block motion metrics include only bodies present in the simulated scene; an absent top block has null drop/tilt metrics.')
        objects={'ball':dict(radius=c['ball_radius'],mass=c['ball_mass'],initial_location=c['ball_initial_location'])}
        objects.update({b['object_id']:dict(size=b['size'],mass=b['mass'],group=b['group'],initial_location=settled[b['object_id']]['location']) for b in active_blocks})
        return dict(schema_version=2,scene='ball_block_building',simulator='pybullet',scenario=s,objects=objects,object_presence=object_presence,
            frames=frames,quality=quality,timed_events=timed_events,
            fps=fps,sample_fps=fps,playback_fps=r['fps'],slow_motion=r['slow_motion'],frame_start=1,frame_end=len(frames),duration_sec=r['duration_sec'],
            physical_duration_sec=r['duration_sec'],playback_duration_sec=r['duration_sec']*r['slow_motion'],physics_dt=dt,substeps_per_frame=steps)
    finally:p.disconnect(client)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);parser.add_argument('--scenario-json',type=Path);parser.add_argument('--scenario-overrides-json',type=Path)
    parser.add_argument('--ball-mass',type=float);parser.add_argument('--ball-speed',type=float);parser.add_argument('--fps',type=int);parser.add_argument('--duration-sec',type=float);parser.add_argument('--slow-motion',type=int,choices=(1,2,4,8))
    args=parser.parse_args();s=json.loads(args.scenario_json.read_text(encoding='utf-8')) if args.scenario_json else defaults()
    if args.scenario_overrides_json:s=merge(s,json.loads(args.scenario_overrides_json.read_text(encoding='utf-8')))
    for name in ('ball_mass','ball_speed'):
        if getattr(args,name) is not None:s['physics'][name]=getattr(args,name)
    for name in ('fps','duration_sec','slow_motion'):
        if getattr(args,name) is not None:s['render'][name]=getattr(args,name)
    data=simulate(s);args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    args.out.with_name('simulation_metrics.json').write_text(json.dumps(data['quality'],indent=2),encoding='utf-8');print(json.dumps(data['quality']))

if __name__=='__main__':main()

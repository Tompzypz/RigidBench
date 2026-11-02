"""Rigid eraser extracts the bottom of a stack; SI units, no scripted motion."""
# PCVE_UNIFIED_ENTRY_BEGIN
from __future__ import annotations

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




import argparse, json, math
from pathlib import Path
import sys
import runtime_support
from scene_config import BASELINE_PHYSICS,load_scenario,validate
from scene_geometry import BOX_SIZE,ERASER_SIZE,COUNT,TABLE_Z,BOX_MASS,UPPER_TILT_LIMIT_DEG,box_poses,moving_objects
from validate_chalk_box_stack import CACHE_SCHEMA_VERSION,simulation_signature
import pybullet as p

PHYSICS_DT=1/2400
# What a schedule entry may write into a running simulation. A launch speed is
# absent on purpose: it is spent at frame 1, so there is nothing left to change.
TIMED_FIELDS={'box_friction','eraser_friction','eraser_mass'}

def load_schedule(physics,frame_count):
    """Read a scenario's timed-edit schedule into ``{frame: params}``."""
    entries=physics.get('timed_edits',[])
    if not isinstance(entries,list):raise ValueError('timed_edits must be a list of {frame, params} events')
    schedule={}
    for entry in entries:
        if not isinstance(entry,dict) or set(entry)!={'frame','params'}:raise ValueError('Each timed edit needs exactly a frame and a params object')
        frame=entry['frame']
        if isinstance(frame,bool) or not isinstance(frame,int) or not 2<=frame<=frame_count:raise ValueError(f'Timed edit frame {frame!r} is outside 2..{frame_count}')
        if frame in schedule:raise ValueError(f'Two timed edits target frame {frame}')
        params=entry['params']
        if not isinstance(params,dict) or not params:raise ValueError(f'Timed edit at frame {frame} carries no parameters')
        unknown=set(params)-TIMED_FIELDS
        if unknown:raise ValueError(f'A timed edit cannot change: {sorted(unknown)}')
        for name,value in params.items():
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
                raise ValueError(f'Timed {name} must be a finite non-negative number')
            if name=='eraser_mass' and value<=0:raise ValueError('Timed eraser_mass must be positive')
        schedule[frame]=dict(params)
    return schedule

def apply_timed_params(client,frame,params,bodies,physics,fps):
    """Write a scheduled parameter set into the live bodies and report both ends.

    The cartons were built with ``lateralFriction = sqrt(box_friction)``, so a
    mid-run change goes through the same mapping the start-up path uses; that is
    what keeps one number meaning one thing in this scene. Poses and velocities
    are read on both sides so the record shows a coefficient was redefined
    rather than the stack being nudged.
    """
    names=['eraser']+[f'box_{i}' for i in range(COUNT)]
    info={name:p.getDynamicsInfo(bodies[name],-1,physicsClientId=client) for name in names}
    before_params={name:physics[name] for name in params}
    before_state={name:dict(location=list(p.getBasePositionAndOrientation(bodies[name],physicsClientId=client)[0]),
                            linear_velocity=list(p.getBaseVelocity(bodies[name],physicsClientId=client)[0]),
                            mass=info[name][0],lateral_friction=info[name][1])
                  for name in names}
    physics.update(params)
    if 'box_friction' in params:
        for i in range(COUNT):
            p.changeDynamics(bodies[f'box_{i}'],-1,lateralFriction=math.sqrt(params['box_friction']),physicsClientId=client)
    if 'eraser_friction' in params:
        p.changeDynamics(bodies['eraser'],-1,lateralFriction=params['eraser_friction'],physicsClientId=client)
    if 'eraser_mass' in params:
        p.changeDynamics(bodies['eraser'],-1,mass=params['eraser_mass'],physicsClientId=client)
    after_info={name:p.getDynamicsInfo(bodies[name],-1,physicsClientId=client) for name in names}
    after_state={name:dict(location=list(p.getBasePositionAndOrientation(bodies[name],physicsClientId=client)[0]),
                           linear_velocity=list(p.getBaseVelocity(bodies[name],physicsClientId=client)[0]),
                           mass=after_info[name][0],lateral_friction=after_info[name][1])
                 for name in names}
    for name in names:
        if after_state[name]['location']!=before_state[name]['location'] or after_state[name]['linear_velocity']!=before_state[name]['linear_velocity']:
            raise RuntimeError('A parameter change moved the stack; that is a kick, not an edit')
    return {'frame':frame,'time_sec':(frame-1)/fps,'params':params,
            'before':{'params':before_params,'bodies':before_state},
            'after':{'params':{name:physics[name] for name in params},'bodies':after_state},
            'status':'applied','effective_from_frame':frame}

def _simulate_physics(physics=None, fps=30, duration_sec=3.0):
    cfg = BASELINE_PHYSICS | (physics or {})
    if fps <= 0 or duration_sec <= 0 or not math.isfinite(duration_sec):
        raise ValueError('fps and duration must be positive')
    for key,value in BASELINE_PHYSICS.items():
        if isinstance(value,(list,tuple,dict)):continue
        if not math.isfinite(cfg[key]):
            raise ValueError(f'{key} must be finite')
        # ``eraser_start_x`` is a signed position; everything else is a
        # magnitude and has to stay nonnegative.
        if key != 'eraser_start_x' and cfg[key] < 0:
            raise ValueError(f'{key} must be finite and nonnegative')
    if cfg['eraser_mass'] <= 0:
        raise ValueError('eraser_mass must be positive')
    # One frame is a whole number of physics steps, so an edit that lands on
    # frame n lands exactly between the steps that produced n-1 and n.
    steps_per_frame = round(1/(fps*PHYSICS_DT))
    if abs(steps_per_frame*fps*PHYSICS_DT-1) > 1e-9:
        raise ValueError(f'{fps} fps is not an integer number of steps at dt={PHYSICS_DT}')
    frame_count = round(duration_sec*fps)
    schedule = load_schedule(cfg, frame_count)
    cid = p.connect(p.DIRECT)
    try:
        dt = PHYSICS_DT
        p.setTimeStep(dt)
        p.setGravity(0, 0, -9.81)
        p.setPhysicsEngineParameter(numSolverIterations=100, contactBreakingThreshold=0.001)
        def body(size, pos, mass, friction, yaw=0.):
            shape = p.createCollisionShape(p.GEOM_BOX, halfExtents=[v/2 for v in size])
            uid = p.createMultiBody(mass, shape, basePosition=pos,
                                    baseOrientation=p.getQuaternionFromEuler([0, 0, yaw]))
            p.changeDynamics(uid, -1, lateralFriction=friction, restitution=0.02,
                             linearDamping=0, angularDamping=0, collisionMargin=0.0001)
            return uid
        body((8, 5, .1), (0,0,-.05), 0, .8)
        body((2.6, 1.0, .08), (0,0,TABLE_Z-.04), 0, .65)
        boxes = [body(BOX_SIZE, pose['location'], BOX_MASS, math.sqrt(cfg['box_friction']), pose['yaw'])
                 for pose in box_poses()]
        # ``eraser_start_x`` sets the run-up; ``moving_objects`` reports the
        # same value into the cache metadata, so the renderer and the truth
        # file never disagree about where the eraser began.
        eraser = body(ERASER_SIZE, (cfg['eraser_start_x'],0,TABLE_Z+ERASER_SIZE[2]/2), cfg['eraser_mass'], cfg['eraser_friction'])
        for _ in range(480): p.stepSimulation()
        p.resetBaseVelocity(eraser, (cfg['eraser_speed'],0,0))
        ids = dict(eraser=eraser, **{f'box_{i}': b for i,b in enumerate(boxes)})
        frames=[]; timed_events=[]; max_tilt=0.; max_spread=0.; first_contact=None
        max_upper_tilt=0.; final_upper_tilt=0.
        for frame in range(1, frame_count+1):
            # The edit lands at the top of its frame: every earlier frame has
            # already been stepped on the baseline physics, and this frame's
            # steps run on the edited value from the state reached so far.
            if frame in schedule:
                timed_events.append(apply_timed_params(cid, frame, schedule[frame], ids, cfg, fps))
            if frame > 1:
                for step in range(1, steps_per_frame+1):
                    p.stepSimulation()
                    t = ((frame-2)*steps_per_frame + step)*dt  # time of the step just taken
                    if first_contact is None and p.getContactPoints(eraser, boxes[0]): first_contact = t
                    # Track upper-stack coherence during the first fall, before table landing.
                    if first_contact is not None and t-first_contact < .10:
                        positions=[]
                        for b in boxes[1:]:
                            pos,q=p.getBasePositionAndOrientation(b); positions.append(pos)
                            up=p.getMatrixFromQuaternion(q)[8]
                            max_tilt=max(max_tilt, math.degrees(math.acos(max(-1,min(1,up)))))
                        max_spread=max(max_spread, max(v[0] for v in positions)-min(v[0] for v in positions))
            final_upper_tilt=max(math.degrees(math.acos(max(-1,min(1,p.getMatrixFromQuaternion(p.getBasePositionAndOrientation(b)[1])[8])))) for b in boxes[1:])
            max_upper_tilt=max(max_upper_tilt,final_upper_tilt)
            frames.append(dict(time=(frame-1)/fps, bodies={name: dict(position=list(p.getBasePositionAndOrientation(b)[0]), quaternion=list(p.getBasePositionAndOrientation(b)[1]),linear_velocity=list(p.getBaseVelocity(b)[0]),angular_velocity=list(p.getBaseVelocity(b)[1])) for name,b in ids.items()}))
        return dict(scene='chalk_box_stack', physics=cfg, fps=fps, duration_sec=duration_sec,
                    geometry=dict(box_size=BOX_SIZE, eraser_size=ERASER_SIZE, count=COUNT, table_z=TABLE_Z),
                    metrics=dict(max_upper_tilt_deg=max_upper_tilt, final_upper_tilt_deg=final_upper_tilt, first_contact_sec=first_contact, upper_tilt_first_100ms_deg=max_tilt, upper_spread_first_100ms_m=max_spread, timed_events=timed_events), frames=frames)
    finally: p.disconnect(cid)

def simulate(s):
    validate(s);r=s['render'];sample_fps=r['fps']
    data=_simulate_physics(s['physics'],sample_fps,r['duration_sec'])
    frames=[]
    for index,old in enumerate(data['frames'][:round(sample_fps*r['duration_sec'])],1):
        frame=dict(frame_index=index,time_sec=old['time'],playback_time_sec=(index-1)/r['fps'])
        for key,pose in old['bodies'].items():
            pos=pose['position'];q=pose['quaternion'];rot=p.getMatrixFromQuaternion(q)
            frame[key]=dict(present=True,location=pos,quaternion_xyzw=q,
                matrix_world=[[rot[3*i+j] for j in range(3)]+[pos[i]] for i in range(3)]+[[0,0,0,1]],
                linear_velocity=pose['linear_velocity'],angular_velocity=pose['angular_velocity'],
                speed=math.sqrt(sum(v*v for v in pose['linear_velocity'])))
        frames.append(frame)
    quality=dict(valid=True,hit_stack=data['metrics']['first_contact_sec'] is not None,**data['metrics'])
    upper=[f'box_{i}' for i in range(1,COUNT)]
    drops={key:frames[0][key]['location'][2]-frames[-1][key]['location'][2] for key in upper}
    # ``final_offset`` scores how far the survivors drifted apart. With a single
    # survivor (COUNT=2) there is nothing to drift apart, so it degenerates to
    # 0 and that term simply never rejects a take.
    first,last=upper[0],upper[-1]
    final_offset=math.dist(frames[-1][first]['location'][:2],frames[-1][last]['location'][:2])
    quality['upper_box_drop_m']=drops
    quality['final_upper_offset_m']=final_offset
    # A brief wobble is allowed, but every survivor must actually descend one
    # level and finish upright, aligned and supported. Tilt alone cannot
    # certify this. The tilt bound follows COUNT: with a single survivor there
    # is no inter-box alignment left to protect (see UPPER_TILT_LIMIT_DEG).
    quality['upper_stack_preserved']=(quality['hit_stack'] and quality['max_upper_tilt_deg']<UPPER_TILT_LIMIT_DEG
        and quality['final_upper_tilt_deg']<2 and final_offset<.02
        and all(abs(drop-BOX_SIZE[2])<.003 for drop in drops.values()))
    quality['collapse_observed']=quality['max_upper_tilt_deg']>60
    from motion_analysis import motion_summary
    motion=motion_summary(frames,moving_objects(s['physics']),r['fps'],r['duration_sec'])
    return dict(schema_version=CACHE_SCHEMA_VERSION,simulation_signature=simulation_signature(s),scene='chalk_box_stack',simulator='pybullet',scenario=s,
        physics=s['physics'],geometry=data['geometry'],objects=moving_objects(s['physics']),frames=frames,quality=quality,
        motion_summary=motion,fps=sample_fps,sample_fps=sample_fps,playback_fps=r['fps'],slow_motion=1,
        frame_start=1,frame_end=len(frames),duration_sec=r['duration_sec'],physical_duration_sec=r['duration_sec'],
        playback_duration_sec=r['duration_sec'],physics_dt=PHYSICS_DT,timed_edits=s['physics'].get('timed_edits',[]))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--scenario-json',type=Path);parser.add_argument('--scenario-overrides-json',type=Path)
    for key in BASELINE_PHYSICS:
        if isinstance(BASELINE_PHYSICS[key],(int,float)):parser.add_argument('--'+key.replace('_','-'),type=float)
    parser.add_argument('--fps',type=int);parser.add_argument('--duration-sec',type=float)
    args=parser.parse_args();data=simulate(load_scenario(args));args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    args.out.with_name('simulation_metrics.json').write_text(json.dumps(data['quality'],indent=2),encoding='utf-8')
    args.out.with_name('motion_summary.json').write_text(json.dumps(data['motion_summary'],indent=2),encoding='utf-8')
    print(json.dumps(data['quality']))
if __name__=='__main__':main()

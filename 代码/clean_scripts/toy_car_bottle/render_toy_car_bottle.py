"""Run with Blender --python, or the repository's .runtime/render Python."""
# Resolve this scene folder and the repository assets directory.
import sys as _pcve_local_sys
from pathlib import Path as _PcveLocalPath
_pcve_scene_dir = _PcveLocalPath(__file__).resolve().parent
_pcve_scripts_root = _pcve_scene_dir.parent
_pcve_local_sys.path.insert(0, str(_pcve_scripts_root))
_pcve_local_sys.path.insert(0, str(_pcve_scene_dir))
_PCVE_PROJECT_ROOT = next(p for p in _pcve_scene_dir.parents if (p / "assets").is_dir())
import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path
import bpy
from mathutils import Vector, Quaternion
from edit_vocab import prepare_config

HERE=Path(__file__).resolve().parent
ROOT = _PCVE_PROJECT_ROOT


def parse_args():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',choices=['preview','animation','frames','keyframes','build'],default='preview')
    parser.add_argument('--out-dir',type=Path,default=ROOT/'renders/toy_car_bottle')
    parser.add_argument('--models-dir',type=Path,help='Directory containing all three GLBs')
    parser.add_argument('--scenario-overrides-json',type=Path)
    parser.add_argument('--physics-python',type=Path)
    parser.add_argument('--resolution',nargs=2,type=int,default=[1280,720])
    parser.add_argument('--fps',type=int,default=24)
    parser.add_argument('--duration-sec',type=float,default=4)
    parser.add_argument('--samples',type=int,default=48)
    parser.add_argument('--frames',help='Comma separated frame numbers for --mode keyframes')
    parser.add_argument('--end-frame',type=int,
                        help='Stop --mode frames here; the rest of the shot is static and can '
                             'be duplicated from the last rendered frame, saving most of the cost')
    return parse_render_args(parser, sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:])


def find_model(name, args):
    dirs=[args.models_dir] if args.models_dir else [ROOT/'assets/models']
    for directory in dirs:
        if (directory/name).is_file():
            return directory/name
    raise FileNotFoundError(f'{name} not found in {dirs}. Supply --models-dir with the actual asset directory.')


def world_bounds(objects):
    points=[obj.matrix_world@Vector(v) for obj in objects for v in obj.bound_box]
    lo=Vector([min(p[i] for p in points) for i in range(3)])
    hi=Vector([max(p[i] for p in points) for i in range(3)])
    return lo,hi


def bake_parts(path):
    """Import a GLB and bake every mesh to world space as a standalone object."""
    previous=set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported=[o for o in bpy.data.objects if o not in previous]
    # Some GLBs carry turntable/NLA animations. Remove them before baking:
    # otherwise imported scale keys override the metric size during playback.
    for imported_obj in imported:
        imported_obj.animation_data_clear()
        if imported_obj.data is not None and hasattr(imported_obj.data,'animation_data_clear'):
            imported_obj.data.animation_data_clear()
    bpy.context.view_layer.update()
    # Bake evaluated geometry, including the Hot Wheels armature's rest pose.
    # Removing its rig before evaluating would collapse/skew skinned meshes.
    depsgraph=bpy.context.evaluated_depsgraph_get()
    parts=[]
    for source in imported:
        if source.type!='MESH':
            continue
        evaluated=source.evaluated_get(depsgraph)
        data=bpy.data.meshes.new_from_object(evaluated,preserve_all_data_layers=True,depsgraph=depsgraph)
        data.transform(source.matrix_world)
        part=bpy.data.objects.new(source.name+'_part',data)
        bpy.context.collection.objects.link(part)
        parts.append(part)
    for source in imported:
        if source.name in bpy.data.objects:
            bpy.data.objects.remove(source,do_unlink=True)
    return parts


def join_parts(parts,name):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in parts:
        obj.select_set(True)
    bpy.context.view_layer.objects.active=parts[0]
    bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    if len(parts)>1:
        bpy.ops.object.join()
    obj=bpy.context.view_layer.objects.active
    obj.name=name
    bpy.context.view_layer.update()
    return obj


def set_origin_to_centre(obj):
    """Move the origin to the object's bounding-box centre, leaving the mesh in place."""
    lo,hi=world_bounds([obj])
    bpy.context.scene.cursor.location=(lo+hi)/2
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active=obj
    bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
    bpy.context.view_layer.update()
    return lo,hi


def import_asset(path,name,target_axis=None,target_size=None):
    obj=join_parts(bake_parts(path),name)
    if target_axis is not None:
        # Only metric-scaled assets get re-centred. Re-centring a background like the
        # room moves its origin to the bbox centre, and the caller then sets location
        # to room_offset, which would silently shift the whole room by -centre.
        lo,hi=set_origin_to_centre(obj)
        obj.location=(0,0,0)
        factor=target_size/(hi-lo)[target_axis]
        obj.scale=(factor,)*3
        bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    bpy.context.view_layer.update()
    return obj


WHEEL_AXLE=(1,0,0)      # GLB width axis; the car's nose is local -Y, so this is the axle
WHEEL_SLACK=0.02        # tolerance used to recognise a wheel pair from its bounds alone


def import_car(path,name,target_axis,target_size):
    """Import the toy car, keep the wheel pairs as separate objects and return a rig.

    The rigid body in the simulation is a sliding box, so nothing here changes the
    trajectory: the wheels are spun afterwards purely so the car does not read as
    having its brakes locked on. Returns (rig, [(wheel_object, wheel_radius_metres)]).
    """
    parts=bake_parts(path)
    lo,hi=world_bounds(parts)
    size=hi-lo
    wheels,body=[],[]
    for part in parts:
        plo,phi=world_bounds([part])
        ps=phi-plo
        # A wheel pair is round in the two non-axle axes, nearly spans the car's width
        # and sits at the bottom of the model.
        circular=abs(ps[1]-ps[2])<=WHEEL_SLACK*max(ps[1],ps[2])
        if circular and ps[0]>=.8*size[0] and plo[2]<=lo[2]+.15*size[2]:
            wheels.append(part)
        else:
            body.append(part)
    if len(wheels)!=2:
        # Unknown asset layout: fall back to a single mesh with no wheel spin.
        for part in parts:
            data=part.data
            bpy.data.objects.remove(part,do_unlink=True)
            bpy.data.meshes.remove(data)
        return import_asset(path,name,target_axis,target_size),[]
    car=join_parts(body,name)
    radii=[]
    for wheel in wheels:
        wlo,whi=set_origin_to_centre(wheel)
        radii.append((whi-wlo)[2]/2)
    rig=bpy.data.objects.new(name+'_rig',None)
    rig.empty_display_size=size[target_axis]*.6
    bpy.context.collection.objects.link(rig)
    rig.location=(lo+hi)/2
    rig.rotation_mode='QUATERNION'
    bpy.context.view_layer.update()
    # Parent with keep-transform by hand: the rig may later carry location,
    # rotation and a uniform scale, all of which must not distort the wheels.
    inverse=rig.matrix_world.inverted()
    for obj in [car]+wheels:
        obj.parent=rig
        obj.matrix_parent_inverse=inverse
    factor=target_size/size[target_axis]
    rig.location=(0,0,0)
    rig.scale=(factor,)*3
    bpy.context.view_layer.update()
    return rig,[(wheel,radius*factor) for wheel,radius in zip(wheels,radii)]


def main():
    args=parse_args()
    config=json.loads((ROOT/'assets'/'scenarios'/'toy_car_bottle'/'scenario.json').read_text(encoding='utf-8'))
    prepare_config(config)
    if args.scenario_overrides_json:
        for group,values in json.loads(args.scenario_overrides_json.read_text(encoding='utf-8')).items():
            config[group].update(values)
    # Validate all assets before touching the scene or writing preview outputs.
    assets={key:find_model(name,args) for key,name in
            [('room','futuristic_room.glb'),('car',config['assets']['car']),('bottle',config['assets']['bottle'])]}
    out=args.out_dir.resolve()
    out.mkdir(parents=True,exist_ok=True)
    resolved=out/'resolved_scenario.json'
    resolved.write_text(json.dumps(config,indent=2),encoding='utf-8')
    python=args.physics_python or ROOT/'.runtime/sim/python.exe'
    if not Path(python).exists():
        python=shutil.which('python')
    trajectory=out/'physics_transforms.json'
    subprocess.run([str(python),str(HERE/'simulate_toy_car_bottle.py'),'--out',str(trajectory),
                    '--scenario-overrides-json',str(resolved),'--fps',str(args.fps),
                    '--duration-sec',str(args.duration_sec)],check=True)
    physics=json.loads(trajectory.read_text(encoding='utf-8'))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene=bpy.context.scene
    scene.render.engine='CYCLES'
    scene.cycles.samples=args.samples
    scene.cycles.use_denoising=True
    scene.cycles.device='CPU'
    scene.render.threads_mode='FIXED';scene.render.threads=4
    if args.device=='auto':
        
        configure_cycles_device(bpy,scene,args.device)
    scene.render.resolution_x,scene.render.resolution_y=args.resolution
    scene.render.resolution_percentage=100
    scene.render.fps=args.fps
    scene.frame_start=1
    scene.frame_end=physics['frame_count']
    layout=config['layout']
    room=import_asset(assets['room'],'futuristic_room')
    room.scale=(layout['room_scale'],)*3
    room.location=layout['room_offset']
    car,wheels=import_car(assets['car'],'toy_car',1,layout['car_length'])
    # GLB nose is local -Y; +90 degrees puts it along the simulation's +X.
    yaw=Quaternion((0,0,1),math.pi/2)
    bottle=import_asset(assets['bottle'],'plastic_bottle',2,layout['bottle_height'])
    bottle_2=None
    if config['physics']['bottle_presence'][1]:
        bottle_2=import_asset(assets['bottle'],'plastic_bottle_2',2,layout['bottle_height'])
    render_bodies=[('car',car),('bottle',bottle)]
    if bottle_2 is not None:
        render_bodies.append(('bottle_2',bottle_2))
    origin=Vector(layout['action_origin'])+Vector((0,0,layout['floor_z']))
    travelled=0.0
    previous_x=None
    for frame in physics['frames']:
        for name,obj in render_bodies:
            state=frame['objects'][name]
            obj.location=Vector(state['position'])+origin
            x,y,z,w=state['quaternion_xyzw']
            obj.rotation_mode='QUATERNION'
            obj.rotation_quaternion=Quaternion((w,x,y,z)) @ (yaw if name=='car' else Quaternion())
            obj.keyframe_insert('location',frame=frame['frame'])
            obj.keyframe_insert('rotation_quaternion',frame=frame['frame'])
        # Spin the wheels by the arc length the body has covered. The simulated body
        # slides as a box, so this is a visual roll, not an extra physical effect.
        car_x=frame['objects']['car']['position'][0]
        if previous_x is not None:
            travelled+=car_x-previous_x
        previous_x=car_x
        for wheel,radius in wheels:
            wheel.rotation_mode='QUATERNION'
            wheel.rotation_quaternion=Quaternion(WHEEL_AXLE,travelled/max(radius,1e-6))
            wheel.keyframe_insert('rotation_quaternion',frame=frame['frame'])
    for obj in [car,bottle]+([bottle_2] if bottle_2 is not None else [])+[wheel for wheel,_ in wheels]:
        for curve in obj.animation_data.action.fcurves:
            for point in curve.keyframe_points:
                point.interpolation='LINEAR'
    bpy.ops.object.camera_add(location=Vector(layout['camera_location'])+origin)
    camera=bpy.context.object
    camera.rotation_euler=(Vector(layout['camera_target'])+origin-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.lens=layout['camera_lens_mm']
    scene.camera=camera
    for loc,power,size in [((0,-1,2),180,2),((1,1,1.7),120,1.5)]:
        bpy.ops.object.light_add(type='AREA',location=Vector(loc)+origin)
        light=bpy.context.object
        light.data.energy=power
        light.data.shape='DISK'
        light.data.size=size
        light.rotation_euler=(origin-light.location).to_track_quat('-Z','Y').to_euler()
    scene.world=bpy.data.worlds.new('Room ambient')
    scene.world.use_nodes=True
    scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.12,.16,.22,1)
    scene.world.node_tree.nodes['Background'].inputs[1].default_value=.3
    scene.frame_set(1)
    # Saved .blend is ready for Render Animation even when this run only previews.
    scene.render.image_settings.file_format='FFMPEG'
    scene.render.ffmpeg.format='MPEG4'
    scene.render.ffmpeg.codec='H264'
    scene.render.filepath=str(out/'toy_car_bottle.mp4')
    scene.cycles.samples=max(96,args.samples)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'toy_car_bottle.blend'))
    scene.cycles.samples=args.samples
    gt=dict(physics)
    gt['coordinate_system']='simulation coordinates + world_origin; quaternions XYZW'
    gt['world_origin']=list(origin)
    gt['render_frames']=[]
    for frame in physics['frames']:
        world_objects={}
        for name,state in frame['objects'].items():
            if not state.get('present',True):
                continue
            x,y,z,w=state['quaternion_xyzw']
            rotation=Quaternion((w,x,y,z)) @ (yaw if name=='car' else Quaternion())
            world_objects[name]={'position':list(Vector(state['position'])+origin),
                                 'quaternion_xyzw':[rotation.x,rotation.y,rotation.z,rotation.w]}
        gt['render_frames'].append({'frame':frame['frame'],'objects':world_objects})
    gt['camera']={'matrix_world':[list(row) for row in camera.matrix_world],'lens_mm':camera.data.lens}
    (out/'ground_truth_transforms.json').write_text(json.dumps(gt,indent=2),encoding='utf-8')
    metadata=dict(config=config,assets={k:str(v) for k,v in assets.items()},fps=args.fps,
                  resolution=args.resolution,duration_sec=args.duration_sec,total_frames=scene.frame_end,
                  first_contact_frame=physics['first_contact_frame'],first_contact_frames=physics['first_contact_frames'],
                  collision_model='box car, one or two convex rigid bottle colliders; no plastic deformation',
                  bottle_presence=config['physics']['bottle_presence'])
    (out/'scenario_metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    if args.mode=='build':
        return
    if args.mode=='preview':
        scene.render.image_settings.file_format='PNG'
        for frame,name in ([(args.preview_frame,'preview.png')] if args.preview_frame is not None else [(1,'first_frame.png'),(scene.frame_end,'last_frame.png')]):
            scene.frame_set(frame)
            scene.render.filepath=str(out/name)
            bpy.ops.render.render(write_still=True)
    elif args.mode=='frames':
        scene.render.image_settings.file_format='PNG'
        scene.render.filepath=str(out/'frames/frame_')
        (out/'frames').mkdir(exist_ok=True)
        if args.end_frame:
            if not 1<=args.end_frame<=scene.frame_end:
                raise SystemExit(f'--end-frame must be within 1..{scene.frame_end}')
            print(f'rendering 1..{args.end_frame} of {scene.frame_end} frames; '
                  f'scene.frame_end set for the animation range only')
            scene.frame_end=args.end_frame
        bpy.ops.render.render(animation=True)
    elif args.mode=='keyframes':
        scene.render.image_settings.file_format='PNG'
        wanted=[int(part) for part in (args.frames or '1').split(',') if part.strip()]
        for frame in wanted:
            if not 1<=frame<=scene.frame_end:
                print(f'skip frame {frame}: outside 1..{scene.frame_end}')
                continue
            scene.frame_set(frame)
            scene.render.filepath=str(out/f'key_f{frame:03d}.png')
            bpy.ops.render.render(write_still=True)
    else:
        scene.render.image_settings.file_format='FFMPEG'
        scene.render.ffmpeg.format='MPEG4'
        scene.render.ffmpeg.codec='H264'
        scene.render.filepath=str(out/'toy_car_bottle.mp4')
        bpy.ops.render.render(animation=True)


"""Shared command-line and output contracts for PCVE scene entry points.

Both ``blender -b --python render.py -- ...`` and Python with bpy are supported.
This module has no Blender dependency until a renderer finishes.
"""

import argparse
import hashlib
import json
import math
import os
import random
import shutil
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'assets').is_dir())
_render_args = None


def python_for(role: str) -> Path:
    override = os.environ.get("PCVE_PHYSICS_PYTHON" if role == "physics" else "PCVE_RENDER_PYTHON")
    if override:
        return Path(override).expanduser()
    names = ("sim/python.exe", "sim/bin/python") if role == "physics" else (
        "render/Scripts/python.exe", "render/bin/python")
    for base in (ROOT / ".runtime", ROOT.parent / "PCVE-ElasticBench/.runtime"):
        for name in names:
            if (base / name).is_file():
                return base / name
    if role == "physics":
        # The original Linux setup activates a PyBullet conda environment and
        # invokes Blender separately. Blender's sys.executable is not Python.
        candidates = [ROOT.parent / "miniconda/envs/physics/bin/python"]
        if os.environ.get("CONDA_PREFIX"):
            prefix = Path(os.environ["CONDA_PREFIX"])
            candidates += [prefix / "python.exe", prefix / "bin/python"]
        for name in ("python3", "python"):
            if shutil.which(name):
                candidates.append(Path(shutil.which(name)))
        for candidate in candidates:
            if candidate.is_file() and "blender" not in candidate.name.lower():
                return candidate
    return Path(sys.executable)


def _add(parser, flag, **kwargs):
    if flag not in parser._option_string_actions:
        parser.add_argument(flag, **kwargs)


def implementation_hashes(directory):
    files = list(Path(directory).glob("*.py"))
    files += [ROOT / "clean_scripts" / name for name in ("pcve_scene_pipeline.py", "pcve_edit_dsl.py")]
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in files if path.is_file()}


def case_outputs(folder):
    """Semantic output keys used by the original suite manifests."""
    names = dict(video="video.mp4", ground_truth="ground_truth_transforms.json",
                 scenario_metadata="scenario_metadata.json", scenario_overrides="scenario_overrides.json",
                 physics="physics_transforms.json", scenario_input="scenario_input.json", preview="preview.png")
    return {key: str((Path(folder) / name).resolve()) for key, name in names.items()
            if (Path(folder) / name).is_file()}


def add_build_arguments(parser):
    _add(parser, "--blender", type=Path, help="Blender executable; otherwise use render Python with bpy.")
    _add(parser, "--physics-python", type=Path, default=python_for("physics"))
    _add(parser, "--render-python", type=Path, default=python_for("render"))
    _add(parser, "--engine", choices=("cycles", "eevee"), default="cycles")
    _add(parser, "--device", choices=("auto", "cpu"), default="auto")
    _add(parser, "--preview-frame", type=int)
    _add(parser, "--fps", type=int)
    _add(parser, "--duration-sec", type=float)
    return parser


def render_prefix(args, script: Path) -> list[str]:
    blender = getattr(args, "blender", None) or os.environ.get("BLENDER_BIN")
    render_python = Path(getattr(args, "render_python", python_for("render")))
    if not blender and render_python == Path(sys.executable):
        candidates = [ROOT / "tools/blender-3.6.23-linux-x64/blender"]
        if shutil.which("blender"):
            candidates.append(Path(shutil.which("blender")))
        blender = next((path for path in candidates if path.is_file()), None)
    if blender:
        # Blender otherwise returns success even when the Python script raises.
        return [str(Path(blender).expanduser()), "-b", "--python-exit-code", "1",
                "--python", str(script), "--"]
    return [str(render_python), str(script)]


def append_render_options(command, args):
    for name in ("engine", "device", "preview_frame"):
        flag = "--" + name.replace("_", "-")
        value = getattr(args, name, None)
        if value is not None and flag not in command:
            command += [flag, str(value)]
    return command


def parse_render_args(parser, argv=None):
    global _render_args
    _add(parser, "--seed", type=int, default=0)
    _add(parser, "--device", choices=("auto", "cpu"), default="auto")
    _add(parser, "--preview-frame", type=int)
    _add(parser, "--fps", type=int)
    _add(parser, "--duration-sec", type=float)
    _add(parser, "--physics-python", type=Path, default=python_for("physics"))
    # Renderers without an engine switch currently implement Cycles only.
    _add(parser, "--engine", choices=("cycles",), default="cycles")
    if argv is None:
        argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    _render_args = parser.parse_args(argv)
    # In the original CLI duration-sec is the real-time clip length. A scene's
    # optional demo slow-motion preset must not silently multiply that request.
    if "--duration-sec" in argv and "--slow-motion" not in argv and hasattr(_render_args, "slow_motion"):
        _render_args.slow_motion = 1
    random.seed(_render_args.seed)
    return _render_args


def apply_physics_overrides(args, baseline):
    """Read the original {physics: ...} override format for scalar CLI scenes.

    Bare schedule arrays remain accepted by the older timed-edit escape hatch.
    Explicit scalar command-line values take precedence over the JSON defaults.
    """
    path = getattr(args, "scenario_overrides_json", None)
    if path is None:
        return None
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return Path(path)
    physics = payload.get("physics", payload)
    unknown = set(physics) - {*baseline, "timed_edits"}
    if unknown:
        raise ValueError(f"Unknown physics overrides: {sorted(unknown)}")
    for name, value in physics.items():
        if name != "timed_edits" and getattr(args, name, None) is None:
            setattr(args, name, value)
    if physics.get("timed_edits"):
        target = Path(args.out_dir) / "timed_edits.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(physics["timed_edits"], indent=2), encoding="utf-8")
        return target
    return None


def _matrix(position, q):
    x, y, z, w = q
    return [[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w), position[0]],
            [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w), position[1]],
            [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y), position[2]],
            [0, 0, 0, 1]]


def _optional_metrics(value):
    if isinstance(value, dict):
        return {key: _optional_metrics(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_optional_metrics(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def finalize_render_outputs(out: Path, scene_name: str, args, scene=None):
    """Keep scene-specific files and also publish the original PCVE filenames."""
    out = Path(out).resolve()
    gt_path = out / "ground_truth_transforms.json"
    if gt_path.is_file():
        gt = json.loads(gt_path.read_text(encoding="utf-8"))
        gt.setdefault("scene", scene_name)
        gt.setdefault("schema_version", 1)
        camera = gt.setdefault("camera", {})
        camera.setdefault("resolution", list(args.resolution))
        camera.setdefault("sensor_width_mm", 36.0)
        if scene is not None and scene.camera is not None:
            cam = scene.camera
            camera.update(matrix_world=[list(row) for row in cam.matrix_world],
                          sensor_width_mm=float(cam.data.sensor_width),
                          sensor_fit=cam.data.sensor_fit)
            if cam.data.type == "ORTHO":
                camera.update(projection="orthographic", ortho_scale=float(cam.data.ortho_scale))
            else:
                camera.update(projection="perspective", lens_mm=float(cam.data.lens))
        frames = gt.get("frames", [])
        # toy_car_bottle retains its raw simulation and render_frames as well.
        rendered = gt.get("render_frames", [])
        for index, frame in enumerate(frames):
            frame.setdefault("frame_index", frame.get("frame", index + 1))
            frame.setdefault("time_sec", frame.get("time", index / gt.get("fps", 24)))
            if camera.get("matrix_world") is not None:
                frame.setdefault("camera_matrix_world", camera["matrix_world"])
            if index < len(rendered):
                for name, state in rendered[index].get("objects", {}).items():
                    raw = frame.get("objects", {}).get(name, {})
                    frame[name] = dict(raw, present=True, location=state["position"],
                                       quaternion_xyzw=state["quaternion_xyzw"],
                                       matrix_world=_matrix(state["position"], state["quaternion_xyzw"]))
        gt.setdefault("frame_start", 1)
        gt.setdefault("frame_end", len(frames))
        if scene_name == "toy_car_bottle":
            layout = gt["config"]["layout"]
            gt["objects"] = {
                "car": {"object_name": "toy_car", "dimensions": [layout["car_length"], layout["car_width"], layout["car_height"]]},
                "bottle": {"object_name": "plastic_bottle", "radius": layout["bottle_radius"], "height": layout["bottle_height"]},
            }
        # A short diagnostic clip may not contain an impact. Its unavailable
        # post-contact quality measurements are null; poses must stay finite.
        for container in (gt, gt.get("physics", {})):
            if "quality" in container:
                container["quality"] = _optional_metrics(container["quality"])
        for frame in frames:
            matrices = [item["matrix_world"] for item in frame.values()
                        if isinstance(item, dict) and "matrix_world" in item
                        and not (item.get("present") is False and item["matrix_world"] is None)]
            matrices += [item for key, item in frame.items() if key.endswith("_matrix_world")]
            for matrix in matrices:
                if matrix is None:
                    raise ValueError("A present object must have a ground-truth transform")
                if not all(math.isfinite(value) for row in matrix for value in row):
                    raise ValueError("Non-finite ground-truth transform")
        gt_path.write_text(json.dumps(gt, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    mode = getattr(args, "mode", "preview")
    if mode == "animation":
        stem = "basketball_door" if scene_name == "home_basketball_door" else scene_name
        source = out / (stem + ".mp4")
        target = out / "video.mp4"
        if source.is_file() and not (scene_name == "uneven_ground_ball" and getattr(args, "label", False)):
            shutil.copy2(source, target)
        if not target.is_file():
            raise FileNotFoundError(f"Animation did not produce {target}")
    refresh_alias = scene_name in ("home_basketball_door", "pot_lid_drop") or (
        scene_name == "toy_car_bottle" and getattr(args, "preview_frame", None) is None)
    if mode == "preview" and (refresh_alias or not (out / "preview.png").is_file()):
        number = getattr(args, "preview_frame", None) or 1
        candidates = [out / f"preview_frame_{number:04d}.png", out / "first_frame.png"]
        candidates += sorted(out.glob("preview_frame_*.png"))
        source = next((p for p in candidates if p.is_file()), None)
        if source is None:
            raise FileNotFoundError(f"Preview did not produce an image in {out}")
        shutil.copy2(source, out / "preview.png")


def run_renderer(main, scene_name):
    global _render_args
    _render_args = None
    main()
    if _render_args is not None:
        import bpy
        finalize_render_outputs(_render_args.out_dir, scene_name, _render_args, bpy.context.scene)


"""Small Blender 3.6/4.x API differences used by the scene renderers."""

SOCKET_NAMES = {
    "Coat Weight": "Clearcoat", "Coat Roughness": "Clearcoat Roughness",
    "Specular IOR Level": "Specular", "Transmission Weight": "Transmission",
    "Emission Color": "Emission", "Sheen Weight": "Sheen",
    "Sheen Roughness": "Roughness", "Subsurface Weight": "Subsurface",
}


def shader_socket(node, name):
    socket = node.inputs.get(name)
    if socket is None:
        socket = node.inputs.get(SOCKET_NAMES.get(name, name))
    if socket is None:
        raise KeyError(f"{node.name}: missing shader input {name}")
    return socket


def set_shader_input(node, name, value):
    socket = shader_socket(node, name)
    if socket.type == "VALUE" and isinstance(value, (tuple, list)):
        value = sum(value[:3]) / 3
    socket.default_value = value


def eevee_engine():
    import bpy
    return "BLENDER_EEVEE_NEXT" if bpy.app.version >= (4, 2, 0) else "BLENDER_EEVEE"


def set_eevee_property(settings, name, value):
    parts = name.split(".")
    for part in parts[:-1]:
        if not hasattr(settings, part):
            return
        settings = getattr(settings, part)
    if hasattr(settings, parts[-1]):
        setattr(settings, parts[-1], value)


def set_color_property(settings, name, value):
    try:
        setattr(settings, name, value)
    except (TypeError, ValueError):
        candidates = ("Filmic", "Standard") if name == "view_transform" else ("Medium High Contrast", "None")
        for candidate in candidates:
            try:
                setattr(settings, name, candidate)
                return
            except (TypeError, ValueError):
                continue
        raise


def configure_cycles_device(bpy, scene, requested):
    scene.cycles.device = "CPU"
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 4
    if requested == "cpu":
        return "CPU"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for backend in ("OPTIX", "CUDA", "HIP", "METAL"):
        try:
            prefs.compute_device_type = backend
            prefs.get_devices()
            found = [device for device in prefs.devices if device.type == backend]
            if found:
                for device in prefs.devices:
                    device.use = device.type == backend
                scene.cycles.device = "GPU"
                return "GPU"
        except (TypeError, RuntimeError, ValueError):
            continue
    return "CPU"


if __name__=='__main__':
    run_renderer(main, 'toy_car_bottle')
    gt_path=_render_args.out_dir.resolve()/'ground_truth_transforms.json'
    gt=json.loads(gt_path.read_text(encoding='utf-8'))
    if any('bottle_2' not in frame.get('objects',{}) for frame in gt.get('frames',[])):
        raise ValueError('Ground truth must record bottle_2 presence in every frame')
    gt['objects']['bottle_2']={
        'object_name':'plastic_bottle_2',
        'radius':gt['config']['layout']['bottle_radius'],
        'height':gt['config']['layout']['bottle_height'],
        'present_in_video':bool(gt['config']['physics']['bottle_presence'][1]),
    }
    gt_path.write_text(json.dumps(gt,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')

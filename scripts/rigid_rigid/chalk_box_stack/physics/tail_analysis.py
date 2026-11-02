"""Report how much of a rendered clip is actually in motion.

Projects every cached world position through the perspective or orthographic camera that the
renderer used, so the answer is in pixels of the delivered frame rather than in
metres the viewer never sees. A frame counts as "moving" when any object still
inside the frame moves at least MIN_PIXELS_PER_FRAME; everything after the last
such frame is the static tail.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
from pathlib import Path
import argparse, json, math

MIN_PIXELS_PER_FRAME = 1.0


def camera_basis(matrix):
    """Right, up and origin of the camera in world space.

    Blender stores a matrix as rows, but an object's local axes in world space are
    its COLUMNS: column 0 is local +X (screen right), column 1 is local +Y (screen
    up). Taking the rows instead rotates the projection and everything lands
    thousands of pixels off frame.
    """
    right = [matrix[r][0] for r in range(3)]
    up = [matrix[r][1] for r in range(3)]
    back = [matrix[r][2] for r in range(3)]
    return right, up, back, [matrix[0][3], matrix[1][3], matrix[2][3]]


def project(points, camera, resolution):
    """World points -> pixel (u, v), top-left origin."""
    right, up, back, origin = camera_basis(camera['matrix_world'])
    width, height = resolution
    orthographic=camera.get('projection')=='orthographic' or 'ortho_scale' in camera
    scale=camera['ortho_scale'] if orthographic else None
    out = []
    for point in points:
        delta = [point[i] - origin[i] for i in range(3)]
        x=sum(delta[i]*right[i] for i in range(3))
        y=sum(delta[i]*up[i] for i in range(3))
        if orthographic:
            u=x/(scale*.5);v=y/(scale*height/width*.5)
        else:
            depth=-sum(delta[i]*back[i] for i in range(3))
            if depth<=0:
                out.append((float('nan'),float('nan')));continue
            focal_px=width*camera['lens_mm']/camera['sensor_width_mm']
            out.append((width*.5+focal_px*x/depth,height*.5-focal_px*y/depth));continue
        out.append(((u * .5 + .5) * width, (1 - (v * .5 + .5)) * height))
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--gt', type=Path, required=True)
    p.add_argument('--min-speed', type=float, default=MIN_PIXELS_PER_FRAME)
    args = p.parse_args()
    data = json.loads(args.gt.read_text(encoding='utf-8'))
    camera = data['camera']
    resolution = camera['resolution']
    names = list(data['objects'])
    frames = data['frames']
    tracks = {name: [] for name in names}
    for frame in frames:
        points = [frame[name]['location'] for name in names]
        for name, pixel in zip(names, project(points, camera, resolution)):
            tracks[name].append(pixel)
    width, height = resolution
    print(f'{"frame":>5} {"t_play":>7} ' + ' '.join(f'{n:>13}' for n in names) + '   fastest')
    last_moving = 0
    for index in range(1, len(frames)):
        speeds = []
        for name in names:
            (u0, v0), (u1, v1) = tracks[name][index - 1], tracks[name][index]
            inside = -60 <= u1 <= width + 60 and -60 <= v1 <= height + 60
            speeds.append(math.hypot(u1 - u0, v1 - v0) if inside else 0.0)
        fastest = max(speeds)
        if fastest >= args.min_speed:
            last_moving = index + 1
        print(f'{frames[index]["frame_index"]:5d} {frames[index]["playback_time_sec"]:7.3f} ' +
              ' '.join(f'{s:13.2f}' for s in speeds) + f'   {fastest:6.2f}')
    total = len(frames)
    print()
    print(f'last moving frame: {last_moving} / {total}')
    print(f'static tail: {total - last_moving} frames ({(total - last_moving) / data["fps"]:.2f} s)')


if __name__ == '__main__':
    main()

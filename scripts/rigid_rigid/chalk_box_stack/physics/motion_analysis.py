"""Measure physical settling, including bodies that have left the camera view."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math


def motion_summary(frames, names, fps, duration_sec, linear_threshold=.01,
                   angular_threshold=.05, minimum_rest_sec=.5):
    """Rest means both speeds remain below their limits for the entire tail.

    Require at least half a second of rest to avoid declaring a short pause or
    the final sample a settled state. Times are sampled at the simulation FPS;
    a null rest time means the recording does not establish settling.
    """
    def summarize(active):
        last=next((i for i in range(len(active)-1,-1,-1) if active[i]),-1)
        start=last+1
        rest=frames[start]['time_sec'] if start<len(frames) else None
        confirmed=(rest is not None and
                   frames[-1]['time_sec']-rest+1e-9>=minimum_rest_sec)
        first=next((i for i,value in enumerate(active) if value),None)
        return dict(settled=confirmed,rest_start_sec=rest if confirmed else None,
                    last_moving_time_sec=frames[last]['time_sec'] if last>=0 else None,
                    moving_sample_duration_sec=sum(active)/fps,
                    motion_span_sec=(rest-frames[first]['time_sec']) if confirmed and first is not None else None,
                    static_tail_sec=duration_sec-rest if confirmed else None)

    active_by_body={name:[math.hypot(*frame[name]['linear_velocity'])>=linear_threshold
                         or math.hypot(*frame[name]['angular_velocity'])>=angular_threshold
                         for frame in frames] for name in names}
    combined=[any(track[i] for track in active_by_body.values()) for i in range(len(frames))]
    return dict(**summarize(combined),linear_threshold_m_s=linear_threshold,
                angular_threshold_rad_s=angular_threshold,minimum_rest_sec=minimum_rest_sec,
                time_resolution_sec=1/fps,includes_offscreen_bodies=True,
                objects={name:summarize(active) for name,active in active_by_body.items()})

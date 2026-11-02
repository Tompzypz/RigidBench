"""Constrained rigid-body dynamics with event-resolved, frictionless sphere impact.

Two generalized angles enforce planar, inextensible rods exactly. RK4 integrates
gravity and F_drag=-c*v at 4800 Hz. A bracketed contact time and a normal impulse
using the two pivot inertias resolve impacts, including oblique contact and the
external pivot reaction. No target motion, prescribed transfer or post-impact
animation is used. Rod and connector masses are idealized as negligible.
"""

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

import argparse
import json
import math
import sys
from pathlib import Path

from twin_pendulum_collision.scene_config import load_scenario, add_scenario_arguments, validate
from twin_pendulum_collision.scene_geometry import (
    BOB_RADIUS, LENGTH, GRAVITY, PHYSICS_HZ, RECEIVER_MASS, RESTITUTION,
    KEYS, PIVOTS, center, tangent, fixed_constants)
from twin_pendulum_collision.cache_contract import simulation_signature


def simulate(s):
    validate(s)
    c, r = s['physics'], s['render']
    masses = (c['driver_mass'], RECEIVER_MASS)
    inertias = tuple(m * (LENGTH ** 2 + .4 * BOB_RADIUS ** 2) for m in masses)
    drag = c['drag_coefficient']
    fps = r['fps'] * r['slow_motion']
    dt = 1 / PHYSICS_HZ
    state = [-math.radians(c['initial_angle_deg']), 0., 0., 0.]
    receiver_active = bool(c['receiver_active'][0])
    timed_edits = {event['frame']: event['params'] for event in c.get('timed_edits', [])}
    collisions = []
    drag_loss = 0.
    collision_loss = 0.
    removed_energy = 0.
    removal_frame = None

    def rhs(y):
        return [y[2], y[3] if receiver_active else 0., *[
            (-masses[i] * GRAVITY * LENGTH * math.sin(y[i]) - drag * LENGTH ** 2 * y[i + 2]) / inertias[i]
            if i == 0 or receiver_active else 0. for i in range(2)]]

    def rk4(y, h):
        k1 = rhs(y)
        k2 = rhs([v + h * k / 2 for v, k in zip(y, k1)])
        k3 = rhs([v + h * k / 2 for v, k in zip(y, k2)])
        k4 = rhs([v + h * k for v, k in zip(y, k3)])
        return [v + h * (a + 2 * b + 2 * d + e) / 6 for v, a, b, d, e in zip(y, k1, k2, k3, k4)]

    def gap(y):
        return math.dist(center(0, y[0]), center(1, y[1])) - 2 * BOB_RADIUS

    def body_energy(i, y):
        return masses[i] * GRAVITY * LENGTH * (1 - math.cos(y[i])) + .5 * inertias[i] * y[i + 2] ** 2

    def energy(y):
        return body_energy(0, y) + (body_energy(1, y) if receiver_active else 0.)

    def free_step(y, h):
        nonlocal drag_loss
        z = rk4(y, h)
        drag_loss += h * drag * LENGTH ** 2 * sum(y[i + 2] ** 2 + z[i + 2] ** 2
                                                 for i in range(2) if i == 0 or receiver_active) / 2
        return z

    def advance(y, h, time, depth=0):
        nonlocal collision_loss
        z = rk4(y, h)
        if not receiver_active or gap(z) >= 0:
            return free_step(y, h)
        if depth > 8:
            raise RuntimeError('Contact failed to separate')
        low, high = 0., h
        for _ in range(36):
            mid = (low + high) / 2
            if gap(rk4(y, mid)) > 0:
                low = mid
            else:
                high = mid
        hit = free_step(y, low)
        a, b = center(0, hit[0]), center(1, hit[1])
        normal = [(b[i] - a[i]) / math.dist(a, b) for i in range(3)]
        jac = [-sum(v * n for v, n in zip(tangent(hit[0]), normal)),
               sum(v * n for v, n in zip(tangent(hit[1]), normal))]
        approach = sum(jac[i] * hit[i + 2] for i in range(2))
        if approach >= 0:
            raise RuntimeError('Overlapping spheres without an approaching impact')
        impulse = -(1 + RESTITUTION) * approach / sum(jac[i] ** 2 / inertias[i] for i in range(2))
        before = energy(hit)
        pre = hit[2:].copy()
        for i in range(2):
            hit[i + 2] += jac[i] * impulse / inertias[i]
        collision_loss += before - energy(hit)
        departure = sum(jac[i] * hit[i + 2] for i in range(2))
        collisions.append(dict(time_sec=time + low, impulse_ns=impulse,
                               approach_normal_speed_m_s=-approach, departure_normal_speed_m_s=departure,
                               restitution_measured=departure / -approach, angular_velocity_before=pre,
                               angular_velocity_after=hit[2:].copy(), energy_loss_j=before - energy(hit)))
        return advance(hit, h - low, time + low, depth + 1)

    def snapshot(index, y):
        if index == 1 and not receiver_active:
            return dict(present=False)
        angle, omega = y[index], y[index + 2]
        pos = center(index, angle)
        # R_y(-theta): the local upward connector always points to the pivot.
        co, si = math.cos(angle), math.sin(angle)
        return dict(present=True, location=list(pos), quaternion_xyzw=[0., -math.sin(angle / 2), 0., math.cos(angle / 2)],
                    matrix_world=[[co, 0., -si, pos[0]], [0., 1., 0., pos[1]], [si, 0., co, pos[2]], [0., 0., 0., 1.]],
                    linear_velocity=[v * omega for v in tangent(angle)], angular_velocity=[0., -omega, 0.],
                    speed=abs(LENGTH * omega), pendulum_angle_rad=angle,
                    height_m=LENGTH * (1 - math.cos(angle)))

    initial_energy = energy(state)
    max_energy = initial_energy
    max_overlap = 0.
    max_balance_error = 0.
    peak_receiver = 0.
    frames = []
    steps = PHYSICS_HZ // fps
    count = round(fps * r['duration_sec'])
    for frame_index in range(count):
        if frame_index:
            for sub in range(steps):
                time = ((frame_index - 1) * steps + sub) * dt
                state = advance(state, dt, time)
                current = energy(state)
                max_energy = max(max_energy, current)
                if receiver_active:
                    max_overlap = max(max_overlap, -gap(state))
                    peak_receiver = max(peak_receiver, abs(state[1]))
                max_balance_error = max(max_balance_error, abs(current + drag_loss + collision_loss + removed_energy - initial_energy))
        # Like the older scenes, apply at the top of this frame, after stepping
        # from the preceding sample. Earlier frames retain source dynamics.
        if frame_index + 1 in timed_edits and receiver_active:
            removed_energy += body_energy(1, state)
            receiver_active = False
            state[3] = 0.
            removal_frame = frame_index + 1
            max_balance_error = max(max_balance_error, abs(energy(state) + drag_loss + collision_loss + removed_energy - initial_energy))
        frames.append(dict(frame_index=frame_index + 1, time_sec=frame_index / fps,
                           playback_time_sec=frame_index / r['fps'],
                           **{key: snapshot(i, state) for i, key in enumerate(KEYS)}))
    finite = all(math.isfinite(v) for f in frames for key in KEYS if f[key]['present']
                 for v in f[key]['location'] + f[key]['linear_velocity'])
    quality = dict(valid=finite and max_overlap < 1e-8 and max_balance_error < max(1e-8, initial_energy * 1e-5),
                   events=dict(first_ball_impact_sec=collisions[0]['time_sec'] if collisions else None,
                               receiver_removed_frame=removal_frame), collisions=collisions,
                   contact_count=len(collisions), transmission_observed=peak_receiver > math.radians(1),
                   receiver_peak_angle_deg=math.degrees(peak_receiver), initial_energy_j=initial_energy,
                   max_energy_j=max_energy, final_energy_j=energy(state), drag_dissipated_energy_j=drag_loss,
                   collision_dissipated_energy_j=collision_loss, removed_body_energy_j=removed_energy,
                   max_energy_balance_error_j=max_balance_error,
                   max_overlap_m=max_overlap, max_rod_error_m=0.)
    if not quality['valid']:
        raise RuntimeError(f'Invalid simulation: {quality}')
    return dict(schema_version=2, scene=s['scene'], simulator='constrained RK4 + event-resolved rigid-sphere impulses',
                constraint_model='Two planar single pendulums; massless rigid rods; finite spherical bob inertia; F_drag=-c*v',
                scenario=s, fixed_constants=fixed_constants(), simulation_signature=simulation_signature(s),
                objects={key: dict(radius=BOB_RADIUS, mass=masses[i], pivot=PIVOTS[i], pendulum_length=LENGTH,
                                   present_from_start=(i == 0 or bool(c['receiver_active'][0])),
                                   pivot_inertia_kg_m2=inertias[i]) for i, key in enumerate(KEYS)},
                frames=frames, quality=quality, fps=fps, sample_fps=fps, playback_fps=r['fps'],
                slow_motion=r['slow_motion'], frame_start=1, frame_end=count,
                physical_duration_sec=r['duration_sec'], playback_duration_sec=r['duration_sec'] * r['slow_motion'],
                last_sample_time_sec=(count - 1) / fps, physics_dt=dt, substeps_per_frame=steps)


def main():
    parser = add_scenario_arguments(argparse.ArgumentParser(description=__doc__))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    data = simulate(load_scenario(args))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    args.out.with_name('simulation_metrics.json').write_text(json.dumps(data['quality'], indent=2), encoding='utf-8')
    print(json.dumps(data['quality']))


if __name__ == '__main__':
    main()

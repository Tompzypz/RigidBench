"""The same engine/device interface used by the other scene renderers."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)

import sys
from pathlib import Path
sys.path.insert(0, str(_PCVE_ROOT / 'scripts'))
from pcve_blender_compat import (shader_socket, set_shader_input, eevee_engine, set_eevee_property, set_color_property)
def configure_renderer(bpy, scene, args):
    scene.render.engine = 'CYCLES' if args.engine == 'cycles' else eevee_engine()
    scene.render.threads_mode = 'FIXED'; scene.render.threads = 4
    if args.engine == 'cycles':
        scene.cycles.samples = args.samples; scene.cycles.use_denoising = True
        scene.cycles.use_adaptive_sampling = True; scene.cycles.adaptive_threshold = .005
        scene.cycles.adaptive_min_samples = min(32, args.samples)
        scene.cycles.max_bounces = 8; scene.cycles.diffuse_bounces = 4; scene.cycles.glossy_bounces = 4
        scene.render.use_persistent_data = True; scene.cycles.device = 'CPU'
        if args.device == 'auto':
            try:
                prefs = bpy.context.preferences.addons['cycles'].preferences
                prefs.compute_device_type = 'CUDA'; prefs.get_devices()
                available = [d for d in prefs.devices if d.type == 'CUDA']
                for d in prefs.devices:
                    d.use = d.type == 'CUDA'
                if available:
                    scene.cycles.device = 'GPU'
            except Exception:
                scene.cycles.device = 'CPU'
        return scene.cycles.device
    return 'GPU'


def configure_color(scene):
    set_color_property(scene.view_settings, 'view_transform', 'AgX')
    set_color_property(scene.view_settings, 'look', 'AgX - Medium High Contrast')
    scene.view_settings.exposure = -.10

"""Appearance render setup only; no simulation settings or shared project edits."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pcve_blender_compat import (shader_socket, set_shader_input, eevee_engine, set_eevee_property, set_color_property)
def configure_renderer(bpy,scene,args):
    scene.render.engine=eevee_engine() if args.engine=='eevee' else 'CYCLES'
    if args.engine=='eevee':
        set_eevee_property(scene.eevee, 'taa_render_samples', args.samples);set_eevee_property(scene.eevee, 'use_raytracing', False)
        set_eevee_property(scene.eevee, 'ray_tracing_options.resolution_scale', '2');set_eevee_property(scene.eevee, 'ray_tracing_options.screen_trace_quality', 0.6)
        set_eevee_property(scene.eevee, 'use_gtao', True);set_eevee_property(scene.eevee, 'gtao_distance', 0.2);set_eevee_property(scene.eevee, 'gtao_quality', 1.0)
        set_eevee_property(scene.eevee, 'shadow_ray_count', 1);set_eevee_property(scene.eevee, 'shadow_step_count', 8)
    else:
        scene.cycles.samples=args.samples;scene.cycles.use_denoising=True;scene.cycles.max_bounces=8;scene.cycles.diffuse_bounces=4;scene.cycles.glossy_bounces=4
        scene.cycles.adaptive_threshold=.008;scene.cycles.seed=19;scene.render.use_persistent_data=True
        # Default 1.5 px pixel filter softens fine background detail; 1.0 keeps the
        # scanned bookshelf textures crisp without aliasing the suspension threads.
        scene.cycles.filter_width=1.0
        scene.cycles.device='CPU'
        if args.device=='auto':
            prefs=bpy.context.preferences.addons['cycles'].preferences
            try:
                prefs.compute_device_type='CUDA';prefs.get_devices();available=[dev for dev in prefs.devices if dev.type=='CUDA']
                for dev in prefs.devices:dev.use=(dev.type=='CUDA')
                if available:
                    scene.cycles.device='GPU';scene.cycles.denoiser='OPTIX' if any(dev.type=='OPTIX' for dev in prefs.devices) else 'OPENIMAGEDENOISE'
                    print('[render] CUDA: '+', '.join(dev.name for dev in available),flush=True)
            except Exception as exc:
                scene.cycles.device='CPU';scene.cycles.denoiser='OPENIMAGEDENOISE'
                print('[render] CPU fallback: '+str(exc),flush=True)
        return scene.cycles.device
    return 'GPU'


def configure_color(scene):
    set_color_property(scene.view_settings, 'view_transform', 'AgX');set_color_property(scene.view_settings, 'look', 'AgX - Medium High Contrast');scene.view_settings.exposure=-.22


def prepare_eevee(bpy,scene,moving):
    if scene.render.engine!=eevee_engine() or bpy.app.version<(4,2,0):return
    for light in bpy.data.lights:light.use_shadow_jitter=False
    scene.use_nodes=True;nodes=scene.node_tree.nodes;links=scene.node_tree.links;nodes.clear()
    layers=nodes.new('CompositorNodeRLayers');denoise=nodes.new('CompositorNodeDenoise');denoise.use_hdr=True
    composite=nodes.new('CompositorNodeComposite');links.new(layers.outputs['Image'],denoise.inputs['Image']);links.new(denoise.outputs['Image'],composite.inputs['Image'])
    probe_data=bpy.data.lightprobes.new('Static room irradiance','VOLUME');probe_data.resolution_x=6;probe_data.resolution_y=4;probe_data.resolution_z=4;probe_data.bake_samples=32;probe_data.surfel_density=10
    probe=bpy.data.objects.new('Static room irradiance',probe_data);scene.collection.objects.link(probe);probe.location=[.2,.5,1.3];probe.scale=[2.5,2.2,1.6]
    dynamic=list(moving)
    for obj in list(dynamic):dynamic.extend(obj.children_recursive)
    dynamic=list(dict.fromkeys(dynamic));previous=[obj.hide_render for obj in dynamic]
    try:
        for obj in dynamic:obj.hide_render=True
        bpy.context.view_layer.objects.active=probe;probe.select_set(True)
        print('[render] Baking static room indirect light',flush=True);bpy.ops.object.lightprobe_cache_bake(subset='ALL')
    finally:
        for obj,hidden in zip(dynamic,previous):obj.hide_render=hidden

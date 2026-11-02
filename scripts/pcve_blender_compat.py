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

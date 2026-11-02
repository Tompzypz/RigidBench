"""Inspect the actual Blender mesh: empty air cavity and mass-consistent PET wall."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
def audit_empty_bottle(bpy,objects):
    import bmesh
    from mathutils import Vector
    from scene_geometry import COM_HEIGHT,EMPTY_BOTTLE_PROPERTIES
    obj=objects['bottle_left'];bpy.context.view_layer.update()
    hit,location,normal,index=obj.ray_cast(Vector((0,0,.015-COM_HEIGHT)),Vector((0,0,1)))
    height=float(location.z+COM_HEIGHT) if hit else None
    if not hit or not .205<=height<=.231:raise RuntimeError('Unexpected surface in air cavity: possible internal fill')
    pet_indices={i for i,m in enumerate(obj.data.materials) if m and m.name.startswith('Clear empty PET')}
    if len(pet_indices)!=1:raise RuntimeError('Expected one clear empty PET material')
    bm=bmesh.new();bm.from_mesh(obj.data)
    bmesh.ops.delete(bm,geom=[f for f in bm.faces if f.material_index not in pet_indices],context='FACES')
    boundary=sum(not e.is_manifold for e in bm.edges if e.link_faces)
    volume=abs(bm.calc_volume(signed=True));bm.free()
    mass=volume*EMPTY_BOTTLE_PROPERTIES['pet_density_kg_m3']
    if boundary:raise RuntimeError('PET wall is not a closed material shell')
    if abs(mass-EMPTY_BOTTLE_PROPERTIES['body_mass_kg'])>.000024:raise RuntimeError('Wall thickness disagrees with specified PET mass')
    if not all(not o.get('has_liquid',True) for k,o in objects.items() if k.startswith('bottle_')):raise RuntimeError('Bottle liquid flag')
    return dict(valid=True,contents='air only',has_liquid=False,interior_axis_first_surface_height_m=height,
        pet_wall_boundary_edges=boundary,pet_material_volume_m3=volume,pet_material_mass_kg=mass,
        cap_mass_estimate_kg=EMPTY_BOTTLE_PROPERTIES['cap_mass_kg'],
        reference_empty_mass_kg=EMPTY_BOTTLE_PROPERTIES['total_mass_kg'],
        mass_basis=EMPTY_BOTTLE_PROPERTIES['mass_basis'])

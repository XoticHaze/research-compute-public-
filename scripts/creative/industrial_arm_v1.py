"""Public original fixed scene recipe: industrial arm, animated GLB, studio preview.

Runs inside Blender 5.2+ only. All inputs are bounded by the fixed worker;
this script never imports arbitrary Python, downloads assets or reads secrets.
"""
import json
import math
import os
from pathlib import Path

import bpy
from mathutils import Vector

out = Path(os.environ["CC_BLENDER_PROBE_OUTPUT"])
params = json.loads(os.environ["CC_BLENDER_PARAMS_JSON"])
assert set(params) == {"camera_azimuth_deg", "preview_frame", "preview_samples"}

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.frame_start = 1
scene.frame_end = 120
scene.render.engine = "CYCLES"
scene.cycles.samples = params["preview_samples"]
scene.render.resolution_x = 600
scene.render.resolution_y = 600
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.threads_mode = "FIXED"
scene.render.threads = 2
scene.world = bpy.data.worlds.new("studio")
scene.world.color = (.18, .18, .18)


def mat(name, rgba, metallic):
    m = bpy.data.materials.new(name)
    m.diffuse_color = rgba
    m.use_nodes = True
    bs = m.node_tree.nodes.get("Principled BSDF")
    bs.inputs["Base Color"].default_value = rgba
    bs.inputs["Metallic"].default_value = metallic
    bs.inputs["Roughness"].default_value = .33
    return m


orange = mat("industrial orange", (.92, .22, .05, 1), .4)
steel = mat("brushed steel", (.28, .42, .49, 1), .75)
dark = mat("carbon", (.065, .08, .09, 1), .1)
floor = mat("stage matte", (.16, .2, .22, 1), .05)


def origin(name, parent=None, position=(0, 0, 0)):
    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    obj.parent = parent
    obj.location = position
    return obj


def cylinder(name, a, b, r, material, parent=None):
    a, b = Vector(a), Vector(b)
    vector = b - a
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=r, depth=vector.length)
    obj = bpy.context.object
    obj.name = name
    obj.parent = parent
    obj.location = (a + b) * .5
    obj.rotation_euler = Vector((0, 0, 1)).rotation_difference(vector).to_euler()
    obj.data.materials.append(material)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    return obj


def box(name, where, size, material, parent=None):
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.object
    obj.name = name
    obj.parent = parent
    obj.location = where
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    return obj


cylinder("base", (0, 0, 0), (0, 0, .26), .52, dark)
turn = origin("turntable", position=(0, 0, .26))
cylinder("shoulder bearing", (0, 0, 0), (0, 0, .22), .33, orange, turn)
shoulder = origin("shoulder", turn, (0, 0, .22))
cylinder("shoulder pivot", (-.2, 0, 0), (.2, 0, 0), .24, dark, shoulder)
cylinder("boom", (0, 0, .1), (0, 0, 1.36), .16, orange, shoulder)
cylinder("hydraulic case", (.13, 0, .2), (.13, 0, .95), .052, steel, shoulder)
elbow = origin("elbow", shoulder, (0, 0, 1.35))
cylinder("elbow pivot", (-.21, 0, 0), (.21, 0, 0), .23, dark, elbow)
cylinder("forearm", (0, 0, .1), (0, 0, 1.04), .13, steel, elbow)
cylinder("forearm sleeve", (.12, 0, .13), (.12, 0, .8), .035, orange, elbow)
wrist = origin("wrist", elbow, (0, 0, 1.04))
cylinder("tool flange", (0, 0, 0), (0, 0, .22), .17, orange, wrist)
box("jaw rail", (0, 0, .23), (.58, .14, .14), dark, wrist)
jaw_a = origin("left grip", wrist, (-.23, 0, .3))
jaw_b = origin("right grip", wrist, (.23, 0, .3))
box("jaw left", (0, 0, .14), (.075, .16, .34), steel, jaw_a)
box("jaw right", (0, 0, .14), (.075, .16, .34), steel, jaw_b)
box("stage", (0, 0, -.12), (8, 8, .2), floor)


def animation(obj, axis, data_path, poses):
    for frame, value in poses:
        values = list(getattr(obj, data_path))
        values[axis] = math.radians(value) if data_path == "rotation_euler" else value
        setattr(obj, data_path, values)
        obj.keyframe_insert(data_path=data_path, frame=frame)


animation(turn, 2, "rotation_euler", [(1, -35), (45, 24), (90, -15), (120, -35)])
animation(shoulder, 1, "rotation_euler", [(1, 15), (45, -30), (90, 6), (120, 15)])
animation(elbow, 1, "rotation_euler", [(1, -40), (45, 60), (90, 10), (120, -40)])
animation(wrist, 1, "rotation_euler", [(1, 0), (45, -45), (90, 15), (120, 0)])
animation(jaw_a, 0, "location", [(1, -.22), (45, -.09), (90, -.22), (120, -.22)])
animation(jaw_b, 0, "location", [(1, .22), (45, .09), (90, .22), (120, .22)])

theta = math.radians(params["camera_azimuth_deg"])
cx, cy = 7 * math.sin(theta), -7 * math.cos(theta)
bpy.ops.object.camera_add(location=(cx, cy, 3.0))
camera = bpy.context.object
camera.rotation_euler = (Vector((0, 0, 1.3)) - camera.location).to_track_quat("-Z", "Y").to_euler()
camera.data.type = "ORTHO"
camera.data.ortho_scale = 4.6
scene.camera = camera
for name, xyz, energy in [
    ("key", (2, -4, 6), 1300),
    ("fill", (-4, -2, 3), 700),
    ("rim", (1, 4, 5), 1400),
]:
    bpy.ops.object.light_add(type="AREA", location=xyz)
    light = bpy.context.object
    light.name = name
    light.data.energy = energy
    light.data.shape = "DISK"
    light.data.size = 4
    light.rotation_euler = (Vector((0, 0, 1)) - light.location).to_track_quat("-Z", "Y").to_euler()

scene.frame_set(params["preview_frame"])
bpy.ops.wm.save_as_mainfile(filepath=str(out / "arm.blend"))
bpy.ops.export_scene.gltf(filepath=str(out / "arm.glb"), export_format="GLB", export_animations=True)
scene.render.filepath = str(out / "preview.png")
bpy.ops.render.render(write_still=True)
print("PUBLIC_FIXED_BLENDER_SCENE_DONE")

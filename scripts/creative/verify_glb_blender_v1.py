"""Second-process Blender reimport of the exact GLB produced by fixed scene recipe.

A successful export message is insufficient; the GLB must load into a new
factory-default Blender context with actual animated actions and mesh objects.
Only the approved owning Blender worker sets the path from its work root.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import bpy

input_file = Path(os.environ["CC_BLENDER_VERIFY_GLB"]).resolve()
output_file = Path(os.environ["CC_BLENDER_VERIFY_RESULT"]).resolve()
if input_file.name != "arm.glb" or output_file.name != "glb_import_verification.json":
    raise RuntimeError("fixed_glb_filename_required")
if input_file.parent != output_file.parent or not input_file.is_file():
    raise RuntimeError("fixed_glb_workdir_invalid")
if input_file.stat().st_size > 500_000_000:
    raise RuntimeError("fixed_glb_oversize")

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(input_file))
meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
animated = [obj for obj in bpy.data.objects if obj.animation_data is not None]
actions = list(bpy.data.actions)
if len(meshes) < 10 or len(actions) == 0 or len(animated) < 2:
    raise RuntimeError("glb_import_missing_required_motion_or_geometry")
result = {
    "schema": "commandcenter.blender_glb_import_verification.v1",
    "status": "PASS",
    "mesh_count": len(meshes),
    "action_count": len(actions),
    "animated_node_count": len(animated),
    "blender_version": bpy.app.version_string,
}
output_file.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
print("BLENDER_GLTF_REIMPORT_MOTION_VERIFIED")

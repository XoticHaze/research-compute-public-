"""Fixed Blender output validation: independently inspect binary signatures and glTF animation.

This verifier does not use Blender or trust metadata supplied by the job.
It is not a visual-quality substitute for human review, but it prevents a
static or corrupt GLB from being called an animated result.
"""
from __future__ import annotations
import json
import struct
from hashlib import sha256
from pathlib import Path


def inspect_glb(raw: bytes) -> dict:
    if len(raw) < 20 or raw[:4] != b"glTF":
        raise ValueError("glb_magic_invalid")
    version, length = struct.unpack_from("<II", raw, 4)
    if version != 2 or length != len(raw):
        raise ValueError("glb_header_invalid")
    json_length = struct.unpack_from("<I", raw, 12)[0]
    if raw[16:20] != b"JSON" or json_length == 0 or json_length > len(raw) - 20:
        raise ValueError("glb_json_chunk_missing")
    try:
        node = json.loads(raw[20:20 + json_length].decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise ValueError("glb_json_invalid") from exc
    if not isinstance(node, dict) or not str((node.get("asset") or {}).get("version", "")).startswith("2"):
        raise ValueError("gltf_asset_version_invalid")
    mesh = node.get("meshes")
    anim = node.get("animations")
    if not isinstance(mesh, list) or not mesh:
        raise ValueError("gltf_mesh_missing")
    if not isinstance(anim, list) or not anim:
        raise ValueError("gltf_animation_missing")
    channels = sum(len(item.get("channels", [])) for item in anim if isinstance(item, dict))
    if channels < 4:
        raise ValueError("gltf_animated_channels_insufficient")
    return {"mesh_count": len(mesh), "animation_count": len(anim), "animated_channels": channels}


def inspect_png(raw: bytes) -> dict:
    if len(raw) < 33 or raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[12:16] != b"IHDR":
        raise ValueError("png_signature_invalid")
    width, height = struct.unpack_from(">II", raw, 16)
    if width != 600 or height != 600:
        raise ValueError("png_dimensions_unexpected")
    return {"width": width, "height": height}


def verify_output_files(root: Path) -> dict:
    root = Path(root)
    expected = ("arm.blend", "arm.glb", "preview.png")
    actual = {}
    for name in expected:
        path = root / name
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 500_000_000:
            raise ValueError("expected_output_missing_or_oversize")
        blob = path.read_bytes()
        actual[name] = {"bytes": len(blob), "sha256": sha256(blob).hexdigest()}
        if name == "arm.blend" and not blob.startswith(b"BLENDER"):
            raise ValueError("native_blend_signature_invalid")
        if name == "arm.glb":
            glb_stats = inspect_glb(blob)
        if name == "preview.png":
            image_stats = inspect_png(blob)
    return {"files": actual, "gltf": glb_stats, "preview": image_stats}

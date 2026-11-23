"""True binary-shape verifier tests, independent of Blender executable."""
import json
import struct
import tempfile
import unittest
from pathlib import Path

from scripts.creative.blender_artifact_verify_v1 import inspect_glb, inspect_png, verify_output_files


def synthetic_glb(channels=5, meshes=1):
    doc = {
        "asset": {"version": "2.0"},
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]} for _ in range(meshes)],
        "animations": [{"name": "turntable", "channels": [
            {"sampler": 0, "target": {"node": i, "path": "rotation"}} for i in range(channels)
        ], "samplers": [{"input": 0, "output": 1}]}],
    }
    data = json.dumps(doc, separators=(",", ":")).encode()
    data += b" " * ((4 - len(data) % 4) % 4)
    return b"glTF" + struct.pack("<II", 2, 20 + len(data)) + struct.pack("<I", len(data)) + b"JSON" + data


def synthetic_png(width=600, height=600):
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", width, height) + bytes([8, 6, 0, 0, 0]) + b"\0\0\0\0"


class BlenderBinaryTests(unittest.TestCase):
    def test_animated_glb_and_preview_shape(self):
        self.assertEqual(inspect_glb(synthetic_glb())["animated_channels"], 5)
        self.assertEqual(inspect_png(synthetic_png())["width"], 600)

    def test_static_glb_not_accepted_as_animation(self):
        with self.assertRaisesRegex(ValueError, "animated_channels"):
            inspect_glb(synthetic_glb(channels=0))
        with self.assertRaisesRegex(ValueError, "glb_header_invalid"):
            inspect_glb(synthetic_glb() + b"junk")

    def test_preview_dimensions_rejected(self):
        with self.assertRaisesRegex(ValueError, "png_dimensions_unexpected"):
            inspect_png(synthetic_png(300, 300))

    def test_artifact_integrity_and_native_blend_signature(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "arm.blend").write_bytes(b"BLENDER" + b"test")
            (root / "arm.glb").write_bytes(synthetic_glb())
            (root / "preview.png").write_bytes(synthetic_png())
            result = verify_output_files(root)
            self.assertEqual(set(result["files"]), {"arm.blend", "arm.glb", "preview.png"})
            (root / "arm.blend").write_bytes(b"bad")
            with self.assertRaisesRegex(ValueError, "native_blend_signature_invalid"):
                verify_output_files(root)


if __name__ == "__main__":
    unittest.main()

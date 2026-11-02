"""Offline bounded checks for integrity-only private web overlay composition.

Run in agent-local/authorized source checkout, never private GitHub Actions compute.
"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.private_web_asset_composer_v1 import compose


class PrivateWebOverlayCompositionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.base = self.root / "selected"
        self.base.mkdir()
        (self.base / "index.html").write_text("<!doctype html><title>existing console</title>")
        (self.base / "assets").mkdir()
        (self.base / "assets" / "mm.js").write_text("console.log('existing app')")
        self.overlay = self.root / "overlay"
        self.private = self.overlay / "assets" / "sampleapp"
        self.private.mkdir(parents=True)
        (self.private / "index.html").write_text("<!doctype html><title>Private example app</title>")
        (self.private / "candidate_action_board.js").write_text("console.log('safe asset')")
        self.manifest = self.root / "private-manifest.json"
        self.receipt = self.root / "receipts" / "compose.json"
        self.output = self.root / "composed"
        self.write_manifest()

    def write_manifest(self, **overrides):
        assets = {}
        for file in self.private.iterdir():
            assets[f"/assets/sampleapp/{file.name}"] = hashlib.sha256(file.read_bytes()).hexdigest()
        node = {
            "schema": "commandcenter.private_web_static_overlay.v1",
            "release_state": "STAGED_NOT_DEPLOYED",
            "access_served_verified": False,
            "app_slug": "sampleapp",
            "source_sha_claim": "1" * 40,
            "assets": assets,
        }
        node.update(overrides)
        self.manifest.write_text(json.dumps(node))

    def go(self):
        return compose(selected_dist=self.base, overlay=self.overlay,
                       manifest_file=self.manifest, output_dist=self.output,
                       receipt_file=self.receipt)

    def test_composes_and_preserves_existing_assets(self):
        base_before = {p.relative_to(self.base): p.read_bytes()
                       for p in self.base.rglob("*") if p.is_file()}
        result = self.go()
        self.assertEqual(result["state"], "COMPOSED_NOT_DEPLOYED")
        self.assertFalse(result["oidc_grant_verified"])
        self.assertFalse(result["access_served_verified"])
        self.assertEqual(result["private_overlay_files_added"], 2)
        self.assertEqual(json.loads(self.receipt.read_text()), result)
        for name, body in base_before.items():
            self.assertEqual((self.output / name).read_bytes(), body)

    def test_tampered_overlay_rejected_without_writing(self):
        (self.private / "index.html").write_text("TAMPER")
        with self.assertRaisesRegex(ValueError, "asset_hash_or_size_mismatch"):
            self.go()
        self.assertFalse(self.output.exists())

    def test_unmanifested_assets_rejected(self):
        (self.private / "secret.txt").write_text("unspecified")
        with self.assertRaisesRegex(ValueError, "unmanifested_private_asset_rejected"):
            self.go()

    def test_dangerous_extension_rejected(self):
        (self.private / "notes.env").write_text("not a web asset")
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "asset_type_not_admitted"):
            self.go()

    def test_slug_conflict_refused(self):
        (self.base / "assets" / "sampleapp").mkdir()
        (self.base / "assets" / "sampleapp" / "index.html").write_text("existing")
        with self.assertRaisesRegex(ValueError, "existing_app_slug_collision"):
            self.go()

    def test_symlink_source_refused(self):
        (self.private / "candidate_action_board.js").unlink()
        (self.private / "candidate_action_board.js").symlink_to(
            self.base / "assets" / "mm.js")
        self.write_manifest(assets={
            "/assets/sampleapp/index.html": hashlib.sha256(
                (self.private / "index.html").read_bytes()).hexdigest(),
            "/assets/sampleapp/candidate_action_board.js": hashlib.sha256(
                (self.base / "assets" / "mm.js").read_bytes()).hexdigest(),
        })
        with self.assertRaisesRegex(ValueError, "special_file_or_symlink_forbidden"):
            self.go()

    def test_empty_selected_build_refused(self):
        (self.base / "index.html").unlink()
        with self.assertRaisesRegex(ValueError, "selected_host_dist_missing_index"):
            self.go()

    def test_cannot_recompose_over_existing_destination(self):
        self.go()
        with self.assertRaisesRegex(ValueError, "output_must_be_new"):
            self.go()


if __name__ == "__main__":
    unittest.main()

"""Integrity-only composition of an approved private web overlay into an existing static build.

This module does NOT fetch source, verify OIDC/release authorization, deploy to
Cloudflare, or grant any right to publish private assets. The release owner must
independently admit both source revisions and encrypted transport before using
the composed distribution. No private GitHub Actions compute is needed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path, PurePosixPath

HEX64 = re.compile(r"[0-9a-f]{64}\Z")
SLUG = re.compile(r"[a-z][a-z0-9-]{0,39}\Z")
SCHEMA = "commandcenter.private_web_static_overlay.v1"
MAX_ASSETS = 32
MAX_ASSET_BYTES = 512 * 1024


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _regular_files(root: Path) -> dict[str, Path]:
    if not root.is_dir() or root.is_symlink():
        raise ValueError("directory_missing_or_symlink")
    result = {}
    for entry in root.rglob("*"):
        if entry.is_symlink() or (not entry.is_dir() and not entry.is_file()):
            raise ValueError("special_file_or_symlink_forbidden")
        if entry.is_file():
            key = entry.relative_to(root).as_posix()
            if key.endswith(".map"):
                raise ValueError("source_map_forbidden")
            result[key] = entry
    return result


def _overlay_files(overlay: Path, manifest: dict) -> tuple[str, dict[str, Path]]:
    if manifest.get("schema") != SCHEMA or manifest.get("release_state") != "STAGED_NOT_DEPLOYED":
        raise ValueError("overlay_manifest_state_invalid")
    if manifest.get("access_served_verified") is not False:
        raise ValueError("staging_receipt_must_not_claim_live_acceptance")
    slug = manifest.get("app_slug")
    if not isinstance(slug, str) or not SLUG.fullmatch(slug):
        raise ValueError("app_slug_invalid")
    reported = manifest.get("assets")
    if not isinstance(reported, dict) or not (1 <= len(reported) <= MAX_ASSETS):
        raise ValueError("overlay_inventory_invalid")
    expected_prefix = "assets/" + slug + "/"
    available = _regular_files(overlay)
    result = {}
    for url, digest in reported.items():
        if not isinstance(url, str) or not url.startswith("/" + expected_prefix):
            raise ValueError("overlay_route_out_of_scope")
        rel = url.lstrip("/")
        path = PurePosixPath(rel)
        if path.is_absolute() or ".." in path.parts or len(path.parts) > 6:
            raise ValueError("overlay_path_traversal")
        if not isinstance(digest, str) or not HEX64.fullmatch(digest):
            raise ValueError("asset_digest_invalid")
        if rel not in available:
            raise ValueError("manifest_asset_missing")
        source = available[rel]
        if source.stat().st_size > MAX_ASSET_BYTES or _file_hash(source) != digest:
            raise ValueError("asset_hash_or_size_mismatch")
        result[rel] = source
    if set(available) != set(result):
        raise ValueError("unmanifested_private_asset_rejected")
    if not all(PurePosixPath(name).suffix.lower() in {".html", ".js", ".css", ".ico", ".png", ".svg", ".webp", ".woff2"} for name in result):
        raise ValueError("asset_type_not_admitted")
    if expected_prefix + "index.html" not in result:
        raise ValueError("app_entrypoint_missing")
    return slug, result


def compose(*, selected_dist: Path, overlay: Path, manifest_file: Path,
            output_dist: Path, receipt_file: Path) -> dict:
    """Compose verified BYTES only, never certify source grants or deployment."""
    if manifest_file.is_symlink() or not manifest_file.is_file():
        raise ValueError("manifest_path_invalid")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    slug, input_files = _overlay_files(overlay, manifest)
    existing = _regular_files(selected_dist)
    if "index.html" not in existing:
        raise ValueError("selected_host_dist_missing_index")
    if any(key == "assets/" + slug or key.startswith("assets/" + slug + "/")
           for key in existing):
        raise ValueError("existing_app_slug_collision")
    if output_dist.exists() or output_dist.is_symlink() or receipt_file.exists():
        raise ValueError("output_must_be_new")
    selected_root = selected_dist.resolve()
    if selected_root in (output_dist.resolve(), *output_dist.resolve().parents):
        raise ValueError("output_inside_input_forbidden")
    overlay_root = overlay.resolve()
    if overlay_root in (output_dist.resolve(), *output_dist.resolve().parents):
        raise ValueError("output_inside_overlay_forbidden")
    receipt_path = receipt_file.resolve()
    if any(root == receipt_path or root in receipt_path.parents
           for root in (output_dist.resolve(), selected_root, overlay_root)):
        raise ValueError("private_receipt_must_stay_outside_web_assets")
    original_hashes = {name: _file_hash(p) for name, p in existing.items()}
    output_dist.parent.mkdir(parents=True, exist_ok=True)
    temp_parent = Path(tempfile.mkdtemp(prefix=".private-web-compose-", dir=output_dist.parent))
    staged = temp_parent / "dist"
    try:
        shutil.copytree(selected_dist, staged)
        for rel, src in input_files.items():
            dst = staged / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
        composed = _regular_files(staged)
        if set(composed) != set(existing) | set(input_files):
            raise ValueError("composed_inventory_mismatch")
        if any(_file_hash(composed[name]) != digest for name, digest in original_hashes.items()):
            raise ValueError("incumbent_asset_mutated")
        if any(_file_hash(composed[name]) != manifest["assets"]["/" + name]
               for name in input_files):
            raise ValueError("overlay_mutated")
        result = {
            "schema": "commandcenter.private_web_asset_composition.v1",
            "state": "COMPOSED_NOT_DEPLOYED",
            "app_slug": slug,
            "incumbent_files_preserved": len(existing),
            "private_overlay_files_added": len(input_files),
            "incumbent_digest_sha256": hashlib.sha256(
                json.dumps(original_hashes, sort_keys=True).encode("utf-8")).hexdigest(),
            "overlay_manifest_sha256": _file_hash(manifest_file),
            "source_sha_claim": manifest.get("source_sha_claim"),
            "oidc_grant_verified": False,
            "access_served_verified": False,
            "private_source_published_to_public_git": False,
        }
        output_dist.rename if False else None
        staged.rename(output_dist)
        receipt_file.parent.mkdir(parents=True, exist_ok=True)
        receipt_file.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                                encoding="utf-8")
        return result
    finally:
        shutil.rmtree(temp_parent, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selected-dist", type=Path, required=True)
    ap.add_argument("--private-overlay", type=Path, required=True)
    ap.add_argument("--overlay-manifest", type=Path, required=True)
    ap.add_argument("--output-dist", type=Path, required=True)
    ap.add_argument("--receipt", type=Path, required=True)
    args = ap.parse_args()
    result = compose(selected_dist=args.selected_dist, overlay=args.private_overlay,
                     manifest_file=args.overlay_manifest, output_dist=args.output_dist,
                     receipt_file=args.receipt)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

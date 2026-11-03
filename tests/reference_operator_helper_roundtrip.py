from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.reference_release_intent_v1 import ExpectedIntent, verify_intent


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        subprocess.run(
            [
                "node",
                str(ROOT / "scripts/operator/reference_release_keygen.mjs"),
                str(out),
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        broker_key_id = (out / "broker-key-id.txt").read_text(encoding="utf-8").strip()
        authority_public = (out / "authority-public.b64").read_text(encoding="utf-8").strip()

        bootstrap_path = out / "bootstrap-intent.json"
        subprocess.run(
            [
                "node",
                str(ROOT / "scripts/operator/reference_release_prepare_intent.mjs"),
                str(out / "authority-private.pkcs8.b64"),
                broker_key_id,
                str(bootstrap_path),
                "28800",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        bootstrap = json.loads(bootstrap_path.read_text(encoding="utf-8"))
        if set(bootstrap) != {"schema", "intent"}:
            raise RuntimeError("bootstrap_fields_rejected")
        if bootstrap["schema"] != "reference-live-intent-v1":
            raise RuntimeError("bootstrap_schema_rejected")

        payload = json.loads(
            __import__("base64").b64decode(
                bootstrap["intent"]["payload_b64"].encode("ascii"), validate=True
            ).decode("utf-8")
        )
        expected = ExpectedIntent(
            grant_id=payload["grant_id"],
            caller_policy_sha256=payload["caller_policy_sha256"],
            harness_sha=payload["harness_sha"],
            broker_key_id=payload["broker_key_id"],
        )
        verified = verify_intent(
            bootstrap["intent"],
            authority_public_b64=authority_public,
            expected=expected,
            now=int(payload["not_before"]) + 60,
            max_intent_seconds=259200,
        )
        if verified != payload:
            raise RuntimeError("operator_intent_roundtrip_mismatch")

        if not (out / "broker-private.jwk").exists():
            raise RuntimeError("broker_private_missing")
        if not (out / "authority-private.pkcs8.b64").exists():
            raise RuntimeError("authority_private_missing")
        # The first seal's keys must never be replaced on a mistaken rerun.
        broker_before = (out / "broker-private.jwk").read_bytes()
        authority_before = (out / "authority-private.pkcs8.b64").read_bytes()
        retry = subprocess.run(
            ["node", str(ROOT / "scripts/operator/reference_release_keygen.mjs"), str(out)],
            cwd=ROOT, capture_output=True, text=True,
        )
        if retry.returncode == 0 or "key_output_directory_not_empty" not in retry.stderr:
            raise RuntimeError("signer_identity_rerun_not_rejected")
        if (out / "broker-private.jwk").read_bytes() != broker_before:
            raise RuntimeError("broker_key_overwritten_on_rerun")
        if (out / "authority-private.pkcs8.b64").read_bytes() != authority_before:
            raise RuntimeError("authority_key_overwritten_on_rerun")
        if any(p.stat().st_mode & 0o077 for p in out.iterdir()):
            raise RuntimeError("key_file_permissions_not_private")
        if out.stat().st_mode & 0o077:
            raise RuntimeError("key_directory_permissions_not_private")
        with tempfile.TemporaryDirectory() as dirty_root:
            dirty = Path(dirty_root)
            (dirty / "sentinel").write_text("must-not-be-replaced", encoding="utf-8")
            denied = subprocess.run(
                ["node", str(ROOT / "scripts/operator/reference_release_keygen.mjs"), str(dirty)],
                cwd=ROOT, capture_output=True, text=True,
            )
            if denied.returncode == 0 or (dirty / "sentinel").read_text() != "must-not-be-replaced":
                raise RuntimeError("preexisting_output_not_protected")
        with tempfile.TemporaryDirectory() as permissive_root:
            permissive = Path(permissive_root)
            permissive.chmod(0o755)
            denied = subprocess.run(
                ["node", str(ROOT / "scripts/operator/reference_release_keygen.mjs"), str(permissive)],
                cwd=ROOT, capture_output=True, text=True,
            )
            if denied.returncode == 0 or any(permissive.iterdir()):
                raise RuntimeError("permissive_output_dir_not_rejected")

    print("REFERENCE_OPERATOR_HELPER_ROUNDTRIP_PASS=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

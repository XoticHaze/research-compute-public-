from pathlib import Path
import tempfile

from scripts.mmibkr_attested_source_to_canonical_receipt_v1 import adapt

BASE = {
    "schema": "mmibkr.attested_source_materialization.v2",
    "ok": True,
    "source_sha": "35e6b44e5c2618f780a84c1c204fe14c76bdf0e5",
    "source_archive_sha256": "59f7a59837354db488817d2d0a0981e939e5182ee8c1d6d300befd4775016917",
    "private_repository_token_used": False,
    "broker_credentials_used": False,
    "plaintext_emitted": False,
    "live_execution_allowed": False,
    "vault_attestation_verified": True,
}

def test_adapter_emits_exact_canonical_receipt():
    with tempfile.TemporaryDirectory() as td:
        node = dict(BASE, source_root=td)
        out = adapt(node)
        assert out["schema"] == "mmibkr.private_source_materialization.v1"
        assert out["mmibkr_head"] == BASE["source_sha"]
        assert out["source_archive_sha256"] == BASE["source_archive_sha256"]
        assert out["source_root"] == str(Path(td).resolve())
        assert out["broker_credentials_materialized"] is False
        assert out["paper_or_live_authority"] is False

def test_adapter_rejects_authority_escalation():
    with tempfile.TemporaryDirectory() as td:
        for key in ("private_repository_token_used", "broker_credentials_used", "plaintext_emitted", "live_execution_allowed"):
            node = dict(BASE, source_root=td)
            node[key] = True
            try:
                adapt(node)
            except ValueError:
                pass
            else:
                raise AssertionError(f"{key}=true accepted")

def test_adapter_rejects_unverified_attestation():
    with tempfile.TemporaryDirectory() as td:
        node = dict(BASE, source_root=td, vault_attestation_verified=False)
        try:
            adapt(node)
        except ValueError:
            pass
        else:
            raise AssertionError("unverified attestation accepted")

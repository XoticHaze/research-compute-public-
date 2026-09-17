from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "cloudflare" / "fleet-authority" / "src" / "index.js"
WRANGLER = ROOT / "cloudflare" / "fleet-authority" / "wrangler.jsonc"


def test_worker_authorizes_stable_github_workload_identity_without_commit_sha_gate():
    text = WORKER.read_text()

    # Stable workload identity remains mandatory.
    assert "claims.repository !== EXPECTED_REPOSITORY" in text
    assert "claims.ref !== ALLOWED_REF" in text
    assert "claims.workflow_ref !== ALLOWED_WORKFLOW_REF" in text
    assert "String(claims.run_id) !== requestedRunId" in text

    # A moving commit SHA must never be an authorization requirement.
    assert "allowed_workflow_sha" not in text.lower()
    assert "ALLOWED_WORKFLOW_SHA" not in text
    assert "claims.workflow_sha !==" not in text

    # SHA may remain in the sealed envelope only as provenance/audit metadata.
    assert "workflow_sha: claims.workflow_sha" in text


def test_worker_keeps_cryptographic_and_time_validation():
    text = WORKER.read_text()
    assert "RSASSA-PKCS1-v1_5" in text
    assert "oidc_signature_rejected" in text
    assert "oidc_time_rejected" in text
    assert "claims.iss !== GITHUB_ISSUER" in text
    assert "!aud.includes(EXPECTED_AUDIENCE)" in text


def test_wrangler_has_no_mutable_sha_or_legacy_event_authority_vars():
    text = WRANGLER.read_text()
    assert "ALLOWED_WORKFLOW_SHA" not in text
    assert "ALLOWED_EVENT_NAME" not in text
    assert "ALLOWED_REF" not in text

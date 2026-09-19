from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "cloudflare" / "fleet-authority" / "src" / "index.js"
WRANGLER = ROOT / "cloudflare" / "fleet-authority" / "wrangler.jsonc"


def test_worker_authorizes_only_native_b1_or_exact_reusable_b1_identity():
    text = WORKER.read_text()

    # Stable native B1 workload identity remains explicit.
    assert "claims.repository === EXPECTED_REPOSITORY" in text
    assert "claims.ref === ALLOWED_REF" in text
    assert "claims.workflow_ref === ALLOWED_WORKFLOW_REF" in text
    assert "ALLOWED_EVENTS.has(claims.event_name)" in text

    # Reusable B1 is admitted only from the canonical public runtime caller.
    assert "RUNTIME_CALLER_REPOSITORY = 'XoticHaze/mm-ibkr-runtime'" in text
    assert "RUNTIME_CALLER_REF = 'refs/heads/main'" in text
    assert (
        "XoticHaze/mm-ibkr-runtime/.github/workflows/"
        "mmibkr-selected-runtime-cloud-r1.yml@refs/heads/main"
    ) in text
    assert "claims.job_workflow_ref === REUSABLE_B1_JOB_WORKFLOW_REF" in text
    assert "RUNTIME_CALLER_EVENTS.has(claims.event_name)" in text
    assert "if (!nativeB1 && !reusableB1)" in text

    # Both modes still require public hosted runner + exact caller run id.
    assert "claims.repository_visibility !== 'public'" in text
    assert "claims.runner_environment !== 'github-hosted'" in text
    assert "String(claims.run_id) !== requestedRunId" in text

    # A moving commit SHA must never be an authorization requirement.
    assert "allowed_workflow_sha" not in text.lower()
    assert "ALLOWED_WORKFLOW_SHA" not in text
    assert "claims.workflow_sha !==" not in text
    assert "claims.job_workflow_sha !==" not in text

    # Moving SHAs remain provenance only.
    assert "workflow_sha: claims.workflow_sha" in text
    assert "job_workflow_sha: String(claims.job_workflow_sha || '')" in text


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
    assert "GITHUB_ALLOWED_EVENT" not in text
    assert "GITHUB_ALLOWED_REF" not in text

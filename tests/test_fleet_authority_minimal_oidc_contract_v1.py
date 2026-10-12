from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "cloudflare" / "fleet-authority" / "src" / "index.js"
WRANGLER = ROOT / "cloudflare" / "fleet-authority" / "wrangler.jsonc"


def test_worker_authorizes_stable_github_workload_identity_without_commit_sha_gate():
    text = WORKER.read_text()

    # Stable workload identity remains mandatory.
    assert "claims.repository !== EXPECTED_REPOSITORY" in text
    assert "claims.repository_visibility !== 'public'" in text
    assert "claims.runner_environment !== 'github-hosted'" in text
    assert "claims.ref !== allowedRef" in text
    assert "claims.workflow_ref !== allowedWorkflowRef" in text
    assert "!allowedEvents.has(claims.event_name)" in text
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
    assert "GITHUB_ALLOWED_EVENT" not in text
    assert "GITHUB_ALLOWED_REF" not in text


def test_canonical_research_session_uses_attested_vault_snapshot_not_expiring_pin():
    exchange = (
        ROOT / "cloudflare" / "fleet-authority" / "src" / "source_exchange.js"
    ).read_text()

    assert "const REGISTRY_BACKTEST_GENERIC_SELECTED_SURFACE_IDENTITY = {" in exchange
    assert (
        "mmibkr-canonical-research-session-bau-r1.yml@refs/heads/main"
        in exchange
    )
    assert "matchedRegistryBacktestGenericSelectedSurface" in exchange
    assert "privateTestProbeUnwrapPathAllowed" in exchange

    # Research-session source access is bounded by exact workflow identity and
    # _resolveVaultSnapshotApproval's exact SHA/manifest/archive attestation,
    # not by a second temporary date/source pin that can expire independently.
    assert "REGISTRY_BACKTEST_GENERIC_SELECTED_SURFACE_EXPIRES_AT" not in exchange
    assert "REGISTRY_BACKTEST_GENERIC_SELECTED_SURFACE_SOURCE" not in exchange
    assert "_resolveVaultSnapshotApproval" in exchange
    assert "reusableExactShaBootstrapAttestation" in exchange
    assert "SOURCE_VAULT_BOOTSTRAP_IDENTITY" in exchange

def test_production_live_bot_profile_is_distinct_and_strictly_oidc_bound():
    worker = WORKER.read_text(encoding="utf-8")
    consumer = (ROOT / "scripts/fleet_authority_envelope_consumer_v1.py").read_text(encoding="utf-8")
    assert "LIVE_BOT_AUTHORITY = 'ibkr-live-bot'" in worker
    assert "LIVE_BOT_ALLOWED_REF = 'refs/heads/main'" in worker
    assert ".github/workflows/mmibkr-selected-runtime-live-owner-r1.yml@refs/heads/main" in worker
    assert "LIVE_BOT_ALLOWED_EVENTS = new Set(['workflow_dispatch'])" in worker
    assert "allowedEvents: LIVE_BOT_ALLOWED_EVENTS" in worker
    assert "isIbkrLiveBotSeal" in worker
    assert "sealIbkrLiveReadonlyGatewayEnv(body, env, oidc, { writable: true })" in worker
    assert "const authority = writable ? LIVE_BOT_AUTHORITY : LIVE_READONLY_AUTHORITY" in worker
    assert "writable ? 'READ_ONLY_API=no' : 'READ_ONLY_API=yes'" in worker
    assert "writable ? 'ENABLE_LIVE_TRADING=1' : 'ENABLE_LIVE_TRADING=0'" in worker
    assert "writable ? LIVE_BOT_ENVELOPE_SCHEMA : LIVE_READONLY_ENVELOPE_SCHEMA" in worker
    assert '"production_live_readonly": {' in consumer
    assert '"production_live_bot": {' in consumer
    assert '"authority": LIVE_BOT_AUTHORITY' in consumer
    assert '"envelope_schema": LIVE_BOT_ENVELOPE_SCHEMA' in consumer
    assert "const isIbkrLiveReadonlySeal = url.pathname === '/v1/authorities/ibkr-live-readonly/seal'" in worker
    assert "const isIbkrLiveBotSeal = url.pathname === '/v1/authorities/ibkr-live-bot/seal'" in worker


def test_live_bot_source_unwrap_is_exact_workflow_dispatch_only():
    exchange = (
        ROOT / "cloudflare" / "fleet-authority" / "src" / "source_exchange.js"
    ).read_text(encoding="utf-8")
    worker = WORKER.read_text(encoding="utf-8")
    # Same original OIDC workflow identity, no changes to live seal admission.
    assert "const LIVE_BOT_SOURCE_UNWRAP_IDENTITY = {" in exchange
    assert "mmibkr-selected-runtime-live-owner-r1.yml@refs/heads/main" in exchange
    assert "const matchedLiveBotSourceUnwrap = matchesIdentity(claims, LIVE_BOT_SOURCE_UNWRAP_IDENTITY);" in exchange
    assert "const liveBotSourceUnwrapPathAllowed = (" in exchange
    assert "pathname === '/v1/source-vault/unwrap'\n      && claims.event_name === 'workflow_dispatch'" in exchange
    assert "matchedLiveBotSourceUnwrap && liveBotSourceUnwrapPathAllowed" in exchange
    assert "LIVE_BOT_ALLOWED_EVENTS = new Set(['workflow_dispatch'])" in worker
    assert "new Set(['workflow_dispatch', 'push'])" not in worker

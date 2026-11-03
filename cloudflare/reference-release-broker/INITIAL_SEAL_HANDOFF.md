# Neutral broker initial-seal handoff
Status: SOURCE-ONLY / NOT DEPLOYED / INITIAL SEAL UNVERIFIED. Updated: 2026-11-03.
Owner: independently authenticated neutral Cloudflare administrator and protected CommandCenter #809 release authority.
Source baseline: 2fcfcbb07478718aa1f9a60bc59af37a5c629b43 (public reference release candidate, not a deployed source claim).

## Critical distinction
The existing neutral `reference-release-broker-v1` Worker is not known to hold a working P-256 signer. The existing `reference-release-maintainer-v1` and `reference-maintenance-authority-v1` are post-seal controllers: the latter refuses maintenance authorization without an already importable broker signer. A maintainer Editor credential cannot bootstrap that key. Public `/healthz` 200 plus `/v1/public-key` 503 is HEALTH_ONLY_KEY_UNVERIFIED_SOURCE_UNKNOWN; it does not identify an active source version.

## Preflight: all observations must be independent of GitHub and sanitized
1. Select the already existing **neutral** account and existing three Workers. Do not duplicate an account, Worker, token, secret, Durable Object or maintenance authority; do not reuse original-account credentials.
2. Independently read back actual 100%-active versions/source metadata, exact binding names and the maintainer's internal `brokerState()` result. A dashboard binding label alone is not authenticated API/functionality proof.
3. Check all broker and private-authority key custody locations for previously generated/installed signer material. Never regenerate or silently rotate an existing identity. Record public fingerprint, not key bytes.
4. Demonstrate GitHub-reachable credentials cannot mutate the neutral broker, signer, authority, controller Workers or approval policy. The Secrets Store `BROKER_EDITOR_TOKEN` binding belongs ONLY on the maintainer; the existing broker-only Editor token does not authorize controller changes.
5. In a separately approved neutral-administrator deployment, remove ONLY an extraneous `BROKER_EDITOR_TOKEN` binding from the authority if still present. Preserve `MAINTAINER`, `AUTHORITY_STATE`, `AUTO_APPLY_ENABLED=0` and the underlying Secrets Store secret. Removal is independent of signer initialization.
6. Record last-known-good live version, actual approved harness ref/SHA and source package. `wrangler.jsonc` is not authoritative proof of deployed bindings. Do not automatically merge protected public #2103 or rotate harness policy.

If any protected account/credential/version/approval preflight fails, STOP before generation or deployment, classify the held owner boundary, and leave the live system unchanged.

## Preparation
- Reviewed create-once helper: `scripts/operator/reference_release_keygen.mjs`, exact Git blob `f8acfd31e6282abdeb38c54610d81df808a84c96` on public source baseline above. Generate only ONCE on an independently controlled private host, only after confirming no prior signer exists. Use a fresh private non-symlinked empty directory, verify the pinned source and Node 22+; never copy key contents or private paths into GitHub, chat or public CI. Its exclusive writes and private-directory policy reject accidental overwrite.
- Exact four-module broker candidate: `cloudflare/reference-release-broker/src/index.js`, `intent.js`, `placement.js`, `ticket.js`. Previous source-only candidate package SHA-256: `2ab1d0d89d0614f1e278d01d5b66e7d0d40ef177c4d14deab42d5e23a7a27cd6`. Recompute/verify exact bytes before owner approval; this SHA is NOT a live deployment receipt.
- **RETIRED:** `scripts/operator/bootstrap_reference_release_broker.ps1` previously used original-account workers.dev and legacy `reference_broker_keygen.mjs`, which writes overwrite-prone keys and contains obsolete harness assumptions. The PowerShell bootstrap is intentionally disabled. The legacy JS helper is not approved for actual first seal.

## Protected owner-only sequence
1. Approve exact source/version/package, independent account, current immutable OIDC/harness policy and rollback. Do not take a private mutable credential from GitHub.
2. If (and only if) no existing signer identity is found, generate new P-256 broker and independent grant-authority keys in private custody with the approved create-once helper.
3. Provision broker PRIVATE P-256 JWK only as the existing neutral broker `BROKER_SIGNING_PRIVATE_JWK`; provision ONLY independent authority PUBLIC P-256 raw key as `AUTHORITY_PUBLIC_B64`. Keep authority PRIVATE PKCS8 outside the broker/GitHub/public runner. Pin broker public key/fingerprint with private verifier. Never disclose either private key or Secrets Store bearer.
4. Independently deploy exact approved broker package to the existing Worker, retaining `GRANT_LEDGER`, signed one-use grant semantics, current immutable `ALLOWED_JOB_WORKFLOW_REF/SHA` and admission policy. Read back version, traffic=100%, bindings, sealed source, key fingerprint, independent mutation DENY and rollback identity. Use no direct unauthenticated source promotion.
5. Verify actual production `/healthz` AND `/v1/public-key`: require HTTP 200 public key matching an independently calculated `sha256:` P-256 fingerprint. Key availability is still not R1 acceptance.
6. ONLY after successful independent signer seal, use existing signed maintenance route for an approved four-module exact-version candidate, with active-binding inheritance, race checks, 100% promotion, identity proof and rollback.
7. Separately approve protected draft #2103 immutable OIDC pin alignment; perform real GitHub OIDC -> private signed grant -> broker signed ticket -> A1 private encrypted capsule -> privately verified encrypted ACK. Prove absent/wrong grant, replay, wrong runner/ref/SHA/key, tamper, expiration and broker outage all fail closed. Ed25519 PLACED issuer registration and durable nonce consumer are a separate admission gate.
8. Only the protected owner can promote CommandCenter #809 to `R1_SIGNED_ADOPTABLE_NON_PHI` after all live evidence. MM-IBKR #766 retains separate explicit human release hold. No R2/PHI/live trading authorization is implied.

## Secret-free administrative acceptance template
```text
neutral_account_match: yes/no
broker_worker_name: reference-release-broker-v1
effective_version_id: <observed>
active_traffic_percent: <observed>
source_package_verified: yes/no
maintainer_effective_version_and_brokerState: pass/fail/not-tested
extra_authority_editor_binding_removed: yes/no/not-approved
service_durable_object_bindings: pass/fail
signer_and_authority_public_binding_present: yes/no
public_key_http_status: <observed>
verified_public_broker_key_id: sha256:<fingerprint> / unverified
github_reachable_mutation_denial: proven/not-proven
last_known_good_rollback: recorded/not-recorded
real_signed_oidc_and_a1_encrypted_result_ack: pass/fail/not-run
negative_release_matrix: pass/fail/not-run
```
Do NOT include any bearer, private key, JWK, PKCS8 content or recovery path in receipts. The protected owning gate and `DEPLOYMENT_BOUNDARY.md` remain authoritative; this file authorizes no privileged mutation.

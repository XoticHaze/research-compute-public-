# Cloudflare-primary cc-pi4 protected root releases (2026-11-14)

**Owner decision:** Cloudflare is the normal owner-signing and release-authorization authority. The existing offline device signer may remain for **emergency fallback only**. Do not turn routine Pi upgrades into Mac SSH/sudo or device-held signature ceremonies.

**Status:** Source candidate, **NOT PROD ADMITTED**. This file does not install root code, initialize a signing key, transfer a Durable Object, turn on a signer, or issue a protected release.

## Verified existing inventory

- Original Cloudflare account (not the separately administered neutral compute account): existing `mmibkr-operator-console` Worker, Cloudflare Access human authorization, `PI_OWNER_APPROVER` SQLite Durable Object binding, exact object name `cc-pi4-owner-v1`.
- Durable Object code already stores optional `pi_owner_key_v1` Ed25519 key material and optional `pi_owner_enrollment_v1` public-key enrollment record. **Source existence is not proof that either storage record exists in production.** An enrollment record is operator-attested, not Pi-root attested.
- The existing Cloudflare owner signer already verifies explicit operator allowlist, independent activation for create-once key initialization, owner consent, and one-use grant issuance. Its original domains were BOT bootstrap and replacement. This candidate adds the **separate** root release domain `commandcenter.pi.release_request_approval.v1\\0`, preserving the same key identifier `ccpi-owner-bootstrap-ed25519-v1` and canonical JSON bytes.
- Existing private queue transport and same-ID receipt projection for `pi.release.apply` already exist. Main-branch operator-console currently **returns HTTP 410** for the legacy key issuer paths and requires a device-held signature for normal dispatch. Do not flip `PI_OWNER_SIGNER_ENABLED=1` on this current GitHub-deployable console.
- The latest observed root-only `pi.bot.execution_gates_status` result (`mw-20261114000039684-release-gates-readonly`, finished 2026-11-14T00:25:58Z) reports `owner_device_public_key_root_owned_pem_header_present=false`. This only proves that the expected root-protected PEM header was not detected then; it does not prove a Cloudflare keypair is absent.
- Separate neutral-account P-256 maintenance signer, GitHub OIDC, Pi SSH keys and Pi root-attestation keys are different trust roles. Do not conflate or rotate them.

## Correct release authority and custody boundary

1. **The Cloudflare owner signing key remains in Cloudflare.** Reuse the exact `pi_owner_key_v1` Durable Object identity if already initialized; never export its private key into GitHub, browser code, chat or an operator helper. No new key unless actual status proves none exists and a separately owner-approved one-time issuance is indispensable.
2. **Isolate signing from GitHub-redeployable application code.** The `mmibkr-operator-console` may be deployed by existing GitHub-scoped Cloudflare Worker credentials. Hence giving that same script access to an active root-signing private key would let a GitHub code writer forge owner root grants. Do **not** reactivate the legacy signer on that mutable Worker.
3. Use an **independently Cloudflare-admin-controlled issuer** in the **already-existing independently administered neutral Cloudflare account**, with a separate Worker script / authority boundary and restricted deploy permissions; do not create a separate new signing key. Cloudflare's same-account Durable Object namespace transfer can preserve an existing SQLite DO identity, if the independent Cloudflare administrator safely performs a reviewed two-phase namespace transfer. This requires verified existing object identity, current deployment bindings, separate trusted Access application, a protected service endpoint, and rollback.
4. The isolated issuer itself must verify Cloudflare Access JWT cryptographically, exact issuer/audience/owner allowlist, fresh owner review, strict same-origin request, short grant expiry and domain, nonreplay issuance, and matching enrolled root public-key fingerprint. **Never accept a caller-supplied `operator` object as issuer authentication**; an editable front-end or GitHub worker must not be capable of authorizing signing via a service binding alone.
5. Reuse the existing scoped Cloudflare private-queue GitHub credential only after its binding and permissions are independently verified, and do not copy its value into any repository or user-visible report. Publish fixed typed signed grant **before** fixed typed request, and verify the same request ID in the Pi root outbox.
6. Keep the existing offline device-held Ed25519 signer available only through a separately approved emergency recovery path. A local root-owned one-use approval is break-glass recovery, not a routine install flow. Never accept an unsigned Git request or a newly supplied public key as a root release grant.

## Live Cloudflare owner-status receipt, 2026-11-14

The operator opened the already-authenticated existing `/api/pi-owner/status` and supplied this exact sanitized status:

```json
{"schema":"commandcenter.pi.owner_signer_status.v1","initialized":false,"enrolled":false,"public_key_pem":null,"public_key_sha256":null,"signing_enabled":false,"github_transport_configured":false}
```

**Classification:** `PI_OWNER_CLOUDFLARE_DO_UNINITIALIZED__QUEUE_UNCONFIGURED`.
This is authoritative live evidence about the *specific existing* `PI_OWNER_APPROVER` object identity `cc-pi4-owner-v1`, not evidence that all Cloudflare accounts lack keys. It decisively rules out *reusing* a `pi_owner_key_v1` keypair from this DO. Do not call code-backed key issuance a preexisting enrolled key. The previous `initialized`-unknown branch is now closed.

Separate source inventory (read 2026-11-14):
- Original-account `fleet-authority` uses X25519 ephemeral secret encryption, not detached Ed25519 root-release approvals.
- Neutral-account maintenance authority has a P-256 ECDSA manifest signer with explicitly different role and scope.
- Neutral-account broker release-ticket signer also uses P-256 ECDSA and is preseal. It is not an original-account Pi owner signer.
- Existing Cloudflare Access JWT uses RS256 to authenticate the human session; the JWT does **not** cryptographically bind a particular root source SHA, predecessor, nonce and expiry as a detached root approval.

Therefore no *verified compatible* Cloudflare-held root-approval key has been recovered. Unless independent owner custody inventory identifies another existing Ed25519 Pi-owner key and proves its authority, one **first issuance** inside Cloudflare is necessary. This must NOT involve a new phone/device-held key, new account, new broad Cloudflare token, GitHub secret export or unattended root enrollment. Reuse the existing Access allowlist, original account, DO infrastructure, typed Pi queues, and existing Cloudflare project permission boundaries wherever possible.

**Critical cloud-owned deployment isolation:** Before initializing that key, create/admit an **independently Cloudflare-admin-deployed signer** in the independently administered neutral account with no GitHub-scoped Worker edit permission. Since the observed DO is empty, migrating its empty namespace or creating a new dedicated DO class does not risk losing retained signing material. The key must be created exactly once *only after* signer isolation and owner-authenticated activation. The GitHub-deployable `mmibkr-operator-console` must remain signing-disabled/HTTP 410. Owner still reviews each exact protected release with Access; the issuer signs one short-lived authorization and records one-use issuance.

**Root bootstrapping remains independently protected:** Existing cc-pi4 root reports no accepted owner verifier PEM. Root worker PR #1185 is source-only. No GitHub edit alone can install root trust. Prefer an already provisioned Cloudflare/CC authenticated owner route for first trust enrollment; otherwise surface the first-seal requirement explicitly. Normal production acceptance remains a later Cloudflare-signed remote `pi.release.apply` with same-ID root `passed`, no Mac/device signer.

## Next owner-only, read-only admission probe (no Mac, no key creation)

Open these existing Cloudflare Access-authenticated routes in the browser. They make no protected changes:

- `https://mmibkr-operator-console.slenderiq.workers.dev/api/pi-owner/status`
  - Record **only**: `initialized`, `enrolled`, `public_key_sha256`, `signing_enabled`, and `github_transport_configured`.
  - Do not share any private PKCS#8, secret, activation code, token, passphrase or authenticated cookies. A **public** PEM may be present in the response; its fingerprint is enough for inventory.
- `https://mmibkr-operator-console.slenderiq.workers.dev/api/pi-owner/device-status`
  - Record **only**: `owner_public_key_configured`, `private_queue_transport_configured`, `legacy_worker_signer_disabled`.

If the first endpoint reports `initialized=false`, **stop** before generating any key; perform a separate search of all existing Cloudflare-authority custodians. If it reports `true`, retain the fingerprint and reconcile it with the independent root-owned Pi public verifier, not with unrelated SSH or attestation keys.

## Protected implementation and production proof

- Implement/validate the isolated Cloudflare-admin-only issuer around the existing retained DO (no GitHub-deployable signer access) and the newly supported exact root-release signing contract; independent Cloudflare owner admits its script, Access app, bindings and deployment permissions.
- Independently source-review, test and admit CommandCenter PR `#1185` into the final root release. Existing `pi.release.apply` cannot accept a Cloudflare signature until its signed-grant verifier is actually installed.
- Find an already trusted CC/Cloudflare remote root-owner route for first public-key enrollment. The current ordinary Pi agent cannot write `/etc/commandcenter-pi/keys/pi-owner-approver-ed25519.pem`; don't try to bypass its root boundary. If no separately approved remote first-seal route exists, classify the **one first-trust-anchor bootstrap** as an explicit blocked gate; emergency attended recovery is not routine release acceptance.
- Once admitted, the real owner approves one fresh exact source SHA/current predecessor through Cloudflare. The independent issuer signs and publishes `pi-node/release-signed-approval.json` followed by `pi-node/release-request.json`. Pi root independently verifies the pinned Cloudflare public key and returns an immutable **same-ID `passed`** receipt in `pi-node/release-results`; read back actual new generation.
- Only after the above real root installation, with **no Mac helper and no device signer used in that normal path**, close the recurring-root-install problem.

## Hard safety limits

No private GitHub Actions compute, arbitrary remote shell, Gateway restart, IBKR session reauthentication, changes to LIVE flags, changes to writer/ledger/margin admission or external holdings, key export, key rotation, or automatic protected source admission. Source candidate and synthetic checks are not production release evidence.

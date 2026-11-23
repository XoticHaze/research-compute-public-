# Shared Compute Worker Factory (generic CommandCenter management executor)

Status: **SOURCE CANDIDATE, NOT DEPLOYED OR ADMITTED**.
Owner: CommandCenter Shared Compute factory contract, separate from the protected neutral release authority.
This is a *reusable account-level management service*, not a project-specific new deployment token.

## Why this exists
The existing `Shared Compute Worker Factory` bootstrap/finalization scripts already encode
a product-level Workers Admin allow plus **same-role Workers Admin DENY** for the
three historical neutral reference Workers. The same-role DENY shape passed a disposable
Cloudflare sentinel test. The final factory token, Secrets Store enrollment and permanent
Cloudflare-side executor are **not verified complete**. Preserve WaterBoys legacy creator
until a replacement has real one-time terminal receipts.

This component supplies the missing, bounded executor for *ordinary* Workers in the original
SlenderIQ account. It CANNOT touch the separately administered
Shared Compute Neutral Authorization account. It is **not** a way to auto-create
`ccpi-owner-cloudflare-authority` there or to enroll Pi root keys.

## Existing bootstrap: do not duplicate
- Reconcile the existing `Shared Compute Token Provisioner TEMP` and `WaterBoys GitHub Deploy` metadata,
  the finalization receipt, and actual active Cloudflare tokens first.
- If an already-proven `Shared Compute Worker Factory` token exists, **do not create another**.
- Independently prove same-role DENY against actual protected immutable Worker IDs and disposable sentinel;
  retain existing ordinary Worker create/delete and account separation.
- Enroll the verified factory token directly in Cloudflare Secrets Store, not GitHub, chat,
  CI, a branch or a deployed site. No token value is returned by this service.
- If any proof fails, stop and preserve existing working WaterBoys/other deployment authority.

## Operations (typed, strict, one-use)
`POST /v1/execute`, exact JSON with `schema=commandcenter.cloudflare.factory_request.v1`,
32 lowercase hex `request_id`, ordinary `worker_name`, and UTC Unix
`expires_at` no more than 300 seconds ahead:
- `ordinary_worker.create`: creates one **inert** ordinary Worker, with no Worker script,
  preview URLs or Workers.dev subdomain. Exact created name and immutable Worker ID are
  read back. No overwrite/delete, source upload or access-policy mutation is supported.
- `existing_worker.inspect`: **separately disabled by default**, owner-only exact account-pinned GET for a preexisting ordinary Worker. Requires immutable `worker_id` and matching `worker_name`, both checked against Cloudflare. Returns a sanitized `existing_worker_identity_verified` receipt with `cloudflare_mutations=0` and flags that source version and live deployment were **not** verified. Never returns bearer tokens, enumerates account tokens, edits protected Workers or issues an approval.
- `existing_worker.editor_token.issue`: optional, **separately disabled by default**.
  Requires exact existing `worker_id` matching the approved ordinary name plus
  `token_ttl_hours` 1 through 168. Issues only a single-Worker Editor token,
  stores it immediately in an approved Cloudflare Secrets Store, never exposes the
  bearer, and attempts to revoke a new token on storage failure.

These operations are separate by design: ordinary Worker creation must not automatically
mint another token for each project. Once the generic manager is admitted, prefer
reusing the manager for later reviewed deployments rather than multiplying credentials.

### Bounded scratch version staging, off-traffic only, NOT deployed

Source now supports a **fourth independently disabled typed operation**:
`existing_worker.scratch_version.stage`. It is owner-Access-authenticated,
not a machine-OIDC write grant. All original `FACTORY_EXECUTOR_ENABLED` /
one-use Durable Object claim / private queue receipt controls still apply.
**`FACTORY_STAGE_VERSION_ENABLED=0` is the additional mandatory gate.**
The live deployed factory is unchanged and must not have this flag enabled
without independent owner source/version, credential isolation and replay admission.

Exact request keys: `schema`, `operation`, `request_id`, `worker_name`,
`worker_id`, `source_commit` (40-hex public repository commit),
`source_sha256` (64-hex), `expires_at` (≤300 seconds). The Worker
must be a disposable `cc-scratch-*` name, **not WaterBoys, NVIDIA,
Fleet Authority, MM-IBKR, the factory itself or any protected neutral Worker**.
The code path verifies the immutable existing Worker ID and name via fixed
original SlenderIQ Cloudflare GET, fetches a single reviewed public module from
`XoticHaze/research-compute-public-` at exact
`cloudflare/ordinary-scratch-releases/<worker_name>/worker.mjs`,
enforces a 32 KiB maximum, verifies the complete SHA-256 digest, then uploads
**one off-traffic version** using the current official Cloudflare
`POST /accounts/<account_id>/workers/scripts/<script_name>/versions`
multipart API. It receives a version UUID and returns a sanitized digest,
worker ID and staging-only receipt. There is **no deployment POST, 100%
traffic switch, custom domain, route, secrets or token issuance**.
An indeterminate POST result is terminal/replay-closed, never blindly retried.

The two **source-only** disposable test projects are:
`cloudflare/ordinary-scratch-releases/cc-scratch-proof-a/worker.mjs` and
`cc-scratch-proof-b/worker.mjs`. They are **not created as Cloudflare
Workers** and their mere presence does not prove an installed factory.
These are reusable first/second-project acceptance fixtures, not a
production publishing engine. Their fully resolved commit and source-file
SHA256 must be frozen into an approved typed proposal when live authorized.
The next extension after a successful admitted two-project stage/readback
must support exact existing production Worker settings/asset binding
preservation and independently approved deployment promotion. Do not widen
this scratch stage to production or neutral Workers by changing a prefix.

The Cloudflare upload operation is documented at
https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/methods/create/
and explicitly **uploads without deploying to the network**. Its existence
is a source contract, not a verified live HTTP acceptance.

### Optional unattended machine identity, read-only only, not admitted

Source implements a **separately disabled** `POST /v1/machine/readiness` and `POST /v1/machine/inspect` for direct GitHub OIDC callers. Fixed issuer and live JWKS are inherited from the existing fleet-authority RS256 verification pattern, but the trust root is **strictly limited** to `XoticHaze/research-compute-public-` main, exact `.github/workflows/cc-factory-machine-readonly-r1.yml`, `workflow_dispatch`, GitHub-hosted public runner, short validity, exact audience, run ID, attempts, SHA and verified RSA signature. Merely possessing a GitHub Actions token or repository write grant cannot bypass this check. There is **no Cloudflare bearer in the public job**.

The two new runtime flags `FACTORY_MACHINE_READONLY_ENABLED=0` and `FACTORY_MACHINE_INSPECT_ENABLED=0` are OFF by default. Readiness is only a sanitized machine-authenticated status, no credential binding or mutation required. Even machine `existing_worker.inspect` requires **four** independent gates (`MACHINE_READONLY`, `MACHINE_INSPECT`, `EXECUTOR`, `INSPECT`) plus the preexisting read-capable Cloudflare-held credential, matching Worker ID/name and one-use Durable Object ledger. **Machine creation, token issuance and Worker release are expressly NOT admitted** and have no OIDC dispatch path. Owner-only ordinary create/token workflow remains unchanged.

Cloudflare Access currently protects **all** factory URLs, so a signed OIDC caller is *not expected to reach* the new path unless an independent owner admits a path-specific machine identity route or another separately authenticated transport. **Do not bypass all Access, add an account-wide machine permit, enable either flag, or deploy new code using the legacy GitHub writer**. The opt-in public workflow only sends a live request if both `workflow_dispatch` input `live_identity_probe=true` and owner-controlled `CC_FACTORY_MACHINE_READONLY_ADMITTED=1` variable are set; ordinary offline tests need neither. Run is no substitute for verified Cloudflare-side source deployment and independent cutover.

Machine identity is **not** a protected approval grant. Future machine write operations need separate CommandCenter exact-project admission, signed/approved bounded requests, replay receipts and no ability to override protected neutral or factory source. The existing user Access owner route remains the protected administrative source of truth.

### Authentication and replay
The first implementation uses **direct owner-authenticated Cloudflare Access**.
The owner email and Access AUD must be independently configured. Every privileged
operation requires the exact Access context, same-origin JSON browser request,
account ID pin, operation enable flag and request TTL. A bound Durable Object claims
the request ID before any external API mutation and permanently rejects replay.
An ambiguous API/readback failure is terminal/indeterminate, not silently retried.

The source now includes a fixed **private CommandCenter GitHub proposal lane**:
`XoticHaze/CommandCenter-gate-control`, branch `cloudflare-factory-inbox`,
inert `cloudflare-factory/proposal.json`, and immutable
`cloudflare-factory/results/<request-id>.json`. The exact proposal SHA and
request ID are rechecked before an independent Cloudflare Access owner clicks
the one-shot approval in `/operator/factory`. The worker publishes its
nonsecret same-ID result into the private GitHub outbox using the separate
Cloudflare-bound `FACTORY_QUEUE_GITHUB_TOKEN`. No GitHub source write alone
authorizes a Cloudflare mutation.

This is **NOT YET** unattended CommandCenter OIDC / signed-grant execution.
The queue token's specific repository/branch permissions, deployed owner UI,
Cloudflare Secrets Store custody and terminal same-ID results require live
independent acceptance. Never allow arbitrary URLs, Worker source upload,
shell, secrets dump, or a GitHub-held privileged Cloudflare bearer.

### Cloudflare-side settings
Initial Wrangler config targets **only original SlenderIQ** account
`ce43cd7b917d98a4bb4866d30eed99c0`.
It configures the `FACTORY_LEDGER` SQLite Durable Object and leaves:

- `FACTORY_EXECUTOR_ENABLED=0`
- `FACTORY_CREATE_ENABLED=0`
- `FACTORY_INSPECT_ENABLED=0`
- `FACTORY_MACHINE_READONLY_ENABLED=0`
- `FACTORY_MACHINE_INSPECT_ENABLED=0`
- `FACTORY_SCOPED_TOKEN_ENABLED=0`
- `FACTORY_STAGE_VERSION_ENABLED=0`

It never configures GitHub Builds or a GitHub Actions deploy.

An independently authorized original-account administrator must deploy the reviewed
immutable source, disconnect all GitHub deployment rights from this executor,
create a Cloudflare Access app protecting **every path**, set `FACTORY_ACCESS_AUD`
and `FACTORY_ALLOWED_EMAILS` for the exact owner, and bind only the
preexisting/proven Cloudflare-side Secrets Store identities:
`FACTORY_WORKERS_ADMIN`, optionally `FACTORY_TOKEN_ISSUER` (account tokens create
only) and `FACTORY_SECRET_WRITER` (Secrets Store edit only), plus
`FACTORY_SECRETS_STORE_ID`. Do not activate any mutation flags yet.

After independent readback of active Worker version, binding isolation,
neutral DENY, expected Owner Access, and immutable ledger identity,
the owner may separately approve `FACTORY_EXECUTOR_ENABLED` and
`FACTORY_CREATE_ENABLED`. Editor-token issuance requires a distinct approval.
All routines must remain fail-closed before this.


### Inspection admission and exact downstream use

After the original-account legacy write-isolation proof and Access AUD/owner settings are verified, an independently approved `FACTORY_INSPECT_ENABLED=1` may expose the exact-name/id read-only command. This is not an early activation shortcut: it still needs `FACTORY_EXECUTOR_ENABLED=1`, a securely bound `FACTORY_WORKERS_ADMIN` read-capable credential, the existing one-shot Durable Object, and ordinary account scope. Readback proves only the exact Worker identity; reviewed source hash, deployed script version, binding parity and domain serving require **independent** separate readbacks. This operation is intended as a diagnostic precursor to general typed reviewed-release support, **not** a substitute for releasing or accepting a Worker.

### Production acceptance, not just source CI
1. No GitHub secret or public artifact contains privileged Cloudflare bearer.
2. Factory token denies each protected same-account immutable Worker ID; different-account
   neutral Workers are independently out-of-scope.
3. Independently authorized creation of one disposable **ordinary** Worker succeeds,
   exact ID/readback passes, and same request ID replay is rejected.
4. Optional Editor issuance proves exact scope/expiration, Cloudflare Secret Store custody,
   no bearer response/log, and failed persistence revocation.
5. Record a sanitized terminal receipt and link it from CommandCenter.
6. Only then retire the legacy WaterBoys factory token, and only after checking downstream consumers.

## References
- `XoticHaze/CommandCenter/docs/security/SHARED_COMPUTE_WORKER_FACTORY_BOUNDARY_V1.md`
- `XoticHaze/CommandCenter/docs/handoffs/CLOUDFLARE_WORKER_FACTORY_NEUTRAL_BOUNDARY_HANDOFF_20260929.md`
- `scripts/finalize_shared_compute_worker_factory_macos.py` (historical source, NOT default execution route)
- https://developers.cloudflare.com/workers/authorization/workers/
- https://developers.cloudflare.com/secrets-store/integrations/workers/
- https://developers.cloudflare.com/api/resources/accounts/subresources/tokens/methods/create/

# Shared Compute Worker Factory (generic CommandCenter management executor)

Status: **SOURCE CANDIDATE, NOT DEPLOYED OR ADMITTED**.
Owner: CommandCenter Shared Compute factory contract, separate from the protected neutral release authority.
This is a *reusable account-level management service*, not a project-specific new deployment token.

## Why this exists
The existing \`Shared Compute Worker Factory\` bootstrap/finalization scripts already encode
a product-level Workers Admin allow plus **same-role Workers Admin DENY** for the
three historical neutral reference Workers. The same-role DENY shape passed a disposable
Cloudflare sentinel test. The final factory token, Secrets Store enrollment and permanent
Cloudflare-side executor are **not verified complete**. Preserve WaterBoys legacy creator
until a replacement has real one-time terminal receipts.

This component supplies the missing, bounded executor for *ordinary* Workers in the original
SlenderIQ account. It CANNOT touch the separately administered
Shared Compute Neutral Authorization account. It is **not** a way to auto-create
\`ccpi-owner-cloudflare-authority\` there or to enroll Pi root keys.

## Existing bootstrap: do not duplicate
- Reconcile the existing \`Shared Compute Token Provisioner TEMP\` and \`WaterBoys GitHub Deploy\` metadata,
  the finalization receipt, and actual active Cloudflare tokens first.
- If an already-proven \`Shared Compute Worker Factory\` token exists, **do not create another**.
- Independently prove same-role DENY against actual protected immutable Worker IDs and disposable sentinel;
  retain existing ordinary Worker create/delete and account separation.
- Enroll the verified factory token directly in Cloudflare Secrets Store, not GitHub, chat,
  CI, a branch or a deployed site. No token value is returned by this service.
- If any proof fails, stop and preserve existing working WaterBoys/other deployment authority.

## Operations (typed, strict, one-use)
\`POST /v1/execute\`, exact JSON with \`schema=commandcenter.cloudflare.factory_request.v1\`,
32 lowercase hex \`request_id\`, ordinary \`worker_name\`, and UTC Unix
\`expires_at\` no more than 300 seconds ahead:
- \`ordinary_worker.create\`: creates one **inert** ordinary Worker, with no Worker script,
  preview URLs or Workers.dev subdomain. Exact created name and immutable Worker ID are
  read back. No overwrite/delete, source upload or access-policy mutation is supported.
- \`existing_worker.editor_token.issue\`: optional, **separately disabled by default**.
  Requires exact existing \`worker_id\` matching the approved ordinary name plus
  \`token_ttl_hours\` 1 through 168. Issues only a single-Worker Editor token,
  stores it immediately in an approved Cloudflare Secrets Store, never exposes the
  bearer, and attempts to revoke a new token on storage failure.

These operations are separate by design: ordinary Worker creation must not automatically
mint another token for each project. Once the generic manager is admitted, prefer
reusing the manager for later reviewed deployments rather than multiplying credentials.

### Authentication and replay
The first implementation uses **direct owner-authenticated Cloudflare Access**.
The owner email and Access AUD must be independently configured. Every privileged
operation requires the exact Access context, same-origin JSON browser request,
account ID pin, operation enable flag and request TTL. A bound Durable Object claims
the request ID before any external API mutation and permanently rejects replay.
An ambiguous API/readback failure is terminal/indeterminate, not silently retried.

This is **NOT YET** a complete CommandCenter-invoked GitHub OIDC / signed-grant
queue. Before automated CC execution, add a separately reviewed exact fixed
private command inbox and independent owner approval to the same service, then
demonstrate a same-ID root-to-terminal receipt. Never allow arbitrary URLs,
Worker source upload, shell, secrets dump, or a GitHub-hosted bearer.

### Cloudflare-side settings
Initial Wrangler config targets **only original SlenderIQ** account
\`ce43cd7b917d98a4bb4866d30eed99c0\`.
It configures the \`FACTORY_LEDGER\` SQLite Durable Object and leaves:

- \`FACTORY_EXECUTOR_ENABLED=0\`
- \`FACTORY_CREATE_ENABLED=0\`
- \`FACTORY_SCOPED_TOKEN_ENABLED=0\`

It never configures GitHub Builds or a GitHub Actions deploy.

An independently authorized original-account administrator must deploy the reviewed
immutable source, disconnect all GitHub deployment rights from this executor,
create a Cloudflare Access app protecting **every path**, set \`FACTORY_ACCESS_AUD\`
and \`FACTORY_ALLOWED_EMAILS\` for the exact owner, and bind only the
preexisting/proven Cloudflare-side Secrets Store identities:
\`FACTORY_WORKERS_ADMIN\`, optionally \`FACTORY_TOKEN_ISSUER\` (account tokens create
only) and \`FACTORY_SECRET_WRITER\` (Secrets Store edit only), plus
\`FACTORY_SECRETS_STORE_ID\`. Do not activate any mutation flags yet.

After independent readback of active Worker version, binding isolation,
neutral DENY, expected Owner Access, and immutable ledger identity,
the owner may separately approve \`FACTORY_EXECUTOR_ENABLED\` and
\`FACTORY_CREATE_ENABLED\`. Editor-token issuance requires a distinct approval.
All routines must remain fail-closed before this.

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
- \`XoticHaze/CommandCenter/docs/security/SHARED_COMPUTE_WORKER_FACTORY_BOUNDARY_V1.md\`
- \`XoticHaze/CommandCenter/docs/handoffs/CLOUDFLARE_WORKER_FACTORY_NEUTRAL_BOUNDARY_HANDOFF_20260929.md\`
- \`scripts/finalize_shared_compute_worker_factory_macos.py\` (historical source, NOT default execution route)
- https://developers.cloudflare.com/workers/authorization/workers/
- https://developers.cloudflare.com/secrets-store/integrations/workers/
- https://developers.cloudflare.com/api/resources/accounts/subresources/tokens/methods/create/

# Reference release broker deployment boundary

This package is intentionally **not deployed by a GitHub Actions workflow**.

The broker is supposed to be an independent authorization domain that constrains GitHub. Giving the GitHub execution domain credentials that can rewrite the broker, its Durable Object state, its signer, or its policy would collapse that independence.

## Required independent bindings

Configure outside the GitHub execution trust domain:

- `BROKER_SIGNING_PRIVATE_JWK` — P-256 private signing JWK; secret/non-exported after provisioning.
- `AUTHORITY_PUBLIC_B64` — pinned public key for the private-authority grant signer.
- `ALLOWED_JOB_WORKFLOW_REF` — exact pinned reusable harness reference. Caller/project identity is not configured here; it is hashed into the independently signed one-time private grant.
- `ALLOWED_JOB_WORKFLOW_SHA` — exact reusable harness commit SHA.
- `MAX_ADMISSION_SECONDS` — <= 900; this is an admission window, not execution runtime.

## Administrative rule

A credential available to the GitHub workload must not have permission to:

- deploy or edit this Worker;
- modify the `GRANT_LEDGER` Durable Object binding/storage;
- replace `BROKER_SIGNING_PRIVATE_JWK`;
- change the authority public key;
- change the approved harness measurement;
- change the admission policy.

Ordinary application deployment tokens may continue to exist for unrelated Workers if they are technically scoped away from these broker resources.

## Rotation

Signer rotation is independently authorized:

1. generate new signer outside GitHub;
2. record/pin new public key in private authority;
3. update broker signer through independent administration;
4. prove both sides agree on the new `broker_key_id`;
5. retire old signer after outstanding grants expire.

A private grant is explicitly bound to the expected broker key ID, so substituting a different broker signer fails closed.

## Timing

The broker ticket expires at `admission_not_after`.

Once the private authority verifies the ticket and admits the workload, the ticket is consumed/dead. The admitted job uses the separate encrypted execution lease from the private job contract.

## Cloudflare resource scoping

Cloudflare now supports Developer Platform roles scoped to an **individual Worker**.

Use that to preserve the independent trust boundary without requiring a separate Cloudflare account:

- the GitHub CI token may retain Editor rights only to explicitly selected ordinary application Workers;
- the release broker Worker must be **excluded** from every GitHub-held mutable scope;
- GitHub may have at most Metadata Read-Only access to the broker if operationally useful; no Content Read-Only is required for normal execution;
- the broker's Durable Object inherits the broker Worker's permissions, so excluding the Worker from GitHub's Editor/Admin scopes also excludes mutation of its Durable Object through that token;
- rotate any existing account-wide Workers edit token after narrowing it, because historical broad tokens defeat the intended separation.

Broker deployment itself is performed from an independently authenticated operator/admin path or another non-GitHub authority.

## Network exposure

This broker has no business-facing purpose.

- `workers_dev = false`;
- `preview_urls = false`;
- attach only the intended neutral custom domain/route through the independent Cloudflare administration path;
- the release endpoint authenticates the caller with GitHub OIDC and fails closed without it;
- do not add a GitHub-stored Cloudflare Access service token as a prerequisite, because that would create another reusable credential in the domain being policed.

## One broker serves all consumers

Do not create a separate release broker or separate Cloudflare policy for each project.

The broker statically pins only the reusable security harness and its signing/authority roots. The independently signed private grant contains a SHA-256 digest of the expected caller OIDC identity (immutable repository/owner IDs, visibility, ref/event, run ID and attempt).

The broker recomputes that digest from the verified GitHub OIDC token and requires an exact match before consuming the grant.

Consequences:
- LPC, MM-IBKR, and future projects consume the same broker/protocol;
- a caller identity can change only through a new private grant, not by changing Cloudflare configuration;
- project names do not need to be embedded in broker policy;
- a stolen grant cannot be moved to a different repository/ref/run/attempt.

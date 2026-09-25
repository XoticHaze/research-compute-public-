# Reference release broker deployment boundary

This package is intentionally **not deployed by a GitHub Actions workflow**.

The broker is supposed to be an independent authorization domain that constrains GitHub. Giving the GitHub execution domain credentials that can rewrite the broker, its Durable Object state, its signer, or its policy would collapse that independence.

## Required independent bindings

Configure outside the GitHub execution trust domain:

- `BROKER_SIGNING_PRIVATE_JWK` — P-256 private signing JWK; secret/non-exported after provisioning.
- `AUTHORITY_PUBLIC_B64` — pinned public key for the private-authority grant signer.
- `ALLOWED_REPOSITORY_ID` — immutable GitHub repository numeric ID.
- `ALLOWED_REPOSITORY_OWNER_ID` — immutable GitHub owner numeric ID.
- `ALLOWED_JOB_WORKFLOW_REF` — exact pinned reusable harness reference.
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

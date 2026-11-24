# Scheduled Pi root release: reviewed candidate, disabled by default

Use only existing neutral Worker **research-compute-public**, account Shared Compute Neutral Authorization. No new Worker/token/DO. No GitHub Builds reconnection or GitHub-driven deployment of this key custodian.

The existing Access-authenticated owner routes stay unchanged. This candidate adds a Cloudflare-owned Cron Trigger handler (configure in the neutral dashboard, initially disabled by missing flag), not an HTTP signing route. The existing root Ed25519 domain and private Git queue stay unchanged. Protected status can recover the existing public PEM without generating a second key.

Independent administrator supplies `PI_OWNER_SCHEDULED_ROOT_PERMIT` on the protected Worker, not in Git:
```json
{"schema":"commandcenter.pi.scheduled_root_permit.v1","permit_id":"<32 lowercase hex>","source_sha":"<reviewed exact 40 hex CommandCenter source>","expected_release":"<verified Pi root generation>","not_before":"<UTC seconds>","expires_at":"<UTC seconds, max 24h>"}
```
Keep `PI_OWNER_SCHEDULED_ROOT_ENABLED` absent/off until exact neutral source, key, Access, queue credential and Pi root trust enrollment verified. Existing normal release/signer flags must also be enabled. Configure the existing Worker cron only after owner admission. This permit authorizes exactly one grant for the specified immutable source/predecessor, not arbitrary Git-controlled code or bot orders. One-use consumption and issuance share a DO transaction. Same-ID retry retrieves the identical stored grant; different IDs cannot reuse the permit. Existing publisher writes the signed grant before the executable request, respecting CAS. No standalone shell, Gateway restart, order authority or new account granted.

For recurring independent maintenance, use an admitted independent reviewed release admission producer to supply new exact permits (not arbitrary queue writer). This candidate does NOT provision such a producer, nor make new code root-trusted by mere Git write. Exact first seal remains an independent boundary; once admitted, dispatch/polling and receipt verification need no operator click. Source-only candidate, no deployment or key issuance claimed.

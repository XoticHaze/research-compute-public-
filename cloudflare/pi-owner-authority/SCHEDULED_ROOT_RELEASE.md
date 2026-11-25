# Persistent Pi root release admission

Reuse existing neutral Worker research-compute-public, owner Access, DO, private queue credential and Pi root key. No GitHub Builds reconnection, public-runner production key, new Worker or arbitrary Git-to-root authorization.

## One-time protected recovery

The CommandCenter installer deploys the persistent signer and scheduler directly; it does not install and later disarm a temporary Worker version. It verifies the existing root trust, installs the exact one-time manifest guard via existing owner sudo only if missing, publishes an inert proposal and uses direct authenticated owner Access to approve only that exact pinned package. The signer publishes the signature before the executable root request. The installer observes the same-ID signed grant and terminal receipt. After protected source/Access/runtime readback, the persistent signer is retained even if Pi completion is delayed or failed. Do not retry an uncertain request ID.

## Later independent issuer enrollment (no Cloudflare redeploy)

An independently operated review/permit issuer must hold its own separate Ed25519 private key and review exact source/artifact/predecessor. The admin may pin its public identity at initial deployment or enable `PI_OWNER_ISSUER_OWNER_ENROLL_ENABLED=1` without static pins. The existing direct owner Access page then admits the independently verified public SPKI and SHA-256 fingerprint in protected DO storage, after explicit custody confirmation. No Git proposal can enroll an issuer. Static pins and temporary bootstrap permits exclude browser enrollment. Active keys cannot be replaced without explicit fingerprint-bound revocation; revocation changes revision and stops further issuance, while a previously issued grant remains bounded by its original expiry. No private key is accepted by the signer API.

The fixed private Git file pi-node/root-release-permit.json carries the independently signed envelope, not the authorization key. The fixed proposal remains inert. Each permit binds exact request ID (including SHA-256 manifest digest), source SHA, expected Pi predecessor, and validity window. The envelope has exactly schema=commandcenter.pi.independent_release_permit.v1, permit (v2 exact permit), signature_b64 (Ed25519 signature over that schema followed by NUL, sorted compact permit JSON and LF).

Cron and DO validate static-pinned envelopes; for browser-enrolled keys, the DO verifies the stored pin and signature and rechecks its active revision atomically with single-use issuance. Same-ID recovery returns only the identical grant; distinct IDs cannot reuse a permit. Prior passed terminal and accepted predecessor are mandatory before scheduled dispatch. Missing issuer, missing signed permit, stale proposal or invalid signature produces no dispatch. Owner Access remains exceptional explicit approval, not the normal automated producer.

The independent issuer core and fixed publisher exist. Deploy them only in separately admitted protected custody. The reviewer input must be independently produced, never derived from Git proposal assertions. No new issuer can be claimed live from this source. A first signed root terminal plus a second no-Mac/no-operator independently admitted terminal are required for autonomous closure.

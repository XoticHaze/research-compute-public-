# IBKR Warm Read Gateway — 2026-09-17

## Purpose

Provide a reusable, private-by-construction read path from the accepted warm IBKR paper Gateway to authorized MM-IBKR consumers without distributing IBKR credentials or granting strategy/execution-policy authority to public compute.

The write path remains separate: selected-runtime paper submission must still enter through MM-IBKR's canonical submit/cancel/flatten authority and explicit paper-proof mode.

## Public workflow contract

Canonical workflow:

- `.github/workflows/ibkr-cloudflare-readonly-b1-r1.yml`
- authority ref: `ibkr-b1-authority-v1`
- default mode: `readonly`

Optional detailed read-return inputs:

- `symbols`: bounded comma-separated market symbols; default `AMAT,APH`
- `read_return_recipient_b64`: one-run X25519 public recipient
- `read_return_recipient_key_id`: SHA-256 fingerprint of that recipient

A detailed read return is admitted only when `mode=readonly` and both recipient fields are present and valid. The request is validated before the Fleet Authority Gateway environment is materialized.

The read request never enables a writable Gateway. `READ_ONLY_API=no` remains reachable only through explicit `paper_submit_proof` mode.

## Data returned privately

After the accepted post-auth pipeline succeeds, `scripts/ibkr_warm_read_return_v1.py` connects to the existing Gateway with `readonly=True` and collects:

- paper managed-account identity
- account summary fields
- positions and average cost
- open trades/orders and status
- broker time
- the existing post-auth handoff
- canonical forward bars for requested symbols

The snapshot explicitly reports:

- `order_submission=false`
- `global_cancel=false`
- `live_execution=false`

## Encryption and publication

Snapshot schema:

- `mmibkr.ibkr_warm_read_snapshot.v1`

Return envelope:

- `ibkr-warm-read-return-x25519-v1`
- X25519 one-run recipient
- HKDF-SHA256
- ChaCha20-Poly1305
- HKDF info domain: `mm-ibkr-warm-read-return-v1`
- authenticated data binds schema, run ID, authority, harness, and recipient fingerprint

Only ciphertext chunks plus the envelope are published under:

- `rendezvous/returns/<run_id>/...`

The public workflow does not publish the decrypted account/position/order snapshot. Temporary read-return material is removed during final cleanup.

## Authority boundary

The public read gateway is transport and broker-truth materialization only.

It does not own or infer:

- strategy intent
- entry/exit decisions
- side or quantity
- selected-runtime execution policy
- live-trading authority
- cancel/flatten policy

MM-IBKR remains the canonical strategy and execution-policy authority.

## Run identity

Private consumers are expected to bind workflow dispatch to all of:

- canonical authority ref `ibkr-b1-authority-v1`
- exact public authority head SHA resolved immediately before dispatch
- random one-run dispatch nonce
- exact nonce-bearing workflow display title
- numeric GitHub run ID
- one-run return-recipient fingerprint

The decrypted snapshot itself carries the GitHub run ID and exact public head SHA and must match the request before it is accepted.

## Validation evidence

The deterministic patch/validation run `35278207392` passed YAML validation and 22 focused warm-state/read-return tests with:

- `IBKR_BROKER_LOGIN_ATTEMPTED=0`
- `IBKR_BROKER_ORDER_ATTEMPTED=0`
- `IBKR_WARM_READ_GATEWAY_PATCH_VALID=1`

The exact validated workflow blob was then promoted to the production workflow path.

Canonical B1 validation run `35278346066` subsequently executed the promoted workflow's own `validate` job successfully. Its `broker-data-proof` job was skipped, so this acceptance validation performed no broker login and no order mutation.

## Consumer shape

An authorized private consumer should:

1. generate a one-run X25519 return keypair;
2. resolve the exact `ibkr-b1-authority-v1` head;
3. dispatch `readonly` with a random nonce, requested symbols, and the public recipient/fingerprint;
4. discover only the nonce/ref/head-correlated run;
5. fetch the run-scoped encrypted return chunks and envelope;
6. validate chunk paths/digests, recipient identity, run ID, and public head;
7. decrypt locally;
8. reject any snapshot that is not paper/read-only or advertises order/global-cancel/live authority.

This is the reusable account/market-data side of the IBKR Cloud route. The canonical selected-runtime paper execution route remains a separate explicit capability.

# IBKR Warm Paper-Proof Activation — 2026-09-17

## Authority

MM-IBKR remains the sole strategy, selected-runtime, sizing, and execution-policy authority. Public compute is transport/execution/evidence only.

## Activation boundary

The existing admitted workflow `.github/workflows/ibkr-cloudflare-readonly-b1-r1.yml` now supports two explicit workflow-dispatch modes:

- `readonly` — default; Gateway API remains read-only.
- `paper_submit_proof` — Gateway API is writable only for the run and the workflow still cannot submit until a run-bound encrypted MM-IBKR command capsule v2 is received and validated.

Push-triggered warm acceptance remains read-only.

A random `dispatch_nonce` is included in the workflow run name so a private producer can correlate its exact workflow-dispatch run without choosing the newest nearby run.

## Public activation runner

`scripts/ibkr_warm_selected_runtime_activation_v1.py`:

1. creates a one-run X25519 command recipient;
2. publishes that recipient to `rendezvous-exchange`;
3. waits for the run-bound encrypted command capsule;
4. validates/decrypts/materializes exact private MM-IBKR source + command;
5. launches the exact private MM-IBKR source head with natural owners disabled;
6. enables only canonical paper submit, exact cancel, and residual flatten route locks;
7. keeps `ENABLE_LIVE_TRADING=0` and global cancel disabled;
8. delegates submit/cancel/flatten through canonical MM-IBKR HTTP routes;
9. encrypts the proof receipt to the private producer’s one-run return recipient;
10. publishes ciphertext only and destroys private runtime material.

The activator contains no direct `ib_insync` order mutation client.

## Route locks in the isolated canonical runtime

Enabled:

- `STRATEGY_IBKR_PAPER_ORDER_SUBMIT_ENABLED_13Z53=1`
- `STRATEGY_IBKR_PAPER_CANCEL_ENABLED_13Z37=1`
- `STRATEGY_IBKR_PAPER_FLATTEN_ENABLED_13Z39=1`

Disabled:

- `ENABLE_LIVE_TRADING=0`
- `STRATEGY_IBKR_PAPER_GLOBAL_CANCEL_ENABLED_13Z37D=0`
- legacy submit toggles
- natural selected-runtime candidate owner
- futures auto owner
- unrelated-open-order override

Canonical submit acknowledgements and the MM-authorized order intent still come from the encrypted command payload; the public layer does not invent them.

## Validation

- activation runner focused hosted validation: run `35215313909` — PASS.
- admitted warm workflow non-broker validation after import fix: run `35215313924` — validate PASS, broker job SKIPPED.
- nonce-correlated workflow validation: run `35215591132` — validate PASS, broker job SKIPPED.

No broker login or order mutation was attempted by these validation runs.

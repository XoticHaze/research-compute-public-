# IBKR Cloud Execution & Warm-State Reuse Handoff

## Objective
Move every exchange-facing capability previously supplied by the MM-IBKR host onto hardened public compute with encrypted/private inputs, while preserving canonical MM-IBKR StrategySpec, selected-runtime, paper-submit, risk, and live-trading authorities.

## Exact authority baseline
- Repository: `XoticHaze/research-compute-public-`
- Authority branch used by the successful/failing proof pair: `ibkr-b1-authority-v1`
- Authority SHA: `2cd779dc56b06c382c6320466c580c22edf19730`
- Authority tree: `eba34e54c0476b0ba678249ee1067c5e007db277`
- Workflow: `.github/workflows/ibkr-cloudflare-readonly-b1-r1.yml`
- Workflow run: `35175232679`, run number 45

## Proven first-run capability
Attempt 1 established a clean authenticated paper Gateway session from ephemeral public compute without requiring IBKR Mobile approval. It proved:
- Cloudflare sealed credential delivery works.
- IBKR paper credentials are valid.
- Gateway can become API-ready from a fresh runner.
- `authenticated_session=true`.
- `paper_account_verified=true`.
- `read_only=true`.
- 1 managed account.
- 30 positions read.
- 0 open orders read.
- 74 account-summary fields read.
- AMAT and APH qualified.
- 384 historical bars fetched for each symbol, 768 normalized forward bars total.
- `consumer_ready=true`.
- An encrypted reusable Gateway/JTS state artifact was produced.

Credential correctness and basic unattended paper authentication are therefore not unresolved blockers.

## Attempt 2 result
Attempt 2 ran on a fresh runner and successfully obtained/decrypted/restored the prior encrypted JTS state (`IBKR_WARM_STATE_RESTORED=1`) but the restored Gateway did not become API-ready. The observed boundary was `pre_auth_or_unknown`; there was no credential rejection, explicit 2FA challenge, or wrong-server signal.

Interpret this as a warm-state lifecycle/startup-continuity defect until disproven, not as evidence that the Cloudflare credentials are invalid.

## Two confirmed workflow defects
### 1. False warm-session classification
The current workflow sets `mode=warm` whenever the API becomes reachable, even when `steps.restore.outputs.restored != '1'`, then prints:

`IBKR_OPERATOR_ACTION=NONE_WARM_SESSION_REUSED`

That made the successful cold/fresh bootstrap appear to be a warm reuse.

Required semantics:
- `IBKR_WARM_STATE_RESTORED`: prior state was restored into this run.
- `IBKR_WARM_REUSE_READY`: this run has produced/preserved state that can be reused by a later run.
- `IBKR_WARM_SESSION_REUSED`: restored state actually led to authenticated/API-ready continuation.
- A fresh successful login must instead report a fresh-session auth path.

Warm reuse must require at least: restored state + Gateway API ready + authenticated paper account verified + no interactive approval requirement.

### 2. Unsafe state-capture/shutdown ordering
At authority SHA `2cd779dc...`, the workflow archives/seals the mounted JTS state while Gateway is still running. Only afterward, in the final cleanup step, it executes `docker stop --time 10` and force-removes the container/volume.

Repair direction:
1. Complete post-auth broker/data handoff.
2. Gracefully stop Gateway with sufficient shutdown grace (current controller guidance established in this lane: 90 seconds).
3. Verify container stopped cleanly.
4. Archive/seal JTS state only after the clean stop.
5. Publish encrypted state.
6. Destroy runtime material.

Do not destroy or replace the known-good `2cd779dc...` authority branch while testing this repair. Cloudflare provenance/allowlisting must be intentionally advanced to any new workflow SHA before a broker run can consume it.

## Cloud exchange-capability matrix
### Proven
- Sealed private credential retrieval.
- Fresh unattended paper Gateway authentication.
- Read-only IB API connectivity.
- Managed-account retrieval.
- Portfolio/position retrieval.
- Open-order retrieval.
- Account-summary retrieval.
- Contract qualification.
- Historical-bar retrieval and normalization.
- Canonical post-auth/forward-data handoff artifact.
- Encrypted JTS state production.
- Encrypted JTS state decryption/restoration into a fresh runner.

### Not yet accepted end to end
- Restored warm state -> API-ready authenticated continuation.
- Cloud paper order submit through MM-IBKR's canonical submit authority.
- Cloud cancel/replace through canonical authority.
- Fill/execution retrieval and reconciliation into canonical trade evidence.
- Position/order reconciliation after cloud paper actions.
- Survivor-forward decision -> canonical paper action -> attributable completed-trade evidence.
- Controlled transition from read-only broker proof to narrowly scoped paper-submit authority.

## Survivor-forward objective
The remaining high-value vertical slice is:

`authenticated broker truth -> survivor/model decision -> canonical MM-IBKR paper submit/cancel/reconcile -> completed attributable trade evidence -> Strategy Intelligence / forward-performance consumer`

The existing encrypted survivor acceptance capsule only proves the verifier/admission path. It does not by itself retrieve broker truth or mutate broker trading authority, so do not call that an end-to-end survivor forward test.

## Authority boundaries / non-negotiables
- Cloud is an execution surface, not a second strategy/runtime/trading authority.
- StrategySpec and selected-runtime identity remain canonical MM-IBKR authorities.
- Paper orders must remain gated by the existing `selected_runtime.execution_policy.paper_submit_enabled` contract.
- Live trading must remain separately gated by `ENABLE_LIVE_TRADING` and is out of scope for initial cloud paper-forward acceptance.
- Private broker credentials/account inputs remain sealed/encrypted and must not be published in public artifacts/logs.
- Fail closed on authority/provenance mismatch, corrupted warm state, wrong account, or live-mode ambiguity.
- Do not report `WARM_SESSION_REUSED` unless reuse actually occurred.

## Next executable sequence
1. Patch the B1 workflow on a side branch: truthful auth-path classifier + graceful-stop-before-snapshot + 90-second stop grace.
2. Add broker-free contract tests for fresh-vs-restored classifier behavior and lifecycle ordering where feasible.
3. Advance Cloudflare allowed workflow SHA intentionally to the repair commit, then rerun cold/fresh proof if required by authority contract.
4. Run cross-runner warm restoration and require authenticated/API-ready continuation.
5. In `XoticHaze/mm-IBKR`, locate and record exact canonical paper submit/cancel/reconcile functions and selected-runtime gates.
6. Expose those mechanics to the hardened public compute worker without duplicating decision authority.
7. Start with minimal paper action scope and mandatory post-action order/position/fill reconciliation.
8. Feed attributable results back into the existing Strategy Intelligence / survivor-forward evidence path.

## Agent pickup rule
Do not reconstruct this lane from chat summaries or compacted poller output if repository truth is available. Pin the repository/branch/SHA first, fetch the exact workflow/source files through the GitHub connector, run the cheapest decisive test, implement the consequence, and update this handoff or its successor with commit/run evidence.

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

## Fleet-authority steady-state contract
PR #1433 merged to `main` as `7b5fc27b42202bbc9061c67ca545fb74d85b1317` and removes the moving workflow-SHA authorization ceremony from the Cloudflare Worker.

The Worker now trusts the stable GitHub OIDC workload identity while retaining fail-closed signature/time validation and stable defense-in-depth claims:
- exact repository
- public repository visibility
- GitHub-hosted runner
- exact authority branch/ref
- exact canonical workflow ref
- admitted `push` / `workflow_dispatch` event
- matching `run_id`

`workflow_sha` remains provenance metadata only. Normal commits on the admitted authority branch must not require a Cloudflare dashboard edit, Wrangler SHA update, health-contract update, or one-time phrase. `/healthz` is liveness only.

The warm-repair workflow therefore removes the old SHA/config health preflight and goes directly from broker-free validation to the one-run sealed envelope request.

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

## Current MM-IBKR canonical paper-execution binding
Grounded against `XoticHaze/mm-IBKR` `main` at commit `dbbae1be58e45e3e89cc0ec56c8b4c1b043a8c41`, tree `d9d1adf33510c1ffcc3bee9cb2b5f48a94792059`.

### Broker/session owner
- `main.py` owns the shared `IB()` session.
- The internal control runtime reuses that session rather than creating a second broker connection.
- `controller.selected_runtime_submit_callable_14th31cx` is the selected-runtime execution seam used by natural candidate materialization.

### Canonical primary submit
- Route: `POST /strategy/ibkr-paper-order-submit`
- Handler: `strategy_ibkr_paper_order_submit`
- Contract: `ibkr_paper_order_submit_13z53`
- Materializer/qualification chain: `_ibkr_order_13z50_materialize` -> `_ibkr_order_13z51_req_contract_details` -> `_ibkr_order_13z52_order_type_support` -> `_ibkr_order_13z62_execution_policy`.
- Selected-runtime authority: `_selected_runtime_execution_authority_14th31cx(payload, symbol=...)`.
- Submit is blocked unless that authority reports `paper_submit_enabled=true`.
- Selected runtime `execution_policy` also controls market orders, inactive-session orders, shorts, and sizing/limits.
- `_ibkr_order_14th31lg_resolve_selected_runtime_sizing` resolves authoritative paper quantity/current-position consequences before submit.
- A single DU paper account is required.
- Duplicate/open-order state and orderRef conflicts are blocked before placement.
- Contract qualification, broker order-type support, route/session policy, limit-price/minTick policy, and authoritative broker-state preflight all fail closed.
- Live authority remains independently exposed as `ENABLE_LIVE_TRADING`; do not collapse that into paper-submit authority.

### Open-order truth and duplicate guard
- Route: `GET /strategy/ibkr-paper-open-orders`.
- `_ibkr_submit_13z36_open_order_rows()` joins `ib.openTrades()` and `ib.openOrders()` into canonical open-order rows with orderId, permId, clientId, orderRef, action, status, filled, remaining, account and contract identity.
- `_ibkr_submit_13z36_build_open_order_guard()` blocks duplicate `orderRef`, exact duplicate open orders, and unresolved same-symbol/account/action broker orders before `placeOrder`.

### Cancel
- Routes: `POST /strategy/ibkr-paper-cancel-preview` and `POST /strategy/ibkr-paper-cancel-submit`.
- Handler core: `_ibkr_cancel_13z37_result(payload, execute=...)`.
- Submit requires a single DU paper account, `STRATEGY_IBKR_PAPER_CANCEL_ENABLED_13Z37`, operator approval, and exact `IBKR_PAPER_CANCEL_ACK_13Z37` acknowledgement.
- Cancel uses the existing `ib.openTrades()` order object and `ib.cancelOrder()`.
- It then re-reads open-order state and fails reconciliation if requested orders remain open or a clientId mismatch is suspected.
- Global cancel also has dedicated preview/submit routes with exact expected-order-set matching before `reqGlobalCancel`.

### Flatten
- Preview route: `POST /strategy/ibkr-paper-flatten-preview-suite`.
- Current flatten chain derives action/quantity from actual `ib.positions()` plus portfolio state and blocks when unresolved orders exist for the symbol or the session is not a single DU paper account.
- The submit/lifecycle artifacts live under `strategy_ibkr_paper_flatten_submit_suite_13z39`; cloud integration should reuse this executor contract rather than synthesize close orders independently.

### Reconcile / lifecycle evidence
- Route: `POST /strategy/ibkr-paper-order-reconcile`.
- Contract: `ibkr_paper_submitted_open_reconcile_13z60`.
- Current lifecycle code joins exact order identity, broker status, openTrades/openOrders, fills/remaining, and before/after position snapshots.
- Canonical lifecycle schema: `broker_lifecycle_13z58.v1`.
- It records lifecycle state, fill mode, failure mode, avg/last fill price, permId, position before/after/delta, whether an open order remains, retry policy, and whether a confirmed BUY makes a subsequent SELL safe.
- `POST /strategy/ibkr-paper-broker-lifecycle-artifacts` exposes local lifecycle artifacts and optional explicit live broker snapshots without mutating orders.

### Cloud integration consequence
Do not build a second cloud-native trader. The encrypted public-compute worker should transport a narrowly scoped canonical request and authoritative selected-runtime context, then execute the same semantic contract above against its authenticated paper `IB()` session. The minimum accepted paper-forward proof must preserve all fail-closed guards and return enough broker identity/lifecycle evidence to be consumed by MM-IBKR Strategy Intelligence.

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
1. **DONE:** Patch the B1 workflow on a side branch with truthful auth-path classification, graceful-stop-before-snapshot, and 90-second stop grace.
2. **DONE:** Add broker-free contract tests for fresh-vs-restored classifier behavior, lifecycle ordering, and absence of mutable SHA/health preflight.
3. **DONE:** Replace mutable Cloudflare SHA authorization with stable GitHub OIDC workload identity in PR #1433 / `7b5fc27b...`.
4. Merge the warm repair into `ibkr-b1-authority-v1` and run the canonical broker proof. A successful one-run sealed-envelope request is also the live proof that the new Worker deployment is active.
5. Run a second fresh-runner proof and require restored state -> API-ready authenticated paper continuation before reporting warm-session reuse accepted.
6. **DONE:** Ground current `XoticHaze/mm-IBKR` canonical submit/cancel/reconcile functions and selected-runtime gates at `dbbae1be58e45e3e89cc0ec56c8b4c1b043a8c41`.
7. Expose those mechanics to the hardened public compute worker without duplicating decision authority.
8. Start with minimal paper action scope and mandatory post-action order/position/fill reconciliation.
9. Feed attributable results back into the existing Strategy Intelligence / survivor-forward evidence path.

## Agent pickup rule
Do not reconstruct this lane from chat summaries or compacted poller output if repository truth is available. Pin the repository/branch/SHA first, fetch the exact workflow/source files through the GitHub connector, run the cheapest decisive test, implement the consequence, and update this handoff or its successor with commit/run evidence.

# MM-IBKR Canonical Runtime ABI v1

Parent: public issue #1614. Runtime substrate: #1617.

## Purpose

Provide one portable, fail-closed execution ABI for established MM-IBKR research capabilities. The same request/receipt semantics are intended for public encrypted compute, local Docker, a workstation/homelab, or a later compute backend.

The dispatcher is **not** an arbitrary command runner. A request selects only a registered `capability_id`; module/path/callable identity is fixed by the public capability registry and independently bound to an exact Git blob SHA from the pinned private source tree.

## Integration stack

The reviewed stack order is:

1. canonical dispatcher/plan ABI (#1620)
2. claim leases + budget-aware session runtime (#1643)
3. governed research capabilities (#1624)

Capability adapters inherit the same claim/cache/session substrate. Do not merge #1624 as a sibling dispatcher fork or drop the lease/session semantics when resolving the stack.

## Implemented capability bindings

The portable ABI currently carries these research-only bindings:

| Capability | Canonical private owner | Portable contract |
| --- | --- | --- |
| `STRATEGY_SPEC_VALIDATE` | `autotuner_strategy_bridge.normalize_strategy_spec` | normalize and digest one StrategySpec |
| `CRW_BACKTEST` | `scripts.operator.crw_backtest_summary_13z.run_backtest` | execute canonical CRW replay over exact governed datasets |
| `AUTOTUNER_PARAMETER_CONSUMPTION` | `autotuner_parameter_consumption.parameter_schema_for_tuning` | derive the searchable CRW parameter surface from the pinned private strategy schema |
| `AUTOTUNER_CANDIDATE_GENERATE` | `autotuner_strategy_bridge.candidate_mutations` | generate a bounded mutation set only after the canonical consumption gate |
| `CANONICAL_DATA_MATERIALIZE` | `data_manager.DataManager.ingest_external_stock_source_bars` | normalize/dedupe/resample governed stock bars into canonical raw/features/sidecar artifacts without provider acquisition |
| `FEATURE_CONTRACT_VALIDATE` | `feature_contract.read_feature_artifact_sidecar` | verify feature artifact bytes, lineage manifest hash, semantic hash, causality and portable feature meaning |
| `STRATEGY_PREVIEW` | `strategies.create` + `strategies.event_bus.build_strategy_definition` | deterministic read-only strategy evaluation over an exact canonical feature artifact |

CRW backtest callers cannot supply absolute source paths. The request carries per-symbol relative paths, byte counts, and SHA-256 identities under a governed `--input-root`; the dispatcher verifies them and injects canonical `_verified_source_paths` only after admission.

AutoTuner callers cannot supply their own parameter schema. The dispatcher derives `CrwScoreMultiModeStrategy.parameter_schema()` from the same pinned private source, applies the canonical consumption gate, and records the relevant private Git blob identities in the receipt.

`CANONICAL_DATA_MATERIALIZE` deliberately excludes provider acquisition. IBKR/provider-bearing fetch surfaces remain dedicated read-only data authorities and feed governed snapshots into the portable materializer.

`FEATURE_CONTRACT_VALIDATE` accepts either a governed external artifact under `--input-root` or a prior canonical receipt artifact addressed by `job_fingerprint + relative_path + SHA-256`. Absolute host paths are never part of the request ABI.

`STRATEGY_PREVIEW` consumes the same governed feature-artifact reference. It owns StrategySpec normalization, feature manifest compatibility, deterministic/as-of row selection, strategy registry evaluation, required/missing indicator evidence, Builder-condition evidence, and the raw research signal. Live/paper positions, sizing, risk/order math, broker-shaped previews, buying-power/margin, order intent, route readiness, and submit authority remain operator/runtime overlays outside the generic executor.

AutoTuner campaign/primary validation, Model Lab, News, Options, and report materialization remain dependency-ordered additions rather than one-off workflow families.

## Request contract

Schema: `mmibkr.canonical_workload_request.v1`

A request binds:

- stable `job_id`
- allowlisted `capability_id`
- exact private MM-IBKR repository, commit, and source archive SHA-256
- exact canonical entrypoint path/module/callable and Git blob SHA-1
- bounded capability arguments
- resource bounds
- `research_only` authority
- explicit false assertions for broker submit/cancel/flatten, StrategySpec write, runtime activation, promotion mutation, and live trading

The private-source materialization receipt is supplied separately and must match the request source identity while asserting no broker credentials or paper/live authority were materialized.

## Plan contract

Schema: `mmibkr.canonical_workload_plan.v1`

A plan contains up to 256 jobs, explicit `depends_on` edges, and a bounded `max_parallel` value. Structural cycles and unknown dependencies fail before work begins.

Independent jobs run in the same ready wave. Downstream jobs become eligible only after all dependencies complete or are reused from a valid content-addressed receipt.

## Cache / claim behavior

When `--receipt-dir` is supplied:

1. the normalized request is content-hashed;
2. an exact matching completed receipt is reused;
3. otherwise an exclusive claim file is created;
4. the canonical capability executes;
5. the receipt is atomically published;
6. the claim is removed.

Claim handling now uses explicit leases and heartbeat ownership from #1643. Active duplicates fail closed; stale claims are archived/recovered; malformed or foreign claims are rejected; a result is published only while the worker still owns the claim. Content-addressed data-materialization cache hits additionally re-verify every persisted artifact byte count and SHA-256 before reuse.

## CLI

Standalone:

```text
python scripts/mmibkr_canonical_workload_dispatch_v1.py run \
  --request request.json \
  --source-root /private/mm-source \
  --source-receipt mmibkr-private-source.json \
  --input-root /governed/input-root \
  --receipt-dir runtime-state
```

Composed plan:

```text
python scripts/mmibkr_canonical_workload_dispatch_v1.py plan-run \
  --plan plan.json \
  --source-root /private/mm-source \
  --source-receipt mmibkr-private-source.json \
  --input-root /governed/input-root \
  --receipt-dir runtime-state
```

## Next dependency-ordered additions

1. consume #1607 and #1549 through the generalized `CRW_BACKTEST` binding as regression/acceptance fixtures;
2. consume #1607 and #1549 as generalized `CRW_BACKTEST` acceptance plans rather than fixed family-specific execution paths;
3. extend `CANONICAL_DATA_MATERIALIZE` to the dedicated futures roll/stitch producer contract without moving broker/provider credentials into the research executor;
4. add a generic registry-backtest adapter so CRW remains the first proven fixture rather than the permanent execution model;
5. AutoTuner campaign + primary validation on top of the admitted parameter/candidate routes;
6. Model Lab first consumer, orchestration, and comparison validation;
7. deterministic News and Options intelligence adapters from #1618;
8. reproducible report/render artifacts and clean-checkout Docker/bootstrap/doctor smoke.

Cloud transports remain replaceable adapters. Broker/runtime/live authorities remain separate.

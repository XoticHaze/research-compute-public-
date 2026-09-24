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
| `REGISTRY_BACKTEST` | `strategy_backtest_registry.run_strategy_backtest` | execute one normalized StrategySpec over one exact governed evaluation dataset across registered strategy families, preserving the primary CRW runner |
| `AUTOTUNER_PARAMETER_CONSUMPTION` | `autotuner_parameter_consumption.parameter_schema_for_tuning` | derive the searchable CRW parameter surface from the pinned private strategy schema |
| `AUTOTUNER_CANDIDATE_GENERATE` | `autotuner_strategy_bridge.candidate_mutations` | generate a bounded mutation set only after the canonical consumption gate |
| `CANONICAL_DATA_MATERIALIZE` | `data_manager.DataManager.ingest_external_stock_source_bars` | normalize governed stock bars into canonical raw/features/sidecars without provider acquisition |
| `FEATURE_CONTRACT_VALIDATE` | `feature_contract.read_feature_artifact_sidecar` | verify exact feature artifact/sidecar lineage and semantic identity |
| `STRATEGY_PREVIEW` | `strategies.create` + registry/Builder contracts | evaluate one deterministic read-only strategy preview from an exact canonical feature artifact |
| `AUTOTUNER_CAMPAIGN` | `autotuner_campaign_runner.run_campaign_iteration` | run bounded research-only candidate campaign iteration |
| `AUTOTUNER_PRIMARY_VALIDATION` | `autotuner_primary_validation_runner.execute_primary_validation` | execute bounded primary walk-forward validation without promotion authority |
| `MODEL_LAB_FIRST_CONSUMER` | `scripts.operator.model_lab_xgboost_first_consumer.execute` | train/evaluate the canonical first predictive consumer while preserving the economic-evidence gap |
| `MODEL_LAB_COMPARE_VALIDATE` | `model_lab_comparison_matrix.align_training_matrices_for_comparison` | align frozen matrices and apply leakage-safe comparison validation |
| `NEWS_REPLAY_ANALYZE` | `news_engine.NewsEngine` | replay a governed article corpus through deterministic canonical matching/scoring with network + LLM acquisition disabled |
| `OPTIONS_SNAPSHOT_ANALYZE` | `options_scanner.OptionsScanner` pure IV/Black-Scholes helpers | analyze an exact captured option snapshot at an explicit as-of time without chain/quote acquisition |

`REGISTRY_BACKTEST` is the generalized arena surface for registry-backed strategy families. Family differences belong in `StrategySpec`; do not add family-specific backtest capability IDs. `CRW_BACKTEST` remains the proven compatibility/acceptance fixture and full CRW evidence route.

CRW backtest callers cannot supply absolute source paths. The request carries per-symbol relative paths, byte counts, and SHA-256 identities under a governed `--input-root`; the dispatcher verifies them and injects canonical `_verified_source_paths` only after admission.

AutoTuner callers cannot supply their own parameter schema. The dispatcher derives `CrwScoreMultiModeStrategy.parameter_schema()` from the same pinned private source, applies the canonical consumption gate, and records the relevant private Git blob identities in the receipt.

Data materialization, feature/preview, AutoTuner campaign/validation, and the portable Model Lab research consumers are now carried by the same dispatcher/session substrate. Status-owned Model Lab process launch/cancel/list remains intentionally outside the generic executor. News, Options, and later intelligence/report consumers remain dependency-ordered additions rather than one-off workflow families.

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

This first slice deliberately does **not** guess that an existing claim is stale. Stale-claim timeout/lease recovery belongs to the next queue/checkpoint increment so recovery semantics can be explicit and testable.

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

1. use the admitted G05/G06/G07 chain as the portable data -> feature lineage -> preview -> full CRW evidence substrate;
2. consume #1607 and #1549 as ordinary composed `CRW_BACKTEST` research jobs rather than one-off execution harnesses;
3. extend the admitted `NEWS_REPLAY_ANALYZE` deterministic replay core into no-lookahead News feature/report consumers; keep provider acquisition separate;
4. extend the admitted `OPTIONS_SNAPSHOT_ANALYZE` pure-analysis core into operator/report consumers while keeping chain/quote acquisition separate;
5. build later G11/G13 intelligence/report consumers on canonical immutable receipts;
6. keep status-owned operator/process orchestration and all broker/runtime/live authorities outside the generic research executor.

Cloud transports remain replaceable adapters. Broker/runtime/live authorities remain separate.

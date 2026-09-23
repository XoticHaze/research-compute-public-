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
| `CANONICAL_DATA_MATERIALIZE` | `scripts.operator.canonical_data_materialize_v1.materialize_snapshot` | materialize a hash-bound governed snapshot through existing DataManager/FuturesManager owners |

CRW backtest callers cannot supply absolute source paths. The request carries per-symbol relative paths, byte counts, and SHA-256 identities under a governed `--input-root`; the dispatcher verifies them and injects canonical `_verified_source_paths` only after admission.

AutoTuner callers cannot supply their own parameter schema. The dispatcher derives `CrwScoreMultiModeStrategy.parameter_schema()` from the same pinned private source, applies the canonical consumption gate, and records the relevant private Git blob identities in the receipt.

Canonical data materialization is offline by design: provider acquisition stays outside the generic executor. The request supplies one governed snapshot under `--input-root`, bound by relative path, bytes, and SHA-256. The private owner delegates to existing DataManager/FuturesManager external-ingest methods. Output is staged, verified file-by-file, then promoted under the normalized job fingerprint. The public receipt exposes counts, hashes, and an opaque artifact reference rather than market values or private filesystem paths.

Data materialization, feature/preview, campaign validation, Model Lab, News, and Options remain dependency-ordered additions rather than one-off workflow families.

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

1. consume #1607 and #1549 through the generalized `CRW_BACKTEST` binding as regression/acceptance fixtures;
2. governed data materialization and `FEATURE_CONTRACT_VALIDATE` / `STRATEGY_PREVIEW`;
3. AutoTuner campaign + primary validation on top of the admitted parameter/candidate routes;
4. Model Lab first consumer, orchestration, and comparison validation;
5. deterministic News and Options intelligence adapters from #1618;
6. explicit claim leases/checkpoints and the budget-aware worker loop from #1617.

Cloud transports remain replaceable adapters. Broker/runtime/live authorities remain separate.

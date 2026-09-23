# MM-IBKR Canonical Runtime ABI v1

Parent: public issue #1614. Runtime substrate: #1617.

## Purpose

Provide one portable, fail-closed execution ABI for established MM-IBKR research capabilities. The same request/receipt semantics are intended for public encrypted compute, local Docker, a workstation/homelab, or a later compute backend.

The dispatcher is **not** an arbitrary command runner. A request selects only a registered `capability_id`; module/path/callable identity is fixed by the public capability registry and independently bound to an exact Git blob SHA from the pinned private source tree.

## Initial capability

`STRATEGY_SPEC_VALIDATE` binds to:

- path: `autotuner_strategy_bridge.py`
- module: `autotuner_strategy_bridge`
- callable: `normalize_strategy_spec`

The first slice intentionally proves the ABI before adding CRW backtest, data materialization, AutoTuner, Model Lab, News, or Options adapters.

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
  --receipt-dir runtime-state
```

Composed plan:

```text
python scripts/mmibkr_canonical_workload_dispatch_v1.py plan-run \
  --plan plan.json \
  --source-root /private/mm-source \
  --source-receipt mmibkr-private-source.json \
  --receipt-dir runtime-state
```

## Next dependency-ordered additions

1. `CRW_BACKTEST`, with #1607 and #1549 as real acceptance consumers.
2. governed data input adapters and `CANONICAL_DATA_MATERIALIZE`.
3. feature validation / strategy preview.
4. AutoTuner campaign/validation.
5. Model Lab.
6. deterministic News and Options intelligence adapters.
7. explicit claim leases/checkpoints and budget-aware worker loop.

Cloud transports remain replaceable adapters. Broker/runtime/live authorities remain separate.

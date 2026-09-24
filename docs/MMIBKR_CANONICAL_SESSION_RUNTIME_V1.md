# MM-IBKR Canonical Session Runtime v1

Parent: public issue #1614. Runtime substrate: #1617. Implementation: draft PR #1643 stacked on #1620.

## Purpose

The canonical session runtime turns an allocated compute window into a bounded queue of reusable MM-IBKR research jobs.

It is intentionally not one five-hour monolithic workflow. Each job remains an ordinary allowlisted canonical capability request. The session runner only decides which dependency-ready jobs can safely start inside the remaining budget, runs independent work in bounded parallel waves, checkpoints progress, and reuses canonical receipts.

The same session manifest is intended to run on GitHub-hosted public encrypted compute today and later from the documented local/Docker runtime without changing scientific capability semantics.

## Execution layers

1. Direct capability: execute one allowlisted request with `mmibkr_canonical_workload_dispatch_v1.py run`.
2. Dependency plan: execute a fixed DAG with `plan-run`.
3. Budget session: execute eligible jobs by priority until the declared compute budget is exhausted.

The session layer composes the dispatcher. It does not clone capability logic.

## Session contract

Schema: `mmibkr.canonical_session.v1`

Top-level fields:
- `session_id`: stable identity for one compute allocation.
- `budget_seconds`: total wall-clock allocation, bounded to 1..18000 seconds.
- `reserve_seconds`: protected shutdown/checkpoint reserve.
- `max_parallel`: maximum concurrent ready jobs, bounded to 1..8.
- `jobs`: up to 256 canonical requests.

Each job declares `job_id`, integer `priority`, explicit `depends_on` edges, and the ordinary canonical `request`.

Scheduling is deterministic: dependencies complete first; higher priority runs first; ties prefer smaller declared `max_wall_seconds`; final tie-break is `job_id`; work that cannot fit inside remaining budget minus reserve is deferred without starting.

## Five-hour compute block

Five hours is exactly 18000 seconds.

Example session header:

```json
{
  "schema": "mmibkr.canonical_session.v1",
  "session_id": "overnight-research-20260923-a",
  "budget_seconds": 18000,
  "reserve_seconds": 120,
  "max_parallel": 4,
  "jobs": []
}
```

The runtime does not hard-code what valuable means. Priority belongs in the manifest so policy can evolve without forking the executor.

Once corresponding capabilities are admitted, a reasonable policy is: 100 missing/stale canonical data, 90 required feature/lineage validation, 80 News/Options deterministic intelligence, 70 backtests/candidate evaluations, 60 AutoTuner/Model Lab comparisons, 50 report/render regeneration, lower for opportunistic refreshes.

Dependencies still outrank priority. A high-priority consumer cannot run until declared producer artifacts exist.

## Claims, leases, and restart safety

PR #1643 adds an explicit claim schema, heartbeat-backed active leases, active-claim duplicate rejection, stale claim archival/recovery, malformed/foreign claim rejection, and result publication only while the worker still owns the claim.

If a session process stops, the checkpoint remains under the receipt directory. Re-running the same `session_id` with the same session fingerprint preserves completed/cached state. Reusing a session ID for a different manifest fails closed.

## External/private-input dependencies

A canonical session job may declare one optional `external_artifact_dependency` when the job cannot start until an artifact is produced outside the in-session DAG, such as an already-authorized encrypted private-input producer.

The declaration is attribution, not producer orchestration:

```json
{
  "external_artifact_dependency": {
    "scope": "input_root",
    "relative_path": "incoming/private-input.bin",
    "sha256": "<exact artifact sha256>",
    "bytes": 12345,
    "producer": {
      "mechanism": "source_exchange",
      "identity": "mmibkr-private-input-producer",
      "trigger": "rendezvous/fire/mmibkr-private-input-r1"
    }
  }
}
```

The session runner performs no network fetch and fires no producer. Before launching the canonical dispatcher it checks only the governed `input_root` for the declared bytes.

- absent artifact -> job state `awaiting_external_artifact`; producer mechanism/identity/trigger remain visible in the sanitized session receipt;
- present artifact with wrong byte count or SHA-256 -> fail closed;
- exact artifact -> the unchanged canonical request is dispatched;
- downstream jobs remain dependency-blocked until the consumer actually completes;
- independent jobs remain eligible to run.

A session that has only unresolved external inputs exits successfully with overall status `awaiting_external_artifact` rather than pretending the canonical consumer executed. Re-running the same immutable session after the exact artifact arrives resumes completed/cached work and gives the newly-unblocked work a fresh compute budget window, so external waiting time is not charged as research compute.

This state does not grant source-vault/source-exchange authority, invent a producer, or imply that a missing artifact is a compute, dispatcher, backtester, or MM-IBKR semantic failure.

## Per-job wall enforcement

The session runner executes each job in a subprocess and applies the request's `resources.max_wall_seconds` as a hard timeout. Timeout/error receipts expose a sanitized failure class and digest, not raw dispatcher stderr.

## Terminal invocation

```text
python scripts/mmibkr_canonical_session_runner_v1.py \
  --session session.json \
  --source-root /private/mm-source \
  --source-receipt mmibkr-private-source.json \
  --receipt-dir runtime-state
```

When a capability consumes governed datasets, the integrated runtime also passes `--input-root /governed/input-root`.

## Portability boundary

The session runtime owns scheduling, receipts, checkpoints, leases, and budget admission. It does not own GitHub Actions, Cloudflare, encrypted transport, source-vault implementation, broker credentials, selected-runtime ownership, StrategySpec mutation, promotion decisions, or paper/live order authority.

## Current capability status

- `STRATEGY_SPEC_VALIDATE` is implemented in #1620.
- `CRW_BACKTEST`, `AUTOTUNER_PARAMETER_CONSUMPTION`, and `AUTOTUNER_CANDIDATE_GENERATE` are implemented in stacked #1624.
- canonical data materialization, preview/feature validation, AutoTuner campaign/primary validation, Model Lab, News, Options intelligence, and report generation remain follow-on capabilities.

The scheduler is deliberately generic so those capabilities can be added without creating another orchestration stack.

## Remaining portable-bootstrap gap

G16 is not closed until the repository also provides canonical Docker/Compose startup, doctor/health command, bootstrap/materialization command, smoke session, local artifact/render paths, and a README path from clean checkout to the same capability/session receipts used in cloud.

That bootstrap should consume this runtime rather than replace it.

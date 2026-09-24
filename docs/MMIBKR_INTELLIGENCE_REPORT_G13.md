# MM-IBKR G13 Canonical Intelligence Report

## Purpose

G13 turns already-sanitized canonical research receipts into a human-readable intelligence artifact.

It is a **public receipt consumer**, not another private MM-IBKR executor.

The materializer never loads private source bytes, acquires provider data, executes a strategy, mutates StrategySpec/runtime/promotion state, or carries broker/live authority.

## Inputs

The materializer consumes:

1. a completed `mmibkr.canonical_workload_plan_receipt.v1`;
2. the exact canonical job receipts referenced by that plan;
3. the exact content-addressed News/Options evidence artifacts referenced by those job receipts;
4. optionally, a separately hash-bound designated-LLM sidecar.

The plan receipt must live under the canonical receipt directory as:

`plan-<plan_id>.json`

Every completed/cached plan job is rebound to:

- exact job fingerprint;
- canonical receipt SHA-256 recorded by the plan;
- exact receipt file bytes;
- result SHA-256;
- MM-IBKR private source commit;
- private source archive SHA-256;
- governed dataset identity when present;
- canonical private dependency Git blobs when present.

Any drift fails closed.

## Deterministic News section

For `NEWS_REPLAY_ANALYZE`, G13 verifies the canonical four-artifact set and renders:

- symbol;
- source;
- publication time;
- title;
- match method;
- relevance class;
- match confidence;
- deterministic sentiment;
- deterministic impact;
- deterministic confidence;
- explicit reason the article is associated with the symbol;
- themes;
- per-symbol scorecards.

Provider/RSS acquisition and LLM enrichment must remain false in the underlying deterministic News receipt.

## Deterministic Options section

For `OPTIONS_SNAPSHOT_ANALYZE`, G13 verifies the canonical analytics/summary artifacts and renders:

- snapshot truth state;
- explicit empty/unavailable reason;
- capture source/time;
- as-of time;
- expiry;
- strike;
- call/put right;
- selected option price basis;
- volume;
- notional USD;
- underlying price;
- moneyness;
- calculated IV;
- Delta/Gamma/Vega/Theta;
- per-row unavailable reason.

The report preserves `current-live`, `watch-only-last-known`, `watch-only-no-history`, and `no-snapshot` truth instead of flattening unavailable data to zero.

IBKR/Alpaca/network acquisition must remain false in the underlying Options receipt.

## Designated LLM sidecar

Generative enrichment is **not part of the deterministic report body**.

Optional sidecar schema:

`mmibkr.intelligence_report_llm_sidecar.v1`

Required fields:

- `deterministic_report_sha256`;
- `provider`;
- `model`;
- `generated_at`;
- bounded text-only `sections`.

The caller must also provide the expected SHA-256 of the sidecar file.

The sidecar is accepted only when:

1. its exact file SHA-256 matches the supplied digest;
2. its `deterministic_report_sha256` matches the exact deterministic JSON report bytes;
3. its field set is exact;
4. narrative sections remain bounded plain text.

LLM text is rendered in a visibly separate section and HTML-escaped. It cannot overwrite deterministic News/Options fields.

## Outputs

The output directory contains:

- `intelligence_report.json` — deterministic canonical report;
- `intelligence_report.html` — human-readable render;
- `intelligence_report_materialization.json` — output hashes, LLM-sidecar disposition, and authority assertions.

The deterministic JSON report identity is the SHA-256 of its exact canonical file bytes.

## CLI

```text
python scripts/mmibkr_intelligence_report_materialize_v1.py \
  --plan-receipt runtime-state/plan-intel.json \
  --receipt-dir runtime-state \
  --output-dir reports/intel
```

Optional designated LLM sidecar:

```text
python scripts/mmibkr_intelligence_report_materialize_v1.py \
  --plan-receipt runtime-state/plan-intel.json \
  --receipt-dir runtime-state \
  --output-dir reports/intel \
  --llm-sidecar governed/llm-sidecar.json \
  --llm-sidecar-sha256 <exact-64-hex-sha256>
```

## Authority

Always:

- research-only = true;
- StrategySpec write = false;
- runtime activation = false;
- promotion mutation = false;
- broker submit = false;
- broker cancel = false;
- broker flatten = false;
- live trading = false.

G13 does not add a private capability ID because it does not require private code execution.

## Acceptance

The canonical workload CI:

- compiles the dispatcher and G13 materializer;
- runs the full canonical dispatcher suite;
- runs G13 report/hash/authority/LLM/truth-state tests;
- retains a representative deterministic JSON + rendered HTML + materialization receipt as artifact `mmibkr-g13-intelligence-report`.

Rendered review is therefore part of acceptance evidence rather than optional polish.

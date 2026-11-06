# Forward model chronology recovery R1

**Status:** draft research consumer and gap audit, not a canonical ledger replacement, broker replay, or automatically granted forward credit.

This implements the operator's intended distinction:

1. A **model** produces a frozen-contract prediction at each eligible close.
2. Its frozen qualifying rule determines whether the **decision** opens a new cohort.
3. Each admitted cohort has its own D+1 entry and H20 (or model-specific) holding horizon; holding periods may overlap.
4. Model graduation review, paper portfolio expression, broker execution, and full scientific confidence are distinct stages. One original completed prospective H20 can open the existing bounded monitored review, subject to separate source, risk, Product and authorization gates. Twenty separate H20 cohorts is the stronger confidence target, **not** a universal first review floor.

## Source recovery order

First search for already durable **original** first-seen predictions and independent owning-issuer verification. Only then use the owning model's *frozen* as-of inference contract to reconstruct dates without records. Never use an after-outcome reconstruction as a first-seen prediction.

**Important for Shared Ridge:** its frozen Foundry producer (`research/run_semiconductor_external_forward_20260904.py`) refits Ridge **monthly** on training-family rows with a resolved-session purge, then emits **daily** decision predictions. Historical reconstruction must preserve the original monthly fit anchors, minimum training history, target exclusion, feature contract, provider-vintage limits and next-session entry. A present-day fitted model or present-day feature matrix cannot be substituted for prior-date inference.

Scientific authority belongs to `XoticHaze/research-foundry`. Canonical runtime data/feature semantics belong to `XoticHaze/mm-IBKR`. This public consumer **never** creates original model predictions.

## Input layout

`research/forward_decision_continuity_r1.py` takes:

- `--manifest`: JSON with exact official exchange sessions, audit date, and **owner-confirmed** model qualification dates.
- `--dated-adapters`: one immutable adapter per model/decision date, at `<root>/<PROGRAM>/<YYYY-MM-DD>.json`; optional matching `<YYYY-MM-DD>.provenance.json`. `latest.json` cannot be used as historical evidence.
- `--prior-ledger`: current canonical cohort ledger, read-only (optional).
- `--price-tape`: owned, validated, adjusted close tape; optional. When absent, simulated returns are explicitly not scored.
- `--out`: JSON audit output.

Example manifest **schema illustration only** (not a claim about the complete model bench):

```json
{
  "schema": "research.forward_decision_continuity_manifest_r1",
  "asof": "2026-11-05",
  "market_sessions": ["2026-11-03", "2026-11-04", "2026-11-05"],
  "models": [{
    "program_id": "SEMICONDUCTOR_SHARED_RIDGE",
    "frozen_model_ref": "e73ec9b15180e208de541ce5d5304888e5550433",
    "first_eligible_decision_date": "2026-11-03",
    "cadence": "DAILY_CLOSE",
    "execution_delay_sessions": 1,
    "holding_horizon_sessions": 20,
    "qualifier": "SEMICONDUCTOR_POSITIVE_VALUE",
    "stock_round_trip_cost_bps": 25,
    "sector_round_trip_cost_bps": 10
  }]
}
```

The example's three-date calendar is **not** enough to calculate a complete future H20 terminal session. The actual calendar must be official and complete for the desired window. Each other model must supply its **own** frozen cadence, eligibility, horizon and qualifying rule; monthly or event-driven models are not forced into the daily Shared Ridge schema.

Provenance example: `{"evidence_class":"REPLAYED_ASOF","replayed_at":"<UTC timestamp>","frozen_model_ref":"<frozen model identity>","adapter_sha256":"<SHA256 of exact dated adapter>"}`. A source-original receipt uses `ORIGINAL_TIMESTAMPED` and `original_observed_at`, but a string timestamp and hash alone cannot authenticate private issuer/vintage rights; **Foundry must independently authenticate** the original before scientific admission.

Optional price tape uses `{"schema":"research.forward_price_tape_r1","adjustment":"ADJUSTED_CLOSE","source_ref":"<owned canonical source>","market_data_asof":"YYYY-MM-DD","prices":{"YYYY-MM-DD":{"AMAT":100,"SMH":100}}}`. A full cash/SMH/QQQ/EW13 comparison requires the exact price members and source/cost contracts. No downloader is created here. Frozen D+1 **adjusted-close** entry/mark semantics are for research simulations; they are not executable order fills.

## What R1 proves and what it does not

- R1 flags every date lacking a qualifying **record** and distinguishes `NO_ENTRY`, `QUALIFY`, `ADMISSION_INCOMPLETE`, `OBSERVATION_ONLY`, and `MISSING_PREDICTION`. Missing records are **not** automatically classified as failed signals/trades.
- R1 refuses mismatched adapter source/date, hash tampering, changed eligibility masks, incomplete paper weights, malformed prices, future session prices and missing cost contracts.
- R1 can compute historical costed **simulation** marks versus matched-net SMH and complete equal-weight prediction universe when caller supplies complete price tapes and frozen weights.
- R1 does **not** rewrite canonical prospective ledgers, grant original timestamp/issuer qualification, promote models, start broker paper trades, submit orders, manufacture daily signals, or execute historical fits.

### Verified baseline through 2026-11-05

`research/continuity_audit/2026-11-05_shared_ridge_baseline_r1.json` binds public source file hashes and documents **40 exchange decision dates** since September 11, **2** registered native Shared Ridge dates, **37** uncovered dates between September 11 and November 4, and an additional uncovered November 5 date. This identifies a coverage-recovery workload only.

### Next owner actions

1. Foundry enumerates actual per-model start dates and all original source/receipt/vintage evidence; do not promote unqualified P08/P02 just because the dates can be replayed.
2. Foundry emits frozen as-of dated adapters for gaps with source and monthly refit lineage. Historical outcomes remain historical backtest evidence unless there is independently proved contemporaneous first-seen provenance.
3. Public production ingests date-indexed immutable adapters **without deleting older dates**, builds separate credit-classed recovery ledger and fresh first-seen ledger, then publishes a daily gap alarm.
4. Keep existing paper/BOT broker authority independent. Verify any later promotion using owner-signed economic and risk gates, not a raw cohort counter.

## Local check

```bash
python -m unittest discover -s tests -p 'test_forward_decision_continuity_r1.py' -v
```

Agent-local regression check: 9 tests passed on this draft. This does not claim GitHub Actions, provider, or native first-seen execution acceptance.

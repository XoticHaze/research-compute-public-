# MM-IBKR G12 News Feature Sidecar

## Capability

`NEWS_FEATURE_SIDECAR_BUILD`

This capability converts already-sanitized deterministic News replay evidence into a no-lookahead feature sidecar for later research/backtest plumbing.

It does **not** read price bars, fills, labels, P&L, backtest outcomes, broker state, or provider feeds.

## Canonical private owners

- `scripts/operator/news_theme_weight_review_probe_14nh.py`
  - `_split_method_counts`
  - `_policy_for_symbol`
- `scripts/operator/news_feature_sidecar_probe_14ni.py`
  - `_score_row`
  - `_build_contract`

The public adapter does not define a replacement News weighting model.

## Input

The request binds an exact article-evidence artifact by:

- scope: `input_root` or `receipt_artifact`
- relative path
- bytes
- SHA-256
- prior job fingerprint when using a receipt artifact

The intended composed path is the `articles.json` artifact emitted by `NEWS_REPLAY_ANALYZE`.

The request also binds:

- `source_run_id`
- timezone-aware `feature_asof_utc`
- bounded `feature_window_hours`
- bounded maximum article rows

## Evidence split

The canonical 14NH owner separates match evidence into:

- direct/labeled/provider/ticker
- alias/company/entity
- theme
- macro/market/sector
- other/manual-review

Theme-only evidence remains context-only and requires direct evidence before trade-signal use.

## Feature sidecar

The canonical 14NI owner emits separate fields for:

- direct article count / score
- alias article count / score
- theme article count / score
- macro context score
- composite score
- weighted evidence
- theme-only flag
- direct-required flag
- reviewed policy
- top theme/source/provider

The composite does not turn theme-only evidence into a standalone signal.

## No-lookahead authority

The canonical rule is:

```text
FEATURE_ASOF_UTC <= bar_timestamp
```

G12 records this rule but does not read bars or execute a join.

The later 14NJ join-audit promotion remains a separate sibling capability.

## Artifacts

The canonical runtime persists content-addressed:

- `news_feature_sidecar.json`
- `news_feature_sidecar.csv`
- `policy_evidence.json`
- `feature_policy_stub.json`
- `feature_column_contract.json`
- `no_lookahead_audit.json`

Cache reuse validates artifact bytes and SHA-256.

## Authority exclusions

Always false:

- provider/network acquisition
- StrategySpec write
- runtime activation
- promotion mutation
- broker submit/cancel/flatten
- live trading

This is a research-only deterministic evidence transformation.

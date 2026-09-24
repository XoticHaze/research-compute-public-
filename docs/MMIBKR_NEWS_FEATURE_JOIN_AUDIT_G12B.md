# MM-IBKR G12b News Feature Join Audit

## Capability

`NEWS_FEATURE_JOIN_AUDIT`

This capability proves whether a canonical News feature sidecar can be joined to exact governed bar timestamps without lookahead.

It does not execute a strategy or backtest.

## Canonical private owner

`scripts/operator/news_feature_backtest_join_audit_14nj.py`

Portable helpers reused:

- `_read_bar_timestamps`
- `_group_sidecar_rows`
- `_representative_sidecar_row`
- `_parse_datetime`
- `_dt_to_iso`
- `_build_contract`

The original 14NJ repo-scanning behavior is intentionally replaced by explicit governed bar artifact references.

## Inputs

- exact G12 sidecar artifact by input-root or prior receipt-artifact identity;
- exact per-symbol bar files by bytes/SHA;
- bounded rows parsed per file;
- bounded join preview count.

Supported bar timestamp parsing remains owned by 14NJ.

## Join rule

```text
FEATURE_ASOF_UTC <= bar_timestamp
```

For each sidecar symbol the audit distinguishes:

- `join_ready`
- `no_candidate_bar_files`
- `no_parseable_bar_timestamps`
- `bars_exist_but_all_before_feature_asof`
- `feature_asof_parse_failed`

This is evidence, not execution authority.

## Outputs

Content-addressed artifacts:

- `join_readiness.json`
- `bar_file_inventory.json`
- `join_preview.json`
- `join_contract.json`
- `no_lookahead_join_audit.json`

The receipt also carries compact readiness and preview projections.

## Explicit exclusions

G12b does not:

- acquire market data;
- recompute News features;
- execute a strategy/backtest;
- read labels, fills, P&L, or backtest outcomes;
- read broker state;
- write StrategySpec;
- activate runtime;
- mutate promotion;
- submit/cancel/flatten;
- enable live trading.

It is a research-only join-readiness audit.

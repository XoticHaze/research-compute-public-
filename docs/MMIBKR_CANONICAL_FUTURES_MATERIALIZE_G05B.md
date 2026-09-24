# MM-IBKR G05b Canonical Dated Futures Materialization

## Capability

`CANONICAL_DATA_MATERIALIZE`

G05b extends the existing canonical data-materialization capability to futures. It does not create a futures-only executor or route.

Asset-specific canonical owners:

- stocks: `data_manager.DataManager.ingest_external_stock_source_bars`
- futures: `futures_manager.FuturesManager.ingest_external_source_bars`

The request's `asset_type` selects the verified private entrypoint while the public capability ID, session runtime, claims, receipts, and artifact cache stay shared.

## Futures input contract

A futures request binds:

- exact governed OHLCV CSV by relative path, bytes, and SHA-256;
- exact governed source-lineage JSON by relative path, bytes, and SHA-256;
- futures root, for example `MNQ`;
- exact dated `contract_month=YYYYMM`;
- source timeframe;
- bounded target timeframe list;
- source-origin identity.

Dated source lineage is validated with the existing private admitted-futures authority:

- `materialize_admitted_futures_source_canonical._load_lineage`
- `materialize_admitted_futures_source_canonical._validate_dated_lineage`

The lineage must bind the same root, contract month, source timeframe, source SHA-256, named source authority, and resolved timestamp semantics.

## Why dated contracts only

G05b deliberately rejects `CONTINUOUS` as a contract month.

An external source may provide dated contract bars. MM-IBKR remains authoritative for:

- signal-history roll decisions;
- execution-risk roll decisions;
- continuous-series stitching;
- any back adjustment or splice policy.

G05b does not choose a roll cutoff and does not import a vendor continuous series as canonical history.

## Canonical materialization

The network-free private owner:

`FuturesManager.ingest_external_source_bars`

reuses MM-IBKR's existing:

- source normalization/cache merge;
- timeframe adapter/resampling;
- indicator owner;
- runtime target-feature materialization;
- atomic futures CSV writer.

For each returned timeframe the public adapter verifies the frame's canonical causal feature manifest and publishes the existing canonical feature sidecar through:

`publish_canonical_feature_sidecar.publish_sidecar`

## Artifacts

For each source or derived timeframe:

- `futures/{ROOT}-{YYYYMM}/{TF}.csv`
- `futures/{ROOT}-{YYYYMM}/{TF}.features.csv`
- `futures/{ROOT}-{YYYYMM}/{TF}.feature_manifest.json`
- canonical feature sidecar for the feature CSV

Every artifact is exposed only by relative path, byte count, and SHA-256.

## Explicit exclusions

Always false:

- market-data acquisition;
- IB historical-data requests;
- new downloader authority;
- roll-cutoff selection;
- back adjustment;
- continuous splice;
- StrategySpec write;
- runtime activation;
- promotion mutation;
- broker submit/cancel/flatten;
- live trading.

The IB object supplied to the private owner is fail-closed for network methods.

## Acceptance proof

The public deterministic fixture covers:

- MNQ dated-contract 1-minute source materialization;
- derived 12-minute target materialization;
- canonical causal feature manifests;
- canonical feature sidecars;
- source-lineage root/month/timestamp failures;
- continuous-month rejection;
- asset-specific private-entrypoint verification;
- content-addressed artifact tamper detection;
- regression of the existing stock materialization path through the shared workload suite.

The private acceptance target is the existing exact module:

`tests.test_materialize_admitted_futures_source_canonical`

plus the already-admitted:

`tests.test_publish_canonical_feature_sidecar`

through the reusable encrypted private-test probe.

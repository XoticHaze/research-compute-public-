from __future__ import annotations

"""Source-only preflight for a genuinely new semiconductor information modality.

After PR #35 rejected additional price-derived risk/regime state, this checks whether the
existing public Yahoo daily payload has enough quote-volume/raw-close coverage to build a
causal volume/liquidity information plane for the original seven semiconductor development
symbols plus SMH/QQQ. No model, path target, return target, admission, ranking or external
panel is evaluated here.

Candidate features are fixed before any model outcome:
- log-volume surprise versus prior 252 sessions;
- 20/60-session log-volume ratio;
- log-dollar-volume surprise using raw close * raw shares;
- 20-session Amihud-style illiquidity using adjusted returns / raw dollar volume;
- sector breadth of positive volume surprise;
- sector cross-sectional dispersion of volume surprise.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

START = '2014-01-01'
END = '2026-09-03'
TRAIN = ('AMAT','APH','KLAC','LRCX','TXN','NXPI','ADI')
CONTEXT = ('SMH','QQQ')
SYMBOLS = (*TRAIN, *CONTEXT)
OUT = Path('semiconductor_volume_liquidity_preflight_20260906.json')
FEATURES = (
    'volume_surprise252',
    'volume_ratio20_60',
    'dollar_volume_surprise252',
    'amihud20',
    'sector_volume_surprise_breadth',
    'sector_volume_surprise_dispersion',
)


def epoch(text: str) -> int:
    return int(datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp())


def load(symbol: str) -> pd.DataFrame:
    q = urlencode({
        'period1': epoch(START),
        'period2': epoch(END),
        'interval': '1d',
        'events': 'history',
        'includeAdjustedClose': 'true',
    })
    req = Request(
        f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{q}',
        headers={'User-Agent': 'Mozilla/5.0 research-compute-public/1.0'},
    )
    with urlopen(req, timeout=30) as response:
        payload = json.loads(response.read().decode())
    result = (payload.get('chart', {}).get('result') or [None])[0]
    if not result:
        raise RuntimeError(f'{symbol}: no chart result')
    timestamps = result.get('timestamp') or []
    indicators = result.get('indicators', {})
    quote = (indicators.get('quote') or [{}])[0]
    raw_close = quote.get('close') or []
    volume = quote.get('volume') or []
    adj_close = ((indicators.get('adjclose') or [{}])[0].get('adjclose') or [])
    n = min(len(timestamps), len(raw_close), len(volume), len(adj_close))
    frame = pd.DataFrame({
        'timestamp': pd.to_datetime(timestamps[:n], unit='s', utc=True),
        'raw_close': pd.to_numeric(pd.Series(raw_close[:n]), errors='coerce'),
        'adj_close': pd.to_numeric(pd.Series(adj_close[:n]), errors='coerce'),
        'volume': pd.to_numeric(pd.Series(volume[:n]), errors='coerce'),
    }).sort_values('timestamp').drop_duplicates('timestamp', keep='last').reset_index(drop=True)
    return frame


def z_against_prior(series: pd.Series, window: int = 252, min_periods: int = 126) -> pd.Series:
    prior = series.shift(1)
    mean = prior.rolling(window, min_periods=min_periods).mean()
    std = prior.rolling(window, min_periods=min_periods).std(ddof=0).replace(0, np.nan)
    return (series - mean) / std


def main() -> None:
    raw = {symbol: load(symbol) for symbol in SYMBOLS}
    cutoff = min(frame.iloc[-1].timestamp for frame in raw.values())
    valid_sets = []
    source = {}
    for symbol, frame in raw.items():
        bounded = frame.loc[frame.timestamp <= cutoff].copy()
        usable = bounded[
            bounded.raw_close.notna()
            & bounded.adj_close.notna()
            & bounded.volume.notna()
            & (bounded.raw_close > 0)
            & (bounded.adj_close > 0)
            & (bounded.volume > 0)
        ]
        valid_sets.append(set(usable.timestamp))
        source[symbol] = {
            'rows_total_at_or_before_cutoff': int(len(bounded)),
            'rows_positive_price_volume': int(len(usable)),
            'first_positive_price_volume': None if usable.empty else usable.iloc[0].timestamp.isoformat(),
            'last_positive_price_volume': None if usable.empty else usable.iloc[-1].timestamp.isoformat(),
            'coverage_fraction': 0.0 if bounded.empty else float(len(usable) / len(bounded)),
        }
    calendar = pd.DatetimeIndex(sorted(set.intersection(*valid_sets)))
    if len(calendar) < 3000:
        raise RuntimeError(f'insufficient common positive price/volume calendar={len(calendar)}')

    frames = {}
    volume_surprise = {}
    for symbol in SYMBOLS:
        f = raw[symbol].set_index('timestamp').reindex(calendar)
        if f[['raw_close','adj_close','volume']].isna().any().any():
            raise RuntimeError(f'{symbol}: missing common-calendar source values')
        log_volume = np.log(f.volume.astype(float))
        dollar_volume = f.raw_close.astype(float) * f.volume.astype(float)
        log_dollar = np.log(dollar_volume)
        adj_ret1 = f.adj_close.astype(float).pct_change()
        surprise = z_against_prior(log_volume)
        part = pd.DataFrame(index=calendar)
        part['volume_surprise252'] = surprise
        part['volume_ratio20_60'] = np.log(
            f.volume.astype(float).rolling(20, min_periods=20).mean()
            / f.volume.astype(float).rolling(60, min_periods=60).mean()
        )
        part['dollar_volume_surprise252'] = z_against_prior(log_dollar)
        scaled_illiquidity = (adj_ret1.abs() / dollar_volume.replace(0, np.nan)) * 1e9
        part['amihud20'] = scaled_illiquidity.rolling(20, min_periods=20).mean()
        frames[symbol] = part
        volume_surprise[symbol] = surprise

    sector_surprise = pd.DataFrame({s: volume_surprise[s] for s in TRAIN}, index=calendar)
    sector_breadth = (sector_surprise > 0).mean(axis=1)
    sector_dispersion = sector_surprise.std(axis=1, ddof=0)
    for symbol in TRAIN:
        frames[symbol]['sector_volume_surprise_breadth'] = sector_breadth
        frames[symbol]['sector_volume_surprise_dispersion'] = sector_dispersion

    usable_feature_rows = {}
    for symbol in TRAIN:
        complete = frames[symbol][list(FEATURES)].replace([np.inf, -np.inf], np.nan).dropna()
        usable_feature_rows[symbol] = {
            'rows': int(len(complete)),
            'first': None if complete.empty else complete.index[0].isoformat(),
            'last': None if complete.empty else complete.index[-1].isoformat(),
        }
    minimum_feature_rows = min(item['rows'] for item in usable_feature_rows.values())
    status = 'PASS' if minimum_feature_rows >= 3000 else 'FAIL'
    if status != 'PASS':
        raise RuntimeError(f'volume/liquidity feature support below 3000 rows: {usable_feature_rows}')

    out = {
        'schema': 'public_compute.semiconductor_volume_liquidity_preflight.v1',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'status': status,
        'development_universe': list(TRAIN),
        'context_symbols': list(CONTEXT),
        'external_panels_loaded': False,
        'common_cutoff': cutoff.isoformat(),
        'common_positive_price_volume_calendar_rows': int(len(calendar)),
        'common_first': calendar[0].isoformat(),
        'common_last': calendar[-1].isoformat(),
        'source_coverage': source,
        'candidate_information_family': 'volume_liquidity',
        'candidate_features_frozen_before_model_outcomes': list(FEATURES),
        'feature_semantics': {
            'normalization': 'volume/dollar-volume surprises normalized against prior history only via shift(1)',
            'dollar_volume': 'raw Yahoo quote close multiplied by raw Yahoo share volume',
            'returns_for_amihud': 'adjusted-close daily return',
            'signal_timing': 'all inputs observable by signal-session close; any downstream execution remains +1 session',
        },
        'usable_feature_rows': usable_feature_rows,
        'minimum_complete_feature_rows': int(minimum_feature_rows),
        'model_executed': False,
        'targets_computed': False,
        'admission_or_ranking_changed': False,
        'next_boundary': 'PASS authorizes one development-only information-value consumer against the exact PR31/PR34 path-head control; it does not authorize trading policy',
        'research_only': True,
        'promotion_authority': False,
        'runtime_mutation': False,
        'broker_action': False,
        'live_trading_change': False,
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + '\n')
    print('SEMICONDUCTOR_VOLUME_LIQUIDITY_PREFLIGHT=' + json.dumps(out, sort_keys=True))


if __name__ == '__main__':
    main()

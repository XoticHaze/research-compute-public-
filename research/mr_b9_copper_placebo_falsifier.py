import json
import numpy as np
import pandas as pd
import yfinance as yf

COST = 0.0025
START = '2012-01-01'
END = '2026-09-01'
TICKERS = ['COPX', 'CPER', 'GLD']
SHIFTS = list(range(6, 73, 6))


def cagr(r):
    if len(r) == 0:
        return float('nan')
    eq = (1 + r).prod()
    return eq ** (12 / len(r)) - 1 if eq > 0 else -1


def maxdd(r):
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())


def evaluate(mask, copx, gld):
    pos = mask.astype(int)
    gross = pd.Series(np.where(pos.eq(1), copx, gld), index=mask.index)
    switches = pos.diff().abs().fillna(0)
    net = gross - switches * COST
    p = float(pos.mean())
    matched = p * copx + (1 - p) * gld
    return {
        'cagr': cagr(net),
        'matched_cagr': cagr(matched),
        'excess': cagr(net) - cagr(matched),
        'maxdd': maxdd(net),
        'months': len(net),
        'switches': int(switches.sum()),
        'copx_participation': p,
    }


def circular_shift(s, k):
    a = s.to_numpy(copy=True)
    return pd.Series(np.roll(a, k), index=s.index).astype(bool)


def main():
    px = yf.download(TICKERS, start=START, end=END, auto_adjust=True, progress=False)['Close']
    m = px.resample('ME').last().dropna()
    ret = m.pct_change().dropna()
    sig = (m['CPER'].pct_change(6) > 0).shift(1).reindex(ret.index).fillna(False)
    idx = ret.index[ret.index >= pd.Timestamp('2015-01-31')]
    ret = ret.loc[idx]
    sig = sig.loc[idx]

    actual = evaluate(sig, ret['COPX'], ret['GLD'])
    placebos = []
    for k in SHIFTS:
        shifted = circular_shift(sig, k)
        e = evaluate(shifted, ret['COPX'], ret['GLD'])
        e['shift_months'] = k
        placebos.append(e)

    ex = np.array([x['excess'] for x in placebos], dtype=float)
    percentile = float((ex < actual['excess']).mean())
    p90 = float(np.quantile(ex, 0.90))

    windows = {}
    positive_windows = 0
    for name, a, b in [
        ('2015_2018', '2015-01-31', '2018-12-31'),
        ('2019_2021', '2019-01-31', '2021-12-31'),
        ('2022_2024', '2022-01-31', '2024-12-31'),
        ('2025_plus', '2025-01-31', '2026-08-31'),
    ]:
        z = ret.loc[a:b]
        s = sig.reindex(z.index)
        if len(z):
            windows[name] = evaluate(s, z['COPX'], z['GLD'])
            positive_windows += int(windows[name]['excess'] > 0)

    decision = 'SUPPORT_TIMING_ALPHA' if actual['excess'] > p90 and positive_windows >= 3 else 'FAIL_TIMING_PLACEBO'
    out = {
        'experiment': 'B9_COPPER_PRODUCER_TREND_PARTICIPATION_PLACEBO_R1',
        'frozen_parent': 'prior completed-month 6m CPER > 0 selects COPX else GLD',
        'cost_one_way': COST,
        'signal_lag_months': 1,
        'placebo': 'deterministic circular shifts of frozen binary signal; 6..72 months by 6',
        'actual': actual,
        'placebo_excesses': placebos,
        'actual_excess_percentile': percentile,
        'placebo_excess_p90': p90,
        'positive_chronology_windows': positive_windows,
        'windows': windows,
        'decision': decision,
        'protected_p01_holdout_read': False,
    }
    print(json.dumps(out, indent=2, default=str))
    with open('mr_b9_copper_placebo_falsifier.json', 'w') as f:
        json.dump(out, f, indent=2, default=str)


if __name__ == '__main__':
    main()

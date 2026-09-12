import datetime as dt
import json
import math
import urllib.request
from pathlib import Path

C = json.loads(Path('research/cowz-fcf-crossfit-r1.json').read_text())
START = dt.datetime.fromisoformat(C['start'] + 'T00:00:00+00:00')
END = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)


def fetch(sym):
    url = (f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={int(START.timestamp())}'
           f'&period2={int(END.timestamp())}&interval=1d&events=history&includeAdjustedClose=true')
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        obj = json.load(r)['chart']['result'][0]
    adj = obj['indicators'].get('adjclose', [{}])[0].get('adjclose') or obj['indicators']['quote'][0]['close']
    return {dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat(): float(p)
            for t, p in zip(obj['timestamp'], adj) if p is not None}


def solve(a, b):
    n = len(b)
    m = [list(map(float, a[i])) + [float(b[i])] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-12:
            raise RuntimeError('singular regression matrix')
        m[col], m[pivot] = m[pivot], m[col]
        div = m[col][col]
        m[col] = [x / div for x in m[col]]
        for r in range(n):
            if r == col:
                continue
            f = m[r][col]
            m[r] = [m[r][j] - f * m[col][j] for j in range(n + 1)]
    return [m[i][-1] for i in range(n)]


def ols(rows):
    # y=COWZ, X=[1, SPY, VTV, QUAL]
    p = 4
    xtx = [[0.0] * p for _ in range(p)]
    xty = [0.0] * p
    for r in rows:
        x = [1.0, r['SPY'], r['VTV'], r['QUAL']]
        y = r['COWZ']
        for i in range(p):
            xty[i] += x[i] * y
            for j in range(p):
                xtx[i][j] += x[i] * x[j]
    ridge = 1e-8
    for i in range(1, p):
        xtx[i][i] += ridge
    return solve(xtx, xty)


def ann(monthly):
    if not monthly:
        return None
    wealth = 1.0
    for x in monthly:
        wealth *= 1.0 + x
    return wealth ** (12.0 / len(monthly)) - 1.0


def compound(vals):
    w = 1.0
    for v in vals:
        w *= 1.0 + v
    return w - 1.0


px = {s: fetch(s) for s in C['symbols']}
common = sorted(set.intersection(*(set(px[s]) for s in C['symbols'])))
months = {}
for d in common:
    months.setdefault(d[:7], []).append(d)
rows = []
for m, ds in sorted(months.items()):
    if len(ds) < 10:
        continue
    f, l = ds[0], ds[-1]
    rows.append({'month': m, **{s: px[s][l] / px[s][f] - 1.0 for s in C['symbols']}})

rows = [r for r in rows if r['month'] + '-01' >= C['evaluation_start']]
years = sorted({r['month'][:4] for r in rows})
cost_m = C['incremental_cowz_cost_bps_per_year'] / 10000.0 / 12.0
heldout = []
for year in years:
    train = [r for r in rows if r['month'][:4] != year]
    test = [r for r in rows if r['month'][:4] == year]
    if len(train) < 36 or len(test) < 6:
        continue
    coef = ols(train)
    for r in test:
        pred = coef[0] + coef[1] * r['SPY'] + coef[2] * r['VTV'] + coef[3] * r['QUAL']
        resid = r['COWZ'] - pred - cost_m
        heldout.append({'month': r['month'], 'residual': resid, 'coef': coef})

raw_after_cost = [r['COWZ'] - cost_m for r in rows]
spy = [r['SPY'] for r in rows]
vtv = [r['VTV'] for r in rows]
qual = [r['QUAL'] for r in rows]
raw_excess_spy = [a - b for a, b in zip(raw_after_cost, spy)]
raw_excess_vtv = [a - b for a, b in zip(raw_after_cost, vtv)]
raw_excess_qual = [a - b for a, b in zip(raw_after_cost, qual)]
resids = [r['residual'] for r in heldout]
recent = [r['residual'] for r in heldout if r['month'] + '-01' >= C['recent_start']]

year_resid = {}
for r in heldout:
    year_resid.setdefault(r['month'][:4], []).append(r['residual'])
year_comp = {y: compound(v) for y, v in year_resid.items()}
pos_frac = sum(v > 0 for v in year_comp.values()) / len(year_comp) if year_comp else 0.0
worst_year = min(year_comp.values()) if year_comp else None

metrics = {
    'months': len(rows),
    'heldout_months': len(heldout),
    'heldout_years': len(year_comp),
    'full_cowz_after_cost_cagr': ann(raw_after_cost),
    'full_spy_cagr': ann(spy),
    'full_vtv_cagr': ann(vtv),
    'full_qual_cagr': ann(qual),
    'full_after_cost_excess_vs_spy': ann(raw_after_cost) - ann(spy),
    'full_after_cost_excess_vs_vtv': ann(raw_after_cost) - ann(vtv),
    'full_after_cost_excess_vs_qual': ann(raw_after_cost) - ann(qual),
    'full_crossfit_residual_annualized': ann(resids),
    'recent_crossfit_residual_annualized': ann(recent),
    'positive_heldout_year_fraction': pos_frac,
    'worst_heldout_year_residual': worst_year,
    'heldout_year_residuals': year_comp,
}

g = C['gates']
checks = {
    'full_crossfit_residual': metrics['full_crossfit_residual_annualized'] >= g['min_full_crossfit_residual_annualized'],
    'recent_crossfit_residual': metrics['recent_crossfit_residual_annualized'] >= g['min_recent_crossfit_residual_annualized'],
    'positive_year_fraction': metrics['positive_heldout_year_fraction'] >= g['min_positive_heldout_year_fraction'],
    'worst_year': metrics['worst_heldout_year_residual'] >= g['min_worst_heldout_year_residual'],
    'raw_excess_vs_spy': metrics['full_after_cost_excess_vs_spy'] >= g['min_full_after_cost_excess_vs_spy'],
}

out = {
    'schema': 'cowz_fcf_crossfit_result.v1',
    'experiment_id': C['experiment_id'],
    'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(),
    'source': 'Yahoo Finance chart adjusted-close public endpoint',
    'contract': C,
    'metrics': metrics,
    'checks': checks,
    'decision': 'PASS_IMPLEMENTATION_DISCRIMINATOR' if all(checks.values()) else 'REJECT_IMPLEMENTATION_CLAIM',
    'research_only': True,
}
Path('cowz-fcf-crossfit-r1-result.json').write_text(json.dumps(out, indent=2, sort_keys=True))
print(json.dumps(out, indent=2, sort_keys=True))

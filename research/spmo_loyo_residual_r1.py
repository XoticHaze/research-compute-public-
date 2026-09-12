import datetime as dt
import json
import math
import urllib.request
from pathlib import Path

CONTRACT = json.loads(Path('research/spmo-loyo-residual-r1.json').read_text())
START = dt.datetime.fromisoformat(CONTRACT['start'] + 'T00:00:00+00:00')
END = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)
SYMS = ['SPMO'] + CONTRACT['factors']


def fetch(sym):
    url = (f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={int(START.timestamp())}'
           f'&period2={int(END.timestamp())}&interval=1d&events=history&includeAdjustedClose=true')
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        o = json.load(r)['chart']['result'][0]
    a = o['indicators'].get('adjclose', [{}])[0].get('adjclose') or o['indicators']['quote'][0]['close']
    return {dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat(): float(p)
            for t, p in zip(o['timestamp'], a) if p is not None}


def solve(a, b):
    n = len(b)
    m = [list(map(float, a[i])) + [float(b[i])] for i in range(n)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        if abs(m[p][c]) < 1e-12:
            raise RuntimeError('singular design')
        m[c], m[p] = m[p], m[c]
        q = m[c][c]
        m[c] = [v / q for v in m[c]]
        for r in range(n):
            if r == c:
                continue
            q = m[r][c]
            m[r] = [m[r][j] - q * m[c][j] for j in range(n + 1)]
    return [m[i][-1] for i in range(n)]


def ols(xs, ys):
    k = len(xs[0])
    xtx = [[0.0] * k for _ in range(k)]
    xty = [0.0] * k
    for x, y in zip(xs, ys):
        for i in range(k):
            xty[i] += x[i] * y
            for j in range(k):
                xtx[i][j] += x[i] * x[j]
    return solve(xtx, xty)


px = {s: fetch(s) for s in SYMS}
ds = sorted(set.intersection(*(set(px[s]) for s in SYMS)))
months = {}
for d in ds:
    months.setdefault(d[:7], []).append(d)
rows = []
for month, dates in sorted(months.items()):
    if len(dates) < 10:
        continue
    first, last = dates[0], dates[-1]
    rets = {s: px[s][last] / px[s][first] - 1 for s in SYMS}
    rows.append({'month': month, 'year': int(month[:4]), **rets})

years = sorted(set(r['year'] for r in rows))
cost_m = CONTRACT['incremental_implementation_cost_bps_per_year'] / 10000 / 12
annual = []
all_resid = []
for year in years:
    train = [r for r in rows if r['year'] != year]
    test = [r for r in rows if r['year'] == year]
    if len(test) < 10 or len(train) < 36:
        continue
    xs = [[1.0] + [r[s] for s in CONTRACT['factors']] for r in train]
    ys = [r['SPMO'] for r in train]
    beta = ols(xs, ys)
    rr = []
    for r in test:
        pred = beta[0] + sum(beta[i + 1] * r[s] for i, s in enumerate(CONTRACT['factors']))
        resid = r['SPMO'] - pred - cost_m
        rr.append(resid)
        all_resid.append((r['year'], resid))
    ann = sum(rr) / len(rr) * 12
    annual.append({'year': year, 'months': len(rr), 'after_cost_annualized_residual': ann,
                   'positive': ann > 0, 'train_beta': {'intercept': beta[0], **{s: beta[i+1] for i, s in enumerate(CONTRACT['factors'])}}})

full = sum(r for _, r in all_resid) / len(all_resid) * 12
recent_vals = [r for y, r in all_resid if y >= CONTRACT['recent_start_year']]
recent = sum(recent_vals) / len(recent_vals) * 12
posfrac = sum(a['positive'] for a in annual) / len(annual)
worst = min(a['after_cost_annualized_residual'] for a in annual)
g = CONTRACT['gates']
passed = (full >= g['min_full_after_cost_annualized_residual'] and
          recent >= g['min_recent_after_cost_annualized_residual'] and
          posfrac >= g['min_positive_year_fraction'] and
          worst >= g['min_worst_year_after_cost_residual'])
out = {
    'schema': 'spmo_loyo_residual_result.v1',
    'experiment_id': CONTRACT['experiment_id'],
    'months': len(all_resid),
    'held_out_years': len(annual),
    'full_after_cost_annualized_residual': full,
    'recent_after_cost_annualized_residual': recent,
    'positive_year_fraction': posfrac,
    'worst_year_after_cost_annualized_residual': worst,
    'annual': annual,
    'gates': g,
    'survives_loyo_residual_falsifier': passed,
    'research_only': True
}
Path('spmo-loyo-residual-r1-result.json').write_text(json.dumps(out, sort_keys=True, indent=2))
print(json.dumps(out, sort_keys=True))

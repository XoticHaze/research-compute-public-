from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import p248_smallvalue_survivor_complementarity_r1 as p248

WINDOWS = {'2020':'2020-01-01','2022':'2022-01-01'}
SV_BP = 10

def metrics(r):
    q = pd.Series(r, dtype=float).dropna()
    e = (1 + q).cumprod()
    n = len(q)
    ann = float(q.mean() * 12)
    vol = float(q.std(ddof=1) * math.sqrt(12))
    return {
        'months': int(n),
        'cagr': float(e.iloc[-1] ** (12 / n) - 1),
        'maxdd': float((e / e.cummax() - 1).min()),
        'sharpe_rf0': float(ann / vol) if vol else None,
    }

def endpoint_cost(r, bps):
    q = pd.Series(r, dtype=float).dropna().copy()
    f = bps / 10000
    if len(q):
        q.iloc[0] -= f
        q.iloc[-1] -= f
    return q

svm = p248.close_month[['AVUV','AVDV','IJR','VSS']].pct_change().dropna()
small_value = 0.5 * svm.AVUV + 0.5 * svm.AVDV
generic_small = 0.5 * svm.IJR + 0.5 * svm.VSS
p64 = p248.p64.copy(); p64.index = p64.index.to_period('M').to_timestamp('M')
p36 = p248.p36.copy(); p36.index = p36.index.to_period('M').to_timestamp('M')
x = small_value.to_frame('sv').join(generic_small.rename('smallcap')).join(p64.rename(columns={'candidate':'p64'})).join(p36.rename(columns={'candidate':'p36'})).dropna()

out = {}
for name, start in WINDOWS.items():
    q = x.loc[x.index >= pd.Timestamp(start)].copy()
    value_blend = (q.sv + q.p64 + q.p36) / 3
    smallcap_blend = (q.smallcap + q.p64 + q.p36) / 3
    value_net = endpoint_cost(value_blend, SV_BP / 3)
    smallcap_net = endpoint_cost(smallcap_blend, SV_BP / 3)
    vm = metrics(value_net)
    cm = metrics(smallcap_net)
    folds = []
    for i, ix in enumerate(np.array_split(np.arange(len(q)), 5), 1):
        a = endpoint_cost(value_blend.iloc[ix], SV_BP / 3)
        b = endpoint_cost(smallcap_blend.iloc[ix], SV_BP / 3)
        folds.append({'fold': i, 'excess_cagr': metrics(a)['cagr'] - metrics(b)['cagr']})
    out[name] = {
        'smallvalue_blend': vm,
        'generic_smallcap_blend': cm,
        'specificity_excess_cagr': vm['cagr'] - cm['cagr'],
        'specificity_sharpe_delta': vm['sharpe_rf0'] - cm['sharpe_rf0'],
        'specificity_maxdd_delta': vm['maxdd'] - cm['maxdd'],
        'positive_specificity_folds': sum(z['excess_cagr'] > 0 for z in folds),
        'folds': folds,
    }

a = out['2020']; b = out['2022']
support = (
    a['specificity_excess_cagr'] > 0 and b['specificity_excess_cagr'] > 0 and
    a['specificity_sharpe_delta'] >= 0 and b['specificity_sharpe_delta'] >= 0 and
    a['specificity_maxdd_delta'] >= 0 and b['specificity_maxdd_delta'] >= 0 and
    a['positive_specificity_folds'] >= 4
)
res = {
    'schema': 'research.p251_smallvalue_specificity_r1',
    'parent': 'P249/P251',
    'claim': 'P249 risk-efficiency is specific to the fixed AVUV/AVDV small-value sleeve rather than generic small-cap diversification.',
    'contract': {
        'candidate_smallvalue': 'fixed 50/50 AVUV/AVDV',
        'matched_smallcap_control': 'fixed 50/50 IJR/VSS',
        'unchanged_companions': ['P64','P36'],
        'capital_rule': 'equal one-third sleeve weights',
        'windows': WINDOWS,
        'cost_rule': 'same 10 bps small-sleeve endpoint cost applied to candidate and control blend at one-third capital share',
        'gate': 'positive candidate-vs-generic-smallcap CAGR both windows; nonnegative Sharpe and maxdd deltas both windows; >=4/5 positive 2020+ chronology folds',
        'no_weight_fund_window_threshold_survivor_or_parameter_search': True,
    },
    'tests': out,
    'decision': 'P251_SMALLVALUE_SPECIFICITY_SUPPORTED' if support else 'P251_SMALLVALUE_SPECIFICITY_NOT_SUPPORTED',
    'interpretation_rule': 'Failure narrows P249 attribution only. It does not erase P249 fixed-blend support unless independent material evidence also invalidates the broader role.',
    'limitations': ['Yahoo adjusted prices are research-only', 'AVUV/AVDV common history limits the sample'],
    'boundaries': {'portfolio_ranking': False, 'allocation_authority': False, 'runtime': False, 'broker': False, 'live_trading': False},
}
Path('artifacts').mkdir(exist_ok=True)
Path('artifacts/p251_smallvalue_specificity_r1.json').write_text(json.dumps(res, indent=2, sort_keys=True, allow_nan=False))
print(json.dumps(res, sort_keys=True))

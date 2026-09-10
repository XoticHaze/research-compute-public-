from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

T = ['SPMO','IJS','SPY','IJR','SRLN','HYG','SHY','DBMF','BIL']
COST = 0.0025
ROLLING_MONTHS = 24
ROLLING_SUPPORT_GATE = 0.65

raw = yf.download(T, start='2015-01-01', end='2026-09-11', auto_adjust=True, progress=False, threads=False)
close = raw['Close'] if isinstance(raw.columns, pd.MultiIndex) else raw
r = close[T].resample('ME').last().pct_change(fill_method=None)
p249 = 0.5 * (r.SPMO + r.IJS)
p249_control = 0.5 * (r.SPY + r.IJR)

betas = []
for i in range(len(r)):
    z = r[['HYG','SHY','SRLN']].iloc[max(0, i-24):i].dropna()
    if len(z) < 24:
        betas.append((np.nan, np.nan))
        continue
    b = np.clip(np.linalg.lstsq(z[['HYG','SHY']].values, z.SRLN.values, rcond=None)[0], 0, 1)
    if b.sum() > 1:
        b = b / b.sum()
    betas.append(tuple(b))
beta = pd.DataFrame(betas, index=r.index, columns=['h','s']).shift(1)
loan_control = beta.h * r.HYG + beta.s * r.SHY

q = pd.DataFrame({
    'p249': p249,
    'p249_control': p249_control,
    'p373': r.SRLN,
    'p373_control': loan_control,
    'dbmf': r.DBMF,
    'dbmf_control': r.BIL,
}).dropna().loc['2021-01-01':]
q['core'] = 0.5 * q.p249 + 0.5 * q.p373
q['core_control'] = 0.5 * q.p249_control + 0.5 * q.p373_control
q['candidate'] = 0.75 * q.core + 0.25 * q.dbmf
q['candidate_control'] = 0.75 * q.core_control + 0.25 * q.dbmf_control

def stats(s: pd.Series) -> dict:
    x = s.copy()
    x.iloc[0] -= COST
    x.iloc[-1] -= COST
    wealth = (1 + x).cumprod()
    n = len(x)
    vol = x.std(ddof=1) * math.sqrt(12)
    return {
        'months': n,
        'cagr': float(wealth.iloc[-1] ** (12/n) - 1),
        'sharpe': float(x.mean() * 12 / vol),
        'max_drawdown': float((wealth / wealth.cummax() - 1).min()),
    }

def evaluate(z: pd.DataFrame) -> dict:
    core = stats(z.core)
    cand = stats(z.candidate)
    ctl = stats(z.candidate_control)
    diffs = {
        'cagr': cand['cagr'] - core['cagr'],
        'sharpe': cand['sharpe'] - core['sharpe'],
        'max_drawdown': cand['max_drawdown'] - core['max_drawdown'],
    }
    matched_excess = cand['cagr'] - ctl['cagr']
    utility_improvements = sum(diffs[k] > 0 for k in ['cagr','sharpe','max_drawdown'])
    return {
        'core': core,
        'candidate': cand,
        'candidate_control': ctl,
        'matched_excess_cagr': matched_excess,
        'vs_core': diffs,
        'utility_improvements': utility_improvements,
        'window_support': bool(matched_excess > 0 and utility_improvements >= 2),
    }

full = evaluate(q)
rolling = []
for end in range(ROLLING_MONTHS, len(q) + 1):
    z = q.iloc[end-ROLLING_MONTHS:end]
    ev = evaluate(z)
    rolling.append({
        'start': str(z.index[0].date()),
        'end': str(z.index[-1].date()),
        'matched_excess_cagr': ev['matched_excess_cagr'],
        'vs_core': ev['vs_core'],
        'utility_improvements': ev['utility_improvements'],
        'support': ev['window_support'],
    })

support_fraction = sum(x['support'] for x in rolling) / len(rolling)
median_marginal_cagr = float(np.median([x['vs_core']['cagr'] for x in rolling]))
median_sharpe_delta = float(np.median([x['vs_core']['sharpe'] for x in rolling]))
median_drawdown_delta = float(np.median([x['vs_core']['max_drawdown'] for x in rolling]))
full_utility_support = full['matched_excess_cagr'] > 0 and full['utility_improvements'] >= 2
robust = bool(
    full_utility_support
    and support_fraction >= ROLLING_SUPPORT_GATE
    and median_marginal_cagr > 0
    and median_sharpe_delta > 0
)
if robust:
    decision = 'ROBUST_INCREMENTAL_UTILITY_SUPPORTED'
elif full_utility_support and support_fraction >= 0.40:
    decision = 'MIXED_STABILITY_SPECIALIST_SLEEVE_ONLY'
else:
    decision = 'INCREMENTAL_UTILITY_NOT_SUPPORTED'

if robust:
    reconciliation = 'P465 full/common-sample utility is corroborated by rolling temporal stability; P430 moving-block bootstrap miss remains a sampling-robustness caveat rather than a contradiction.'
elif decision == 'MIXED_STABILITY_SPECIALIST_SLEEVE_ONLY':
    reconciliation = 'P465 full-sample utility is real but rolling persistence is incomplete, which is directionally consistent with P430 failing its stricter sampling-robustness gate. Retain DBMF matched-alpha/diversification evidence but do not promote fixed-dose portfolio admission.'
else:
    reconciliation = 'P465 full-sample comparison does not survive the predeclared temporal-stability admission gate; this aligns with the adverse P430 bootstrap caveat. Demote fixed-dose portfolio admission without erasing underlying DBMF matched-alpha/diversification evidence.'

out = {
    'schema': 'research.p466_dbmf_admission_stability_r1.v1',
    'workload_id': 'P466_DBMF_PORTFOLIO_ADMISSION_CONFLICT_R1',
    'parent': 'FUND_MODEL_SURVIVOR_PORTFOLIO',
    'claim': 'Predeclared rolling temporal-stability test of the exact single collapsed 75% frozen P249+P373 core plus 25% DBMF implementation. This is distinct from P430 moving-block bootstrap and P465 cross-candidate fixed-capital comparison.',
    'contract': {
        'frozen_candidate': '75% P249+P373 frozen core + 25% DBMF',
        'matched_control': '75% frozen core control + 25% BIL',
        'common_sample_start': '2021-01-01',
        'endpoint_cost_bps': 25,
        'rolling_window_months': ROLLING_MONTHS,
        'rolling_support_gate': ROLLING_SUPPORT_GATE,
        'window_support_rule': 'matched after-cost excess CAGR > 0 and at least two of CAGR, Sharpe, max-drawdown improve versus frozen core',
        'terminal_support_rule': 'full sample supports same rule, >=65% rolling windows support it, median rolling marginal CAGR > 0, and median rolling Sharpe delta > 0',
        'weight_grid': False,
        'date_rescue': False,
        'threshold_rescue': False,
    },
    'coverage': {'months': len(q), 'start': str(q.index[0].date()), 'end': str(q.index[-1].date()), 'rolling_windows': len(rolling)},
    'full_sample': full,
    'rolling': rolling,
    'rolling_summary': {
        'support_fraction': support_fraction,
        'median_marginal_cagr': median_marginal_cagr,
        'median_sharpe_delta': median_sharpe_delta,
        'median_max_drawdown_delta': median_drawdown_delta,
    },
    'decision': decision,
    'reconciliation': reconciliation,
    'boundaries': {'scientific_authority': True, 'portfolio_ranking': False, 'allocation_authority': False, 'runtime': False, 'broker': False, 'live_trading': False},
}
Path('research/artifacts').mkdir(parents=True, exist_ok=True)
Path('research/artifacts/p466_dbmf_admission_stability_r1.json').write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False))
print(json.dumps({'decision': decision, 'coverage': out['coverage'], 'full_matched_excess_pp': round(100*full['matched_excess_cagr'],3), 'full_vs_core': full['vs_core'], 'rolling_summary': out['rolling_summary'], 'reconciliation': reconciliation}, sort_keys=True))

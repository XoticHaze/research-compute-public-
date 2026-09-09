from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import p82_component_contribution_r2 as p82

START = pd.Timestamp('2015-01-01')


def cagr(r):
    r = pd.Series(r, dtype=float).dropna()
    return float((1 + r).prod() ** (12 / len(r)) - 1) if len(r) else float('nan')


def analyze(candidate, baseline):
    x = pd.DataFrame({'candidate': candidate, 'baseline': baseline}).dropna()
    x['excess_monthly'] = x['candidate'] - x['baseline']
    x['year'] = x.index.year
    annual = []
    for year, z in x.groupby('year'):
        annual.append({
            'year': int(year),
            'months': int(len(z)),
            'candidate_cagr': cagr(z.candidate),
            'baseline_cagr': cagr(z.baseline),
            'excess_cagr': cagr(z.candidate) - cagr(z.baseline),
            'sum_monthly_excess': float(z.excess_monthly.sum()),
        })
    ranked = sorted(annual, key=lambda d: d['sum_monthly_excess'], reverse=True)
    total_positive = sum(max(0.0, d['sum_monthly_excess']) for d in annual)
    top3_positive_share = (sum(max(0.0, d['sum_monthly_excess']) for d in ranked[:3]) / total_positive) if total_positive > 0 else None
    removal = {}
    for n in (1, 2, 3):
        years = {d['year'] for d in ranked[:n]}
        z = x.loc[~x['year'].isin(years)]
        removal[str(n)] = {
            'removed_years': sorted(years),
            'months': int(len(z)),
            'excess_cagr': cagr(z.candidate) - cagr(z.baseline),
        }
    return {
        'full_excess_cagr': cagr(x.candidate) - cagr(x.baseline),
        'positive_calendar_year_fraction': float(sum(d['excess_cagr'] > 0 for d in annual) / len(annual)),
        'top3_positive_excess_share': top3_positive_share,
        'annual': annual,
        'remove_top_contribution_years': removal,
    }


def main():
    f = p82.build().loc[START:].copy()
    candidate = 0.5 * f.p64 + 0.5 * f.p36
    matched = 0.5 * f.p64_matched + 0.5 * f.p36_matched
    tests = {
        'matched': analyze(candidate, matched),
        'qqq': analyze(candidate, f.qqq),
    }
    m = tests['matched']
    q = tests['qqq']
    concentrated = (
        (m['top3_positive_excess_share'] is not None and m['top3_positive_excess_share'] >= 0.60)
        or m['remove_top_contribution_years']['2']['excess_cagr'] <= 0
        or q['remove_top_contribution_years']['2']['excess_cagr'] <= 0
        or m['positive_calendar_year_fraction'] < 0.60
        or q['positive_calendar_year_fraction'] < 0.55
    )
    out = {
        'schema': 'research.p82_year_concentration_r1',
        'parent': 'P82',
        'hypothesis': 'The unchanged fixed 50/50 P64+P36 blend has post-2015 after-cost excess that is distributed across calendar years rather than being carried by a small number of unusually favorable years.',
        'scientific_contract': {
            'blend_weights': [0.5, 0.5],
            'component_cost_bps': 50,
            'start': '2015-01-01',
            'comparators': ['same fixed component matched-control blend', 'QQQ'],
            'tests': ['calendar-year persistence', 'top-positive-year concentration', 'remove top 1/2/3 contribution years'],
            'no_parameter_or_weight_tuning': True,
        },
        'tests': tests,
        'decision': 'P82_EXCESS_CONCENTRATED' if concentrated else 'P82_EXCESS_BROADLY_DISTRIBUTED',
    }
    Path('artifacts').mkdir(exist_ok=True)
    Path('artifacts/p82_year_concentration_r1.json').write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False))
    print(json.dumps(out, sort_keys=True))


if __name__ == '__main__':
    main()

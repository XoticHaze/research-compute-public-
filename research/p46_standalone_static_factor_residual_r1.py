from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_temporal_factor_discriminators_r1 as p46
import p46_p36_beta_residual_r1 as beta

CONTROLS = ('SPY','QQQ','TLT','GLD','DBC')

def main():
    close = base.load(p46.SYMBOLS)
    month_start = pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp()
    close = close.loc[close.index < month_start]
    a = p46.returns(close, p46.FACTORS)
    monthly = close.resample('ME').last()
    factor_returns = monthly.loc[:, list(CONTROLS)].pct_change().reindex(a.index)
    active = a.gross - a.turnover * 0.005 - a.ew
    windows = [('full', active.index.min(), active.index.max() + pd.Timedelta(days=1)), ('2022_forward', pd.Timestamp('2022-01-01'), active.index.max() + pd.Timedelta(days=1))]
    tests = {}
    for name, lo, hi in windows:
        ix = active.index[(active.index >= lo) & (active.index < hi)]
        y = active.loc[ix]
        x2 = factor_returns.loc[ix, ['QQQ','SPY']]
        x5 = factor_returns.loc[ix, list(CONTROLS)]
        valid = y.notna() & x5.notna().all(axis=1)
        y = y.loc[valid]
        x2 = x2.loc[valid]
        x5 = x5.loc[valid]
        r2 = beta.fit(y, x2.to_numpy())
        r2['bootstrap'] = beta.boot(y, x2.to_numpy(), reps=4000, block=min(12,max(3,len(y)//3)), seed=2026090911 + len(y))
        r5 = beta.fit(y, x5.to_numpy())
        r5['bootstrap'] = beta.boot(y, x5.to_numpy(), reps=4000, block=min(12,max(3,len(y)//3)), seed=2026090912 + len(y))
        tests[name] = {'months': int(len(y)), 'qqq_spy': r2, 'all_static_universe_controls': r5}
    full = tests['full']['all_static_universe_controls']
    recent = tests['2022_forward']['all_static_universe_controls']
    supported = full['annualized_intercept'] > 0 and full['bootstrap']['bootstrap_95pct'][0] > 0 and recent['annualized_intercept'] > 0
    decision = 'P46_DYNAMIC_SELECTION_RESIDUAL_SURVIVES_STATIC_UNIVERSE_CONTROLS' if supported else 'P46_RESIDUAL_EXPLAINED_OR_UNSTABLE_UNDER_STATIC_UNIVERSE_CONTROLS'
    out = {
        'schema':'research.p46_standalone_static_factor_residual_r1',
        'parent':'P46',
        'scientific_contract':{
            'active_return':'P46 net at 50 bps minus exact equal-weight universe control',
            'null':'measured residual alpha is explainable by a static linear mix of the same investable cross-asset returns',
            'reference_controls':['QQQ','SPY'],
            'expanded_controls':list(CONTROLS),
            'bootstrap':'4000 moving-block draws',
            'no_parameter_or_weight_tuning':True
        },
        'source':{'normalized_complete_month_price_panel_sha256':base.source_hash(close)},
        'tests':tests,
        'decision':decision
    }
    Path('artifacts').mkdir(exist_ok=True)
    Path('artifacts/p46_standalone_static_factor_residual_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps(out,sort_keys=True))

if __name__ == '__main__':
    main()

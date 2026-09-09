from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base

FULL = ('SPY','QQQ','TLT','GLD','DBC')
FACTORS = ('mom6','trend200','low_vol6','drawdown6')

def build(close, symbols):
    monthly = close.resample('ME').last(); daily_r = close.pct_change()
    maps = {
        'mom6': monthly.pct_change(6),
        'trend200': (close / close.rolling(200, min_periods=160).mean() - 1).resample('ME').last(),
        'low_vol6': -(daily_r.rolling(126, min_periods=100).std(ddof=0) * math.sqrt(252)).resample('ME').last(),
        'drawdown6': (close / close.rolling(126, min_periods=100).max() - 1).resample('ME').last(),
    }
    prev = {s: 0. for s in symbols}; rec=[]
    for i, dt in enumerate(monthly.index[:-1]):
        block = pd.DataFrame({f: maps[f].loc[dt, list(symbols)] for f in FACTORS}, index=list(symbols))
        if block.isna().any().any(): continue
        score = block.rank(axis=0, pct=True, method='average').mean(axis=1)
        nxt = monthly.index[i+1]; realized = monthly.loc[nxt, list(symbols)] / monthly.loc[dt, list(symbols)] - 1
        if realized.isna().any(): continue
        chosen = score.sort_values(ascending=False).head(2).index.tolist(); w={s:(.5 if s in chosen else 0.) for s in symbols}
        turn=.5*sum(abs(w[s]-prev[s]) for s in symbols)
        rec.append({'date':nxt,'gross':sum(w[s]*float(realized[s]) for s in symbols),'ew':float(realized.mean()),'turnover':turn}); prev=w
    return pd.DataFrame(rec).set_index('date')

def evaluate(fr, bps):
    c=fr.gross-fr.turnover*bps/10000; cm=base.metrics(c); bm=base.metrics(fr.ew); pos,folds=base.fold_count(c,fr.ew)
    return {'candidate':cm,'matched_equal_weight':bm,'excess_cagr':cm['cagr']-bm['cagr'],'positive_folds':pos,'folds':folds}

def main():
    close=base.load(FULL)
    current_month_start=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp()
    close=close.loc[close.index<current_month_start]
    tests={}
    variants={'full':FULL, **{f'without_{s}':tuple(x for x in FULL if x!=s) for s in FULL}}
    for name,symbols in variants.items():
        fr=build(close,symbols); tests[name]={'symbols':list(symbols),'window':{'start':str(fr.index.min().date()),'end':str(fr.index.max().date()),'months':len(fr)},'25':evaluate(fr,25),'50':evaluate(fr,50)}
    loo=[v for k,v in tests.items() if k!='full']
    supported=sum(v['25']['excess_cagr']>0 and v['50']['excess_cagr']>0 and v['25']['positive_folds']>=3 for v in loo)>=4
    out={'schema':'research.p46_leave_one_asset_out_r1','parent':'P46','scientific_contract':{'economics':'fixed four-factor top-2 monthly cross-asset composite','test':'remove each asset one at a time and recompute ranks/weights on remaining four assets','costs_bps':[25,50],'matched_control':'equal weight of same remaining universe','incomplete_months_excluded':True,'no_parameter_tuning':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_complete_month_price_panel_sha256':base.source_hash(close)},'tests':tests,'decision':'P46_UNIVERSE_ROBUSTNESS_SUPPORTED' if supported else 'P46_UNIVERSE_DEPENDENCE_DETECTED'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_leave_one_asset_out_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps({'decision':out['decision'],'summary':{k:{'window':v['window'],'excess25':v['25']['excess_cagr'],'folds25':v['25']['positive_folds'],'excess50':v['50']['excess_cagr']} for k,v in tests.items()}},sort_keys=True))
if __name__=='__main__': main()

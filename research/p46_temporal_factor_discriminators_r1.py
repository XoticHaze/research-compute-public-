from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import fixed_multifactor_cross_sectional_r1_complete_month as guard

SYMBOLS = base.UNIVERSES['crossasset']
FACTORS = ('mom6','trend200','low_vol6','drawdown6')

def feature_panel(close, factors):
    monthly=close.resample('ME').last(); daily_r=close.pct_change()
    vol6=(daily_r.rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last()
    trend200=(close/close.rolling(200,min_periods=160).mean()-1).resample('ME').last()
    dd6=(close/close.rolling(126,min_periods=100).max()-1).resample('ME').last(); mom6=monthly.pct_change(6)
    maps={'mom6':mom6,'trend200':trend200,'low_vol6':-vol6,'drawdown6':dd6}; rows=[]
    for dt in monthly.index:
        block=pd.DataFrame({f:maps[f].loc[dt,list(SYMBOLS)] for f in factors},index=list(SYMBOLS))
        if block.isna().any().any(): continue
        score=block.rank(axis=0,pct=True,method='average').mean(axis=1)
        rows += [{'month':dt,'symbol':s,'score':float(score[s])} for s in SYMBOLS]
    return pd.DataFrame(rows), monthly

def returns(close,factors):
    panel,monthly=feature_panel(close,factors); months=sorted(panel.month.unique()); prev={s:0. for s in SYMBOLS}; rec=[]
    for month in months:
        block=panel[panel.month==month].sort_values(['score','symbol'],ascending=[False,True]); loc=monthly.index.get_loc(month)
        if len(block)!=len(SYMBOLS) or not isinstance(loc,(int,np.integer)) or loc+1>=len(monthly): continue
        nxt=monthly.index[loc+1]; realized=monthly.loc[nxt,list(SYMBOLS)]/monthly.loc[month,list(SYMBOLS)]-1
        if realized.isna().any(): continue
        chosen=block.head(2).symbol.tolist(); w={s:(.5 if s in chosen else 0.) for s in SYMBOLS}; turnover=.5*sum(abs(w[s]-prev[s]) for s in SYMBOLS)
        rec.append({'date':nxt,'gross':sum(w[s]*float(realized[s]) for s in SYMBOLS),'ew':float(realized.mean()),'turnover':turnover}); prev=w
    return pd.DataFrame(rec).set_index('date')

def score(frame,bps=25):
    c=frame.gross-frame.turnover*bps/10000; b=frame.ew; cm=base.metrics(c); bm=base.metrics(b); pos,folds=base.fold_count(c,b)
    return {'months':len(frame),'start':str(frame.index.min().date()),'end':str(frame.index.max().date()),'candidate':cm,'matched_ew':bm,'excess_cagr':cm['cagr']-bm['cagr'],'positive_folds':pos,'folds':folds}

def main():
    close=base.load(SYMBOLS); full=returns(close,FACTORS)
    tests={}
    for start in ('2015-01-01','2020-01-01'):
        f=full.loc[pd.Timestamp(start):]; tests[f'temporal_{start[:4]}_forward']={'25':score(f,25),'50':score(f,50)}
    for omitted in FACTORS:
        f=returns(close,tuple(x for x in FACTORS if x!=omitted)); tests[f'ablate_{omitted}']={'25':score(f,25),'50':score(f,50)}
    out={'schema':'research.p46_temporal_factor_discriminators_r1','parent':'P46','scientific_contract':{'economics':'crossasset top-2 monthly fixed composite','temporal_holdouts':['2015-forward','2020-forward'],'ablations':[f'omit {x}' for x in FACTORS],'costs_bps':[25,50],'comparator':'same-universe equal weight','no_parameter_tuning':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_price_panel_sha256':base.source_hash(close)},'tests':tests}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_temporal_factor_discriminators_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps({k:{'excess25':v['25']['excess_cagr'],'folds25':v['25']['positive_folds'],'excess50':v['50']['excess_cagr']} for k,v in tests.items()},sort_keys=True))
if __name__=='__main__': main()

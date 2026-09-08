from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base

FACTORS=('mom6','trend200','low_vol6','drawdown6'); BASE=tuple(base.UNIVERSES['industry'])

def maps(close):
    m=close.resample('ME').last(); dr=close.pct_change()
    return m,{'mom6':m.pct_change(6),'trend200':(close/close.rolling(200,min_periods=160).mean()-1).resample('ME').last(),'low_vol6':-(dr.rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last(),'drawdown6':(close/close.rolling(126,min_periods=100).max()-1).resample('ME').last()}

def run(symbols,factors=FACTORS,lag=0):
    close=base.load(tuple(symbols)); m,fm=maps(close); prev={s:0. for s in symbols}; rec=[]
    for dt in m.index:
        b=pd.DataFrame({f:fm[f].loc[dt,list(symbols)] for f in factors},index=list(symbols))
        if b.isna().any().any(): continue
        sc=b.rank(axis=0,pct=True,method='average').mean(axis=1); loc=m.index.get_loc(dt)
        if not isinstance(loc,(int,np.integer)) or loc+1+lag>=len(m): continue
        start=m.index[loc+lag]; nxt=m.index[loc+1+lag]; r=m.loc[nxt,list(symbols)]/m.loc[start,list(symbols)]-1
        if r.isna().any(): continue
        chosen=sc.sort_values(ascending=False).head(3).index.tolist(); w={s:(1/3 if s in chosen else 0.) for s in symbols}; to=.5*sum(abs(w[s]-prev[s]) for s in symbols)
        rec.append({'date':nxt,'gross':sum(w[s]*float(r[s]) for s in symbols),'ew':float(r.mean()),'turnover':to}); prev=w
    return pd.DataFrame(rec).set_index('date'),close

def score(fr,bps):
    c=fr.gross-fr.turnover*bps/10000; b=fr.ew; cm,bm=base.metrics(c),base.metrics(b); pos,folds=base.fold_count(c,b)
    return {'months':len(fr),'start':str(fr.index.min().date()),'end':str(fr.index.max().date()),'candidate':cm,'matched_ew':bm,'excess_cagr':cm['cagr']-bm['cagr'],'positive_folds':pos,'folds':folds}
def pack(fr): return {'25':score(fr,25),'50':score(fr,50)}
def bootstrap(fr,n=2000,seed=47):
    x=(fr.gross-fr.turnover*.0025-fr.ew).to_numpy(); rng=np.random.default_rng(seed); vals=np.array([rng.choice(x,size=len(x),replace=True).mean()*12 for _ in range(n)]); q=np.quantile(vals,[.025,.975]); return {'annualized_mean_excess':float(x.mean()*12),'bootstrap_95pct':[float(q[0]),float(q[1])],'p_excess_le_zero':float((vals<=0).mean()),'n':n}
def breakeven(fr):
    b=base.metrics(fr.ew)['cagr']; xs=[]
    for bp in range(201): xs.append(base.metrics(fr.gross-fr.turnover*bp/10000)['cagr']-b)
    non=[i for i,x in enumerate(xs) if x<=0]; return {'first_nonpositive_bps':non[0] if non else None,'excess25':xs[25],'excess50':xs[50],'excess100':xs[100]}
def main():
    tests={}; full,close=run(BASE)
    for omitted in BASE:
        fr,_=run(tuple(s for s in BASE if s!=omitted)); tests[f'leave_industry_out_{omitted}']=pack(fr)
    for f in FACTORS:
        fr,_=run(BASE,(f,)); tests[f'factor_alone_{f}']=pack(fr)
    lag,_=run(BASE,FACTORS,1); tests['one_month_execution_lag']=pack(lag); tests['paired_bootstrap_25bps']=bootstrap(full); tests['cost_breakeven']=breakeven(full)
    out={'schema':'research.p47_deep_robustness_r2','parent':'P47','scientific_contract':{'universe':list(BASE),'top_k':3,'factors':list(FACTORS),'cadence':'monthly','costs_bps':[25,50],'matched_comparator':'same-universe equal weight','tests':['8 leave-one-industry-out','4 factor-alone','one-month execution lag','paired bootstrap','cost break-even'],'no_weight_or_lookback_tuning':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_price_panel_sha256':base.source_hash(close)},'tests':tests}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p47_deep_robustness_r2.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({k:({'excess25':v['25']['excess_cagr'],'folds25':v['25']['positive_folds'],'excess50':v['50']['excess_cagr']} if isinstance(v,dict) and '25' in v else v) for k,v in tests.items()},sort_keys=True))
if __name__=='__main__': main()

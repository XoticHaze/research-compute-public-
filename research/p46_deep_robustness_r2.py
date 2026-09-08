from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base

FACTORS=('mom6','trend200','low_vol6','drawdown6')
BASE=tuple(base.UNIVERSES['crossasset'])
ALT=('SPY','QQQ','IEF','IAU','PDBC')


def feature_maps(close):
    m=close.resample('ME').last(); dr=close.pct_change()
    return m,{
      'mom6':m.pct_change(6),
      'trend200':(close/close.rolling(200,min_periods=160).mean()-1).resample('ME').last(),
      'low_vol6':-(dr.rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last(),
      'drawdown6':(close/close.rolling(126,min_periods=100).max()-1).resample('ME').last(),
    }


def run(symbols,factors=FACTORS,lag=0):
    close=base.load(tuple(symbols)); m,maps=feature_maps(close); prev={s:0. for s in symbols}; rec=[]
    for dt in m.index:
        block=pd.DataFrame({f:maps[f].loc[dt,list(symbols)] for f in factors},index=list(symbols))
        if block.isna().any().any(): continue
        score=block.rank(axis=0,pct=True,method='average').mean(axis=1)
        loc=m.index.get_loc(dt)
        if not isinstance(loc,(int,np.integer)) or loc+1+lag>=len(m): continue
        nxt=m.index[loc+1+lag]; realized=m.loc[nxt,list(symbols)]/m.loc[m.index[loc+lag],list(symbols)]-1
        if realized.isna().any(): continue
        chosen=score.sort_values(ascending=False).head(2).index.tolist(); w={s:(.5 if s in chosen else 0.) for s in symbols}
        turn=.5*sum(abs(w[s]-prev[s]) for s in symbols)
        rec.append({'date':nxt,'gross':sum(w[s]*float(realized[s]) for s in symbols),'ew':float(realized.mean()),'turnover':turn}); prev=w
    return pd.DataFrame(rec).set_index('date'),close


def score(fr,bps=25):
    c=fr.gross-fr.turnover*bps/10000; b=fr.ew; cm,bm=base.metrics(c),base.metrics(b); pos,folds=base.fold_count(c,b)
    return {'months':len(fr),'start':str(fr.index.min().date()),'end':str(fr.index.max().date()),'candidate':cm,'matched_ew':bm,'excess_cagr':cm['cagr']-bm['cagr'],'positive_folds':pos,'folds':folds,'mean_turnover_annual':float(fr.turnover.mean()*12)}


def paired_bootstrap(fr,n=2000,seed=46):
    x=(fr.gross-fr.turnover*.0025-fr.ew).to_numpy(); rng=np.random.default_rng(seed); vals=[]
    for _ in range(n):
        samp=rng.choice(x,size=len(x),replace=True); vals.append(float(np.mean(samp)*12))
    lo,hi=np.quantile(vals,[.025,.975]); return {'annualized_mean_excess':float(x.mean()*12),'bootstrap_95pct':[float(lo),float(hi)],'p_excess_le_zero':float(np.mean(np.array(vals)<=0)),'n':n}


def breakeven(fr):
    bm=base.metrics(fr.ew)['cagr']; grid=list(range(0,201)); ex=[]
    for b in grid:
        ex.append(base.metrics(fr.gross-fr.turnover*b/10000)['cagr']-bm)
    non=[b for b,e in zip(grid,ex) if e<=0]
    return {'first_nonpositive_bps':non[0] if non else None,'excess_at_25':ex[25],'excess_at_50':ex[50],'excess_at_100':ex[100]}


def pack(fr): return {'25':score(fr,25),'50':score(fr,50)}

def main():
    tests={}; base_fr,base_close=run(BASE)
    for omitted in BASE:
        syms=tuple(s for s in BASE if s!=omitted); fr,_=run(syms); tests[f'leave_asset_out_{omitted}']=pack(fr)
    alt_fr,alt_close=run(ALT); tests['independent_proxy_universe']=pack(alt_fr)
    for factor in FACTORS:
        fr,_=run(BASE,(factor,)); tests[f'factor_alone_{factor}']=pack(fr)
    lag_fr,_=run(BASE,FACTORS,lag=1); tests['one_month_execution_lag']=pack(lag_fr)
    tests['paired_bootstrap_25bps']=paired_bootstrap(base_fr)
    tests['cost_breakeven']=breakeven(base_fr)
    out={'schema':'research.p46_deep_robustness_r2','parent':'P46','scientific_contract':{'base_universe':list(BASE),'factors':list(FACTORS),'top_k':2,'cadence':'monthly','costs_bps':[25,50],'matched_comparator':'same-universe equal weight','tests':['5 leave-one-asset-out','independent proxy universe','4 factor-alone attribution','one-month execution lag','paired bootstrap','cost break-even'],'no_weight_or_lookback_tuning':True},'sources':{'base_provider':'Yahoo Finance via yfinance','base_panel_sha256':base.source_hash(base_close),'alt_panel_sha256':base.source_hash(alt_close)},'tests':tests}
    Path('artifacts').mkdir(exist_ok=True); p=Path('artifacts/p46_deep_robustness_r2.json'); p.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    summary={k:({'excess25':v['25']['excess_cagr'],'folds25':v['25']['positive_folds'],'excess50':v['50']['excess_cagr']} if isinstance(v,dict) and '25' in v else v) for k,v in tests.items()}; print(json.dumps(summary,sort_keys=True))
if __name__=='__main__': main()

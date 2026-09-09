from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base

SYMBOLS=('VOO','VUG','IEF','IAU','PDBC')
FACTORS=('mom6','trend200','low_vol6','drawdown6')
BPS=(25,50,100)


def feature_panel(close):
    monthly=close.resample('ME').last(); daily_r=close.pct_change()
    vol6=(daily_r.rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last()
    trend200=(close/close.rolling(200,min_periods=160).mean()-1).resample('ME').last()
    dd6=(close/close.rolling(126,min_periods=100).max()-1).resample('ME').last()
    mom6=monthly.pct_change(6)
    maps={'mom6':mom6,'trend200':trend200,'low_vol6':-vol6,'drawdown6':dd6}
    rows=[]
    for dt in monthly.index:
        block=pd.DataFrame({f:maps[f].loc[dt,list(SYMBOLS)] for f in FACTORS},index=list(SYMBOLS))
        if block.isna().any().any(): continue
        score=block.rank(axis=0,pct=True,method='average').mean(axis=1)
        rows += [{'month':dt,'symbol':s,'score':float(score[s])} for s in SYMBOLS]
    return pd.DataFrame(rows),monthly


def cagr(x):
    x=pd.Series(x,dtype=float).dropna()
    return float((1+x).prod()**(12/len(x))-1) if len(x) else float('nan')


def max_dd(x):
    w=(1+pd.Series(x,dtype=float).dropna()).cumprod(); return float((w/w.cummax()-1).min())


def build(close):
    panel,monthly=feature_panel(close); months=sorted(panel.month.unique()); prev={s:0.0 for s in SYMBOLS}; rec=[]
    for month in months:
        block=panel[panel.month==month].sort_values(['score','symbol'],ascending=[False,True])
        loc=monthly.index.get_loc(month)
        if len(block)!=len(SYMBOLS) or not isinstance(loc,(int,np.integer)) or loc+1>=len(monthly): continue
        nxt=monthly.index[loc+1]; r=monthly.loc[nxt,list(SYMBOLS)]/monthly.loc[month,list(SYMBOLS)]-1
        if r.isna().any(): continue
        chosen=set(block.head(2).symbol.tolist()); w={s:(0.5 if s in chosen else 0.0) for s in SYMBOLS}
        turn=0.5*sum(abs(w[s]-prev[s]) for s in SYMBOLS)
        rec.append({'date':nxt,'gross':sum(w[s]*float(r[s]) for s in SYMBOLS),'matched':float(r.mean()),'turnover':turn})
        prev=w
    return pd.DataFrame(rec).set_index('date')


def score(f,bp):
    cand=f.gross-f.turnover*bp/10000.0; matched=f.matched
    folds=[]
    for n,ids in enumerate(np.array_split(np.arange(len(f)),5),1):
        q=f.iloc[ids]; ce=cagr(q.gross-q.turnover*bp/10000.0); be=cagr(q.matched)
        folds.append({'fold':n,'excess_cagr':ce-be})
    return {'months':int(len(f)),'start':str(f.index.min().date()),'end':str(f.index.max().date()),'candidate_cagr':cagr(cand),'matched_cagr':cagr(matched),'excess_cagr':cagr(cand)-cagr(matched),'positive_folds':int(sum(x['excess_cagr']>0 for x in folds)),'candidate_max_drawdown':max_dd(cand),'matched_max_drawdown':max_dd(matched),'annual_turnover':float(f.turnover.mean()*12),'folds':folds}


def main():
    close=base.load(SYMBOLS)
    current_month_start=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp()
    close=close.loc[close.index<current_month_start]
    f=build(close)
    tests={str(bp):score(f,bp) for bp in BPS}
    p=tests['50']
    decision='P46_ALT_ETF_REPRESENTATION_SUPPORTED' if p['excess_cagr']>0 and p['positive_folds']>=3 else 'P46_ALT_ETF_REPRESENTATION_NOT_SUPPORTED'
    out={'schema':'research.p46_alt_etf_representation_r2','parent':'P46','hypothesis':'The frozen four-factor top-2 cross-asset mechanism transports to a distinct ETF representation of the same broad economic sleeves.','scientific_contract':{'original_representation':['SPY','QQQ','TLT','GLD','DBC'],'alternate_representation':list(SYMBOLS),'mapping':{'SPY':'VOO','QQQ':'VUG','TLT':'IEF','GLD':'IAU','DBC':'PDBC'},'factors':list(FACTORS),'top_k':2,'costs_bps':list(BPS),'matched_control':'same alternate-universe equal weight over identical months','no_factor_weight_topk_tuning':True,'representation_test_not_independent_source_test':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_complete_month_price_panel_sha256':base.source_hash(close)},'tests':tests,'decision':decision,'interpretation_rule':'Support indicates representation transport, not source independence or promotion. Failure rejects transport to this alternate sleeve representation, not the original P46 result.'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_alt_etf_representation_r2.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'tests':tests},sort_keys=True))

if __name__=='__main__': main()

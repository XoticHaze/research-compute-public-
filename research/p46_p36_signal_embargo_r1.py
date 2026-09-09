from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_temporal_factor_discriminators_r1 as p46

P46_SYMS=tuple(p46.SYMBOLS); P36_SYMS=('SMH','QQQ'); ALL=tuple(dict.fromkeys((*P46_SYMS,'SMH')))
def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1)
def embargo(close,n):
    if n==0: return close.copy()
    keep=[]
    for _,g in close.groupby(close.index.to_period('M')):
        keep.extend(g.index[:-n] if len(g)>n else [])
    return close.loc[pd.DatetimeIndex(keep)]
def evaluate(close,n,bp):
    info=embargo(close,n); panel,im=p46.feature_panel(info[list(P46_SYMS)],p46.FACTORS); actual=close.resample('ME').last(); mom=info[list(P36_SYMS)].resample('ME').last().pct_change(6)
    s46={}; s36={}
    for dt in sorted(panel.month.unique()):
        b=panel[panel.month==dt].sort_values(['score','symbol'],ascending=[False,True])
        if len(b)==len(P46_SYMS):
            chosen=set(b.head(2).symbol.tolist()); s46[pd.Timestamp(dt)]={s:(.5 if s in chosen else 0.) for s in P46_SYMS}
    for dt in mom.index:
        if mom.loc[dt].isna().any(): continue
        pick='SMH' if mom.at[dt,'SMH']>mom.at[dt,'QQQ'] else 'QQQ'; s36[pd.Timestamp(dt)]={'SMH':1. if pick=='SMH' else 0.,'QQQ':1. if pick=='QQQ' else 0.}
    prev46={s:0. for s in P46_SYMS}; prev36={s:0. for s in P36_SYMS}; rec=[]; labels=[pd.Timestamp(x) for x in actual.index if pd.Timestamp(x) in s46 and pd.Timestamp(x) in s36]
    for i in range(len(labels)-1):
        dt,nxt=labels[i],labels[i+1]; r46=actual.loc[nxt,list(P46_SYMS)]/actual.loc[dt,list(P46_SYMS)]-1; r36=actual.loc[nxt,list(P36_SYMS)]/actual.loc[dt,list(P36_SYMS)]-1
        if r46.isna().any() or r36.isna().any(): continue
        w46=s46[dt]; w36=s36[dt]; t46=.5*sum(abs(w46[s]-prev46[s]) for s in P46_SYMS); t36=.5*sum(abs(w36[s]-prev36[s]) for s in P36_SYMS)
        g46=sum(w46[s]*float(r46[s]) for s in P46_SYMS); g36=sum(w36[s]*float(r36[s]) for s in P36_SYMS)
        cand=.5*(g46-t46*bp/10000)+.5*(g36-t36*bp/10000); matched=.5*float(r46.mean())+.25*float(r36['SMH']+r36['QQQ']); rec.append((nxt,cand,matched)); prev46=w46; prev36=w36
    f=pd.DataFrame(rec,columns=['date','candidate','matched']).set_index('date'); pos=0
    for ids in np.array_split(np.arange(len(f)),5):
        q=f.iloc[ids]; pos+=cagr(q.candidate)-cagr(q.matched)>0
    return {'months':len(f),'start':str(f.index.min().date()),'end':str(f.index.max().date()),'excess_cagr':cagr(f.candidate)-cagr(f.matched),'positive_folds':int(pos)}
def main():
    close=base.load(ALL); month_start=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp(); close=close.loc[close.index<month_start]
    tests={str(n):{str(bp):evaluate(close,n,bp) for bp in (25,50,100)} for n in (0,1,3,5)}; one=tests['1']['50']; three=tests['3']['50']; supported=one['excess_cagr']>0 and one['positive_folds']>=3 and three['excess_cagr']>0
    out={'schema':'research.p46_p36_signal_embargo_r1','parents':['P46','P36'],'scientific_contract':{'candidate':'fixed 50% P46 + 50% P36 research combination','test':'remove final N trading days from every signal month before feature/rank computation, then realize on unchanged actual month-end intervals','embargo_trading_days':[0,1,3,5],'costs_bps_per_sleeve':[25,50,100],'matched_control':'exact blended matched control','incomplete_months_excluded':True,'no_parameter_or_weight_tuning':True,'no_portfolio_authority':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_complete_month_price_panel_sha256':base.source_hash(close)},'tests':tests,'decision':'P46_P36_SIGNAL_EMBARGO_SUPPORTED' if supported else 'P46_P36_SIGNAL_EMBARGO_WEAK'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_p36_signal_embargo_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'tests':tests},sort_keys=True))
if __name__=='__main__': main()

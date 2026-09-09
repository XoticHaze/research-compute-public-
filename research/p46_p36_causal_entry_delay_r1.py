from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_temporal_factor_discriminators_r1 as p46

P46_SYMS=tuple(p46.SYMBOLS)
P36_SYMS=('SMH','QQQ')
ALL=tuple(dict.fromkeys((*P46_SYMS,'SMH')))

def cagr(r):
    r=pd.Series(r,dtype=float).dropna()
    return float((1+r).prod()**(12/len(r))-1)

def signals(close):
    panel,monthly=p46.feature_panel(close[list(P46_SYMS)],p46.FACTORS)
    p46sig={}
    for dt in sorted(panel.month.unique()):
        b=panel[panel.month==dt].sort_values(['score','symbol'],ascending=[False,True])
        if len(b)==len(P46_SYMS):
            chosen=set(b.head(2).symbol.tolist())
            p46sig[pd.Timestamp(dt)]={s:(.5 if s in chosen else 0.) for s in P46_SYMS}
    m36=close[list(P36_SYMS)].resample('ME').last(); mom=m36.pct_change(6); p36sig={}
    for dt in m36.index:
        if mom.loc[dt].isna().any(): continue
        pick='SMH' if mom.at[dt,'SMH']>mom.at[dt,'QQQ'] else 'QQQ'
        p36sig[pd.Timestamp(dt)]={'SMH':1. if pick=='SMH' else 0.,'QQQ':1. if pick=='QQQ' else 0.}
    return monthly,p46sig,p36sig

def evaluate(close,delay,bps):
    monthly,s46,s36=signals(close)
    month_labels=[pd.Timestamp(x) for x in monthly.index if pd.Timestamp(x) in s46 and pd.Timestamp(x) in s36]
    daily=close.index
    prev46={s:0. for s in P46_SYMS}; prev36={s:0. for s in P36_SYMS}; rec=[]
    for i in range(len(month_labels)-1):
        sig=month_labels[i]; nxt=month_labels[i+1]
        sig_obs=daily[daily<=sig]
        nxt_obs=daily[daily<=nxt]
        if len(sig_obs)==0 or len(nxt_obs)==0: continue
        sig_day=sig_obs[-1]; nxt_day=nxt_obs[-1]
        a=int(daily.get_loc(sig_day))+delay; z=int(daily.get_loc(nxt_day))+delay
        if a>=len(daily) or z>=len(daily) or z<=a: continue
        entry=daily[a]; exit_=daily[z]
        w46=s46[sig]; w36=s36[sig]
        r46=close.loc[exit_,list(P46_SYMS)]/close.loc[entry,list(P46_SYMS)]-1
        r36=close.loc[exit_,list(P36_SYMS)]/close.loc[entry,list(P36_SYMS)]-1
        if r46.isna().any() or r36.isna().any(): continue
        t46=.5*sum(abs(w46[s]-prev46[s]) for s in P46_SYMS)
        t36=.5*sum(abs(w36[s]-prev36[s]) for s in P36_SYMS)
        g46=sum(w46[s]*float(r46[s]) for s in P46_SYMS)
        g36=sum(w36[s]*float(r36[s]) for s in P36_SYMS)
        candidate=.5*(g46-t46*bps/10000)+.5*(g36-t36*bps/10000)
        matched=.5*float(r46.mean())+.5*.5*float(r36['SMH']+r36['QQQ'])
        rec.append({'date':exit_,'candidate':candidate,'matched':matched,'entry':str(entry.date()),'signal_month':str(sig.date())})
        prev46=w46; prev36=w36
    f=pd.DataFrame(rec).set_index('date')
    pos=0; folds=[]
    for n,ids in enumerate(np.array_split(np.arange(len(f)),5),1):
        sub=f.iloc[ids]; ex=cagr(sub.candidate)-cagr(sub.matched); pos+=ex>0
        folds.append({'fold':n,'start':str(sub.index.min().date()),'end':str(sub.index.max().date()),'excess_cagr':ex})
    return {'months':len(f),'start':str(f.index.min().date()),'end':str(f.index.max().date()),'candidate_cagr':cagr(f.candidate),'matched_cagr':cagr(f.matched),'excess_cagr':cagr(f.candidate)-cagr(f.matched),'positive_folds':int(pos),'folds':folds}

def main():
    close=base.load(ALL)
    month_start=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp()
    close=close.loc[close.index<month_start]
    tests={str(d):{str(bp):evaluate(close,d,bp) for bp in (25,50,100)} for d in (0,1,3,5)}
    d1=tests['1']['50']; d3=tests['3']['50']
    supported=d1['excess_cagr']>0 and d1['positive_folds']>=3 and d3['excess_cagr']>0
    out={'schema':'research.p46_p36_causal_entry_delay_r1','parents':['P46','P36'],'scientific_contract':{'candidate':'fixed 50% P46 + 50% P36 research combination','signal_information':'month-end signals use only closes available through the completed signal month','execution_test':'enter and exit at the same N-trading-day offset after each month end','entry_delays_trading_days':[0,1,3,5],'costs_bps_per_sleeve':[25,50,100],'matched_control':'exact blended same-interval control','incomplete_months_excluded':True,'no_parameter_or_weight_tuning':True,'no_portfolio_authority':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_complete_month_price_panel_sha256':base.source_hash(close)},'tests':tests,'decision':'P46_P36_CAUSAL_ENTRY_DELAY_SUPPORTED' if supported else 'P46_P36_CAUSAL_ENTRY_DELAY_WEAK'}
    Path('artifacts').mkdir(exist_ok=True)
    Path('artifacts/p46_p36_causal_entry_delay_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps({'decision':out['decision'],'tests':{d:{bp:{'excess':v['excess_cagr'],'folds':v['positive_folds'],'months':v['months']} for bp,v in z.items()} for d,z in tests.items()}},sort_keys=True))
if __name__=='__main__': main()

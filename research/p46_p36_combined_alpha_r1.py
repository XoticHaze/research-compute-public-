from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_temporal_factor_discriminators_r1 as p46

def cagr(r):
    r=pd.Series(r,dtype=float).dropna()
    return float((1+r).prod()**(12/len(r))-1)

def p36_frame(close):
    m=close[['SMH','QQQ']].resample('ME').last(); mom=m.pct_change(6); prev={'SMH':0.,'QQQ':0.}; rec=[]
    for i,dt in enumerate(m.index[:-1]):
        nxt=m.index[i+1]
        if mom.loc[dt].isna().any() or m.loc[[dt,nxt],['SMH','QQQ']].isna().any().any(): continue
        pick='SMH' if mom.at[dt,'SMH']>mom.at[dt,'QQQ'] else 'QQQ'; w={'SMH':1. if pick=='SMH' else 0.,'QQQ':1. if pick=='QQQ' else 0.}; turn=.5*sum(abs(w[s]-prev[s]) for s in w)
        smh=float(m.at[nxt,'SMH']/m.at[dt,'SMH']-1); q=float(m.at[nxt,'QQQ']/m.at[dt,'QQQ']-1)
        rec.append({'date':nxt,'gross':smh if pick=='SMH' else q,'matched':.5*(smh+q),'turnover':turn}); prev=w
    return pd.DataFrame(rec).set_index('date')

def metrics(candidate, matched):
    cm=base.metrics(candidate); bm=base.metrics(matched); pos,folds=base.fold_count(candidate,matched)
    return {'candidate':cm,'matched':bm,'excess_cagr':cm['cagr']-bm['cagr'],'positive_folds':pos,'folds':folds}

def main():
    syms=tuple(dict.fromkeys((*p46.SYMBOLS,'SMH'))); close=base.load(syms)
    current_month_start=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp(); close=close.loc[close.index<current_month_start]
    a=p46.returns(close,p46.FACTORS); b=p36_frame(close); idx=a.index.intersection(b.index); a=a.loc[idx]; b=b.loc[idx]
    tests={}
    for label,ix in [('full',idx),('2022_forward',idx[idx>=pd.Timestamp('2022-01-01')])]:
        tests[label]={}
        for bp in (25,50,100):
            p46net=a.loc[ix].gross-a.loc[ix].turnover*bp/10000; p36net=b.loc[ix].gross-b.loc[ix].turnover*bp/10000
            candidate=.5*p46net+.5*p36net; matched=.5*a.loc[ix].ew+.5*b.loc[ix].matched
            tests[label][str(bp)]=metrics(candidate,matched)
    supported=tests['full']['25']['excess_cagr']>0 and tests['full']['50']['excess_cagr']>0 and tests['full']['25']['positive_folds']>=3 and tests['2022_forward']['50']['excess_cagr']>0
    out={'schema':'research.p46_p36_combined_alpha_r1','parents':['P46','P36'],'scientific_contract':{'candidate':'research-only fixed 50% P46 + 50% P36 sleeves','matched_control':'50% P46 same-universe equal weight + 50% static SMH/QQQ 50/50','costs_bps_applied_per_sleeve':[25,50,100],'windows':['full','2022-forward'],'incomplete_months_excluded':True,'fixed_blend_no_weight_tuning':True,'no_portfolio_authority':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_complete_month_price_panel_sha256':base.source_hash(close)},'window':{'start':str(idx.min().date()),'end':str(idx.max().date()),'months':len(idx)},'tests':tests,'decision':'P46_P36_COMBINED_ALPHA_SUPPORTED' if supported else 'P46_P36_COMBINED_ALPHA_NOT_SUPPORTED'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_p36_combined_alpha_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'window':out['window'],'tests':{k:{b:{'excess':v['excess_cagr'],'folds':v['positive_folds']} for b,v in x.items()} for k,x in tests.items()}},sort_keys=True))
if __name__=='__main__': main()

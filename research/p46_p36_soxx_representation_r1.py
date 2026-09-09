from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_temporal_factor_discriminators_r1 as p46

def p36_frame(close):
    m=close[['SOXX','QQQ']].resample('ME').last(); mom=m.pct_change(6); prev={'SOXX':0.,'QQQ':0.}; rec=[]
    for i,dt in enumerate(m.index[:-1]):
        nxt=m.index[i+1]
        if mom.loc[dt].isna().any() or m.loc[[dt,nxt],['SOXX','QQQ']].isna().any().any(): continue
        pick='SOXX' if mom.at[dt,'SOXX']>mom.at[dt,'QQQ'] else 'QQQ'; w={'SOXX':1. if pick=='SOXX' else 0.,'QQQ':1. if pick=='QQQ' else 0.}; turn=.5*sum(abs(w[s]-prev[s]) for s in w)
        soxx=float(m.at[nxt,'SOXX']/m.at[dt,'SOXX']-1); q=float(m.at[nxt,'QQQ']/m.at[dt,'QQQ']-1)
        rec.append({'date':nxt,'gross':soxx if pick=='SOXX' else q,'matched':.5*(soxx+q),'turnover':turn}); prev=w
    return pd.DataFrame(rec).set_index('date')

def main():
    syms=tuple(dict.fromkeys((*p46.SYMBOLS,'SOXX'))); close=base.load(syms)
    current_month_start=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp(); close=close.loc[close.index<current_month_start]
    a=p46.returns(close,p46.FACTORS); b=p36_frame(close); idx=a.index.intersection(b.index); a=a.loc[idx]; b=b.loc[idx]; tests={}
    for label,ix in [('full',idx),('2022_forward',idx[idx>=pd.Timestamp('2022-01-01')])]:
        tests[label]={}
        for bp in (25,50,100):
            cand=.5*(a.loc[ix].gross-a.loc[ix].turnover*bp/10000)+.5*(b.loc[ix].gross-b.loc[ix].turnover*bp/10000); matched=.5*a.loc[ix].ew+.5*b.loc[ix].matched
            cm=base.metrics(cand); bm=base.metrics(matched); pos,folds=base.fold_count(cand,matched)
            tests[label][str(bp)]={'candidate':cm,'matched':bm,'excess_cagr':cm['cagr']-bm['cagr'],'positive_folds':pos,'folds':folds}
    supported=tests['full']['25']['excess_cagr']>0 and tests['full']['50']['excess_cagr']>0 and tests['full']['25']['positive_folds']>=3 and tests['2022_forward']['50']['excess_cagr']>0
    out={'schema':'research.p46_p36_soxx_representation_r1','parents':['P46','P36'],'scientific_contract':{'candidate':'research-only fixed 50% P46 + 50% frozen 6m SOXX-vs-QQQ P36 representation','matched_control':'50% P46 same-universe equal weight + 50% static SOXX/QQQ 50/50','costs_bps_applied_per_sleeve':[25,50,100],'windows':['full','2022-forward'],'incomplete_months_excluded':True,'no_weight_or_parameter_tuning':True,'no_portfolio_authority':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_complete_month_price_panel_sha256':base.source_hash(close)},'window':{'start':str(idx.min().date()),'end':str(idx.max().date()),'months':len(idx)},'tests':tests,'decision':'P46_P36_SOXX_REPRESENTATION_SUPPORTED' if supported else 'P46_P36_SOXX_REPRESENTATION_NOT_SUPPORTED'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_p36_soxx_representation_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'window':out['window'],'tests':{k:{bp:{'excess':v['excess_cagr'],'folds':v['positive_folds']} for bp,v in z.items()} for k,z in tests.items()}},sort_keys=True))
if __name__=='__main__': main()

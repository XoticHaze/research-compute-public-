from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_temporal_factor_discriminators_r1 as p46

SYMS=p46.SYMBOLS

def build(close):
    panel,monthly=p46.feature_panel(close,p46.FACTORS); spy=close['SPY'].resample('ME').last(); state=spy.pct_change(6).shift(1); prev={s:0. for s in SYMS}; rows=[]
    for month in sorted(panel.month.unique()):
        b=panel[panel.month==month].sort_values(['score','symbol'],ascending=[False,True]); loc=monthly.index.get_loc(month)
        if len(b)!=len(SYMS) or not isinstance(loc,(int,np.integer)) or loc+1>=len(monthly) or pd.isna(state.reindex([month]).iloc[0]): continue
        nxt=monthly.index[loc+1]; r=monthly.loc[nxt,list(SYMS)]/monthly.loc[month,list(SYMS)]-1
        if r.isna().any(): continue
        risk_on=bool(state.loc[month]>0)
        if risk_on:
            chosen=b.head(2).symbol.tolist(); w={s:(.5 if s in chosen else 0.) for s in SYMS}
        else:
            w={s:(1.0 if s=='QQQ' else 0.) for s in SYMS}
        turn=.5*sum(abs(w[s]-prev[s]) for s in SYMS); rows.append({'date':nxt,'gross':sum(w[s]*float(r[s]) for s in SYMS),'turnover':turn,'ew':float(r.mean()),'qqq':float(r['QQQ']),'risk_on':risk_on}); prev=w
    return pd.DataFrame(rows).set_index('date')

def score(frame,original,bps):
    c=frame.gross-frame.turnover*bps/10000; o=(original.gross-original.turnover*bps/10000).reindex(frame.index); ew=frame.ew; q=frame.qqq
    cm=base.metrics(c); om=base.metrics(o); em=base.metrics(ew); qm=base.metrics(q); pe,pf=base.fold_count(c,ew); po,pof=base.fold_count(c,o)
    return {'candidate':cm,'original_p46':om,'matched_ew':em,'QQQ':qm,'excess_vs_original_cagr':cm['cagr']-om['cagr'],'excess_vs_matched_ew_cagr':cm['cagr']-em['cagr'],'excess_vs_QQQ_cagr':cm['cagr']-qm['cagr'],'positive_folds_vs_ew':pe,'folds_vs_ew':pf,'positive_folds_vs_original':po,'folds_vs_original':pof,'mean_invested_in_original_p46':float(frame.risk_on.mean())}

def main():
    close=base.load(SYMS); hybrid=build(close); original=p46.returns(close,p46.FACTORS); tests={}
    for label,fr in [('full',hybrid),('2022_forward',hybrid.loc[pd.Timestamp('2022-01-01'):])]:
        tests[label]={str(b):score(fr,original,b) for b in (25,50,100)}
    f50=tests['full']['50']; h50=tests['2022_forward']['50']; supported=f50['excess_vs_original_cagr']>0 and f50['excess_vs_QQQ_cagr']>0 and h50['excess_vs_original_cagr']>0 and h50['excess_vs_matched_ew_cagr']>0
    out={'schema':'research.p46_riskoff_qqq_mutation_r1','parent':'P46','scientific_contract':{'risk_on':'unchanged P46 four-factor top-2 monthly selection','risk_off':'QQQ 100% only when prior SPY six-month return sign is non-positive, lagged one month','costs_bps':[25,50,100],'comparators':['original P46','same-universe equal weight','QQQ'],'holdout':'2022-forward','no_parameter_tuning':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_price_panel_sha256':base.source_hash(close)},'tests':tests,'decision':'P46_RISKOFF_QQQ_MUTATION_SUPPORTED' if supported else 'P46_RISKOFF_QQQ_MUTATION_NOT_SUPPORTED'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_riskoff_qqq_mutation_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'full50':f50,'recent50':h50},sort_keys=True))
if __name__=='__main__': main()

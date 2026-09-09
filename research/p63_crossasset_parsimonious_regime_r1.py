from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base

SYMS=tuple(base.UNIVERSES['crossasset'])

def frame():
    close=base.load(SYMS); m=close.resample('ME').last(); mom=m.pct_change(6); trend=(close/close.rolling(200,min_periods=160).mean()-1).resample('ME').last(); prev={s:0.0 for s in SYMS}; rec=[]
    for dt in m.index:
        b=pd.DataFrame({'mom6':mom.loc[dt,list(SYMS)],'trend200':trend.loc[dt,list(SYMS)]},index=list(SYMS))
        if b.isna().any().any(): continue
        sc=b.rank(axis=0,pct=True,method='average').mean(axis=1); loc=m.index.get_loc(dt)
        if not isinstance(loc,(int,np.integer)) or loc+1>=len(m): continue
        nxt=m.index[loc+1]; r=m.loc[nxt,list(SYMS)]/m.loc[dt,list(SYMS)]-1
        if r.isna().any(): continue
        chosen=sc.sort_values(ascending=False).head(2).index.tolist(); w={s:(0.5 if s in chosen else 0.0) for s in SYMS}; to=0.5*sum(abs(w[s]-prev[s]) for s in SYMS)
        rec.append({'date':nxt,'feature_date':dt,'gross':sum(w[s]*float(r[s]) for s in SYMS),'ew':float(r.mean()),'turnover':to}); prev=w
    return pd.DataFrame(rec).set_index('date'),close

def main():
    fr,close=frame(); spy=close['SPY']; state=(spy>spy.rolling(200,min_periods=160).mean()).resample('ME').last(); tests={}
    for bp in (25,50):
        cand=fr.gross-fr.turnover*bp/10000; ex=cand-fr.ew; rows={}
        feature_state=pd.Series([state.get(pd.Timestamp(x),pd.NA) for x in fr.feature_date],index=fr.index,dtype='boolean')
        for label,mask in (('risk_on',feature_state==True),('risk_off',feature_state==False)):
            keep=mask.fillna(False); c=cand[keep]; b=fr.ew[keep]; cm,bm=base.metrics(c),base.metrics(b)
            rows[label]={'months':int(keep.sum()),'annualized_mean_excess':float((c-b).mean()*12),'candidate':cm,'matched_ew':bm,'excess_cagr':cm['cagr']-bm['cagr']}
        strong=ex.nlargest(5).index; keep=~fr.index.isin(strong); cm,bm=base.metrics(cand[keep]),base.metrics(fr.ew[keep]); rows['remove_five_strongest_relative_months']={'months':int(keep.sum()),'removed':[str(pd.Timestamp(x).date()) for x in strong],'candidate':cm,'matched_ew':bm,'excess_cagr':cm['cagr']-bm['cagr']}
        tests[str(bp)]=rows
    out={'schema':'research.p63_crossasset_parsimonious_regime_r1','parents':['P46','P57'],'hypothesis':'P57 alpha is not merely a risk-state or five-extreme-month artifact.','scientific_contract':{'universe':list(SYMS),'factors':['mom6','trend200'],'top_k':2,'cadence':'monthly','costs_bps':[25,50],'regime':'feature-month SPY above causal 200d SMA','concentration_test':'remove five strongest candidate-minus-matched months','no_parameter_tuning':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_price_panel_sha256':base.source_hash(close)},'tests':tests}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p63_crossasset_parsimonious_regime_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps({bp:{k:{'months':v['months'],'excess_cagr':v['excess_cagr']} for k,v in rows.items()} for bp,rows in tests.items()},sort_keys=True))
if __name__=='__main__': main()

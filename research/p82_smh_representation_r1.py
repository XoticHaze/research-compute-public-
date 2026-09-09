from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p66_combination_serial_persistence_r1 as p66
import p82_rolling_chronology_r1 as roll

BP=50; DELAY=5; START=pd.Timestamp('2015-01-01')


def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')


def smh_frame():
    close=base.load(('SMH',)).dropna(subset=['SMH','QQQ']).sort_index(); idx=close.index
    mes=pd.Series(idx,index=idx).groupby(idx.to_period('M')).max().tolist(); mes=[pd.Timestamp(x) for x in mes]; m=close.loc[mes]
    rel=m['SMH'].pct_change(6)-m['QQQ'].pct_change(6); sig={pd.Timestamp(dt):(1.0 if rel.loc[dt]>0 else 0.0) for dt in m.index if pd.notna(rel.loc[dt])}
    labels=list(sig); rec=[]; prev=None
    for i in range(len(labels)-1):
        dt,nxt=labels[i],labels[i+1]; a=idx.get_indexer([dt],method='pad')[0]+DELAY; z=idx.get_indexer([nxt],method='pad')[0]+DELAY
        if min(a,z)<0 or max(a,z)>=len(idx): continue
        w=sig[dt]; sr=float(close.iloc[z]['SMH']/close.iloc[a]['SMH']-1); qr=float(close.iloc[z]['QQQ']/close.iloc[a]['QQQ']-1); turn=1.0 if prev is None else abs(w-prev)
        rec.append((idx[z],w*sr+(1-w)*qr-turn*BP/10000,0.5*sr+0.5*qr,qr)); prev=w
    return pd.DataFrame(rec,columns=['date','p36','p36_matched','qqq']).set_index('date'),close


def blend():
    p64,_=p66.frame(BP); p36,close=smh_frame(); a=p64[['candidate','matched']].copy(); a.index=a.index.to_period('M'); a.columns=['p64','p64_matched']; b=p36.copy(); b.index=b.index.to_period('M')
    f=a.join(b,how='inner'); f.index=f.index.to_timestamp('M'); f['candidate']=.5*f.p64+.5*f.p36; f['matched']=.5*f.p64_matched+.5*f.p36_matched; return f,close


def folds(q):
    out=[]
    for i,ids in enumerate(np.array_split(np.arange(len(q)),5),1):
        z=q.iloc[ids]; out.append({'fold':i,'excess_vs_matched':cagr(z.candidate)-cagr(z.matched),'excess_vs_qqq':cagr(z.candidate)-cagr(z.qqq)})
    return out


def main():
    f,close=blend(); q=f.loc[f.index>=START].dropna(); fs=folds(q); r36=roll.rolling_excess(q,36)
    out={'schema':'research.p82_smh_representation_r1','parent':'P82','hypothesis':'If P82 delayed blend economics are not specific to the SOXX semiconductor representation, replacing only the P36 semiconductor ETF with SMH while freezing signal logic, P64 sleeve, weights, five-day delay and 50-bps costs should retain matched and QQQ excess with meaningful chronology.','scientific_contract':{'p36_representation':'SMH versus QQQ 6-month relative momentum','p64_sleeve':'unchanged','sleeve_weights':[0.5,0.5],'execution_delay_trading_days':DELAY,'component_cost_bps':BP,'start':'2015-01-01','controls':['same fixed blend using static SMH/QQQ matched sleeve','QQQ'],'chronological_folds':5,'rolling_window_months':36,'no_signal_weight_delay_or_parameter_tuning':True},'aggregate':{'months':len(q),'candidate_cagr':cagr(q.candidate),'matched_cagr':cagr(q.matched),'qqq_cagr':cagr(q.qqq),'excess_vs_matched':cagr(q.candidate)-cagr(q.matched),'excess_vs_qqq':cagr(q.candidate)-cagr(q.qqq)},'folds':fs,'positive_folds_vs_matched':sum(x['excess_vs_matched']>0 for x in fs),'positive_folds_vs_qqq':sum(x['excess_vs_qqq']>0 for x in fs),'rolling_36m':r36,'source':{'provider':'Yahoo Finance via yfinance; research-only','panel_sha256':base.source_hash(close)}}
    out['decision']='P82_SMH_REPRESENTATION_SUPPORTED' if out['aggregate']['excess_vs_matched']>0 and out['aggregate']['excess_vs_qqq']>0 and out['positive_folds_vs_matched']>=3 and r36['positive_share_vs_matched']>=.5 else 'P82_SMH_REPRESENTATION_WEAK'
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p82_smh_representation_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()

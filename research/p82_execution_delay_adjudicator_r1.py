from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p66_combination_serial_persistence_r1 as p66

BP=50
DELAYS=(1,2,3,5)
WINDOWS={'full':'2005-01-01','2015_forward':'2015-01-01','2022_forward':'2022-01-01'}

def cagr(r):
    r=pd.Series(r,dtype=float).dropna()
    return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')

def mdd(r):
    r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod()
    return float((e/e.cummax()-1).min()) if len(e) else float('nan')

def p36_frame(delay:int):
    close=base.load(('SOXX',)).dropna(subset=['SOXX','QQQ']).sort_index(); idx=close.index
    mes=pd.Series(idx,index=idx).groupby(idx.to_period('M')).max().tolist(); mes=[pd.Timestamp(x) for x in mes]
    m=close.loc[mes]
    rel=m['SOXX'].pct_change(6)-m['QQQ'].pct_change(6)
    sig={pd.Timestamp(dt):(1.0 if rel.loc[dt]>0 else 0.0) for dt in m.index if pd.notna(rel.loc[dt])}
    labels=list(sig); rec=[]; prev=None
    for i in range(len(labels)-1):
        dt,nxt=labels[i],labels[i+1]
        a0=idx.get_indexer([dt],method='pad')[0]+delay; z0=idx.get_indexer([nxt],method='pad')[0]+delay
        if a0<0 or z0<0 or a0>=len(idx) or z0>=len(idx): continue
        w=sig[dt]
        ar=float(close.iloc[z0]['SOXX']/close.iloc[a0]['SOXX']-1)
        qr=float(close.iloc[z0]['QQQ']/close.iloc[a0]['QQQ']-1)
        turn=1.0 if prev is None else abs(w-prev)
        rec.append((idx[z0],w*ar+(1-w)*qr-turn*BP/10000,0.5*ar+0.5*qr,qr))
        prev=w
    return pd.DataFrame(rec,columns=['date','p36','p36_matched','qqq']).set_index('date'),close

def blend(delay:int):
    p64,_=p66.frame(BP); p36,close=p36_frame(delay)
    a=p64[['candidate','matched']].copy(); a.index=a.index.to_period('M'); a.columns=['p64','p64_matched']
    b=p36[['p36','p36_matched','qqq']].copy(); b.index=b.index.to_period('M')
    f=a.join(b,how='inner'); f.index=f.index.to_timestamp('M')
    f['candidate']=0.5*f.p64+0.5*f.p36
    f['matched']=0.5*f.p64_matched+0.5*f.p36_matched
    return f,close

def evaluate(q):
    folds=[]
    for i,ids in enumerate(np.array_split(np.arange(len(q)),5),1):
        z=q.iloc[ids]
        if len(z): folds.append({'fold':i,'vs_matched':cagr(z.candidate)-cagr(z.matched),'vs_qqq':cagr(z.candidate)-cagr(z.qqq)})
    return {'months':len(q),'candidate_cagr':cagr(q.candidate),'matched_cagr':cagr(q.matched),'qqq_cagr':cagr(q.qqq),'excess_vs_matched':cagr(q.candidate)-cagr(q.matched),'excess_vs_qqq':cagr(q.candidate)-cagr(q.qqq),'candidate_mdd':mdd(q.candidate),'matched_mdd':mdd(q.matched),'qqq_mdd':mdd(q.qqq),'positive_folds_vs_matched':sum(x['vs_matched']>0 for x in folds),'positive_folds_vs_qqq':sum(x['vs_qqq']>0 for x in folds),'folds':folds}

def main():
    out={'schema':'research.p82_execution_delay_adjudicator_r1','parent':'P82','hypothesis':'The fixed P82 50/50 P64 + P36 SOXX blend retains economically meaningful after-cost excess when realistic execution is delayed beyond the already-supported one-trading-day implementation, without retuning weights or signals.','scientific_contract':{'component_cost_bps':BP,'sleeve_weights':[0.5,0.5],'p36_signal':'unchanged 6-month SOXX minus QQQ relative momentum at month end','execution_delays_trading_days':list(DELAYS),'windows':WINDOWS,'matched_control':'same fixed blend of P64 matched control and static SOXX/QQQ control','opportunity_control':'QQQ','chronological_folds':5,'no_parameter_or_weight_tuning':True},'delays':{}}
    source_hashes={}
    for d in DELAYS:
        f,close=blend(d); source_hashes[str(d)]=base.source_hash(close); tests={}
        for name,start in WINDOWS.items(): tests[name]=evaluate(f.loc[f.index>=pd.Timestamp(start)].copy())
        out['delays'][str(d)]=tests
    out['source']={'provider':'Yahoo Finance via yfinance; research-only','panel_sha256_by_delay':source_hashes}
    recent=out['delays']['5']['2022_forward']
    out['decision']='P82_DELAY_ROBUSTNESS_SUPPORTED' if recent['excess_vs_matched']>0 and recent['excess_vs_qqq']>0 and recent['positive_folds_vs_matched']>=3 else 'P82_IMPLEMENTATION_DELAY_WEAKNESS'
    Path('artifacts').mkdir(exist_ok=True)
    Path('artifacts/p82_execution_delay_adjudicator_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps(out,sort_keys=True))

if __name__=='__main__': main()

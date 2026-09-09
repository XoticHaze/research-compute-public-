#!/usr/bin/env python3
import hashlib, json, os
from pathlib import Path
import numpy as np
import pandas as pd
os.environ.setdefault('P36_ASSET','SOXX'); os.environ.setdefault('P36_CHILD','C2')
import p36_independent_proxy_validation as base

ASSET='SOXX'; BP=50; DELAYS=(1,3); REPEATS=6; TOL=0.001

def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')

def evaluate(px):
    common=pd.concat(px,axis=1,join='inner').dropna().sort_index()
    month_ends=pd.Series(common.index,index=common.index).groupby(common.index.to_period('M')).max().tolist(); month_ends=[pd.Timestamp(x) for x in month_ends]
    m=common.loc[month_ends]; rel=m[ASSET].pct_change(6)-m['QQQ'].pct_change(6)
    sig={pd.Timestamp(dt):(1.0 if rel.loc[dt]>0 else 0.0) for dt in m.index if pd.notna(rel.loc[dt])}
    labels=[dt for dt in m.index if dt in sig]; idx=common.index; out={}
    fp=hashlib.sha256(pd.Series(sig).to_csv(float_format='%.1f').encode()).hexdigest()
    for delay in DELAYS:
        rec=[]; prev=None
        for i in range(len(labels)-1):
            dt,nxt=labels[i],labels[i+1]
            a0=idx.get_indexer([dt],method='pad')[0]+delay; z0=idx.get_indexer([nxt],method='pad')[0]+delay
            if a0<0 or z0<0 or z0>=len(idx): continue
            w=sig[dt]; ar=float(common.iloc[z0][ASSET]/common.iloc[a0][ASSET]-1); qr=float(common.iloc[z0]['QQQ']/common.iloc[a0]['QQQ']-1)
            gross=w*ar+(1-w)*qr; turn=1.0 if prev is None else abs(w-prev); net=gross-turn*BP/10000.0; matched=0.5*ar+0.5*qr
            rec.append((idx[z0],net,matched)); prev=w
        f=pd.DataFrame(rec,columns=['date','candidate','matched']).set_index('date')
        out[str(delay)]={'months':len(f),'candidate_cagr':cagr(f.candidate),'matched_cagr':cagr(f.matched),'excess_cagr':cagr(f.candidate)-cagr(f.matched),'return_fingerprint':hashlib.sha256(f.to_csv(date_format='%Y-%m-%d',float_format='%.12g').encode()).hexdigest()}
    return fp,out

def main():
    pulls=[]
    for n in range(REPEATS):
        px={}; src={}
        for s in (ASSET,'QQQ'): px[s],src[s]=base.yahoo(s)
        sfp,e=evaluate(px); pulls.append({'repeat':n+1,'sources':src,'signal_fingerprint':sfp,'economics':e})
    ranges={}; stable=True
    for d in DELAYS:
        vals=[p['economics'][str(d)]['excess_cagr'] for p in pulls]; fps=[p['economics'][str(d)]['return_fingerprint'] for p in pulls]
        ranges[str(d)]={'min_excess_cagr':min(vals),'max_excess_cagr':max(vals),'span':max(vals)-min(vals),'all_positive':all(v>0 for v in vals),'unique_return_fingerprints':len(set(fps))}
        if not all(v>0 for v in vals) or max(vals)-min(vals)>TOL: stable=False
    out={'schema':'research.p36_soxx_source_economic_repeatability_r1','parent':'P36','scientific_contract':{'representation':'SOXX_vs_QQQ','model':'unchanged six-month relative momentum selector','cost_bps':BP,'entry_delays_trading_days':list(DELAYS),'matched_control':'same shifted intervals static 50/50 SOXX+QQQ','identical_source_pull_repeats':REPEATS,'material_excess_cagr_tolerance':TOL,'no_parameter_tuning':True},'pulls':pulls,'ranges':ranges,'unique_signal_fingerprints':len(set(p['signal_fingerprint'] for p in pulls)),'decision':'P36_SOXX_SOURCE_ECONOMICS_STABLE_WITHIN_TEST' if stable else 'P36_SOXX_MUTABLE_SOURCE_ECONOMICALLY_MATERIAL'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p36_soxx_source_economic_repeatability_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()

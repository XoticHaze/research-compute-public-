#!/usr/bin/env python3
import json, os
from pathlib import Path
import numpy as np
import pandas as pd
os.environ.setdefault('P36_CHILD','C2')
import p36_independent_proxy_validation as base

ASSET=os.environ['P36_ASSET'].strip().upper()
if ASSET not in {'SOXX','XSD'}: raise SystemExit(f'unsupported asset {ASSET}')
COSTS=(25,50,100); DELAYS=(1,3,5)

def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')

def main():
    syms=[ASSET,'QQQ']; px={}; src={}
    for s in syms: px[s],src[s]=base.yahoo(s)
    common=pd.concat(px,axis=1,join='inner').dropna().sort_index()
    month_ends=pd.Series(common.index,index=common.index).groupby(common.index.to_period('M')).max().tolist(); month_ends=[pd.Timestamp(x) for x in month_ends]
    m=common.loc[month_ends]
    # Exact alignment with the released P36 validator: its shifted signal at return-month t is
    # the unshifted 6m relative-momentum observation available at the PRIOR month-end.
    # Therefore causal execution delay must begin after that prior month-end, not one month later.
    rel=m[ASSET].pct_change(6)-m['QQQ'].pct_change(6)
    sig={pd.Timestamp(dt):(1.0 if rel.loc[dt]>0 else 0.0) for dt in m.index if pd.notna(rel.loc[dt])}
    rows=[]; idx=common.index; labels=[dt for dt in m.index if dt in sig]
    for delay in DELAYS:
        for bp in COSTS:
            rec=[]; prev=None
            for i in range(len(labels)-1):
                dt,nxt=labels[i],labels[i+1]
                a0=idx.get_indexer([dt],method='pad')[0]+delay; z0=idx.get_indexer([nxt],method='pad')[0]+delay
                if a0<0 or z0<0 or z0>=len(idx): continue
                w=sig[dt]; ar=float(common.iloc[z0][ASSET]/common.iloc[a0][ASSET]-1); qr=float(common.iloc[z0]['QQQ']/common.iloc[a0]['QQQ']-1)
                gross=w*ar+(1-w)*qr; turn=1.0 if prev is None else abs(w-prev); net=gross-turn*bp/10000.0; matched=0.5*ar+0.5*qr
                rec.append((idx[z0],net,matched)); prev=w
            f=pd.DataFrame(rec,columns=['date','candidate','matched']).set_index('date'); pos=0
            for ids in np.array_split(np.arange(len(f)),5):
                q=f.iloc[ids]
                if len(q): pos += cagr(q.candidate)>cagr(q.matched)
            rows.append({'delay_days':delay,'cost_bps':bp,'months':len(f),'candidate_cagr':cagr(f.candidate),'matched_cagr':cagr(f.matched),'excess_cagr':cagr(f.candidate)-cagr(f.matched),'positive_folds':int(pos),'start':str(f.index.min().date()),'end':str(f.index.max().date())})
    key={(r['delay_days'],r['cost_bps']):r for r in rows}; support=key[(1,50)]['excess_cagr']>0 and key[(1,50)]['positive_folds']>=3 and key[(3,50)]['excess_cagr']>0
    out={'schema':'research.p36_causal_entry_delay_r1','parent':'P36','asset':ASSET,'scientific_contract':{'economics':'unchanged six-month relative momentum asset-vs-QQQ monthly selector','released_validator_alignment':'unshifted signal at month-end t maps to released shifted-signal return month t+1','entry_delays_trading_days':list(DELAYS),'costs_bps':list(COSTS),'matched_control':'same shifted intervals static 50/50 asset+QQQ','no_parameter_tuning':True},'supersedes_run_interpretation':{'run_id':34329700307,'classification':'HARNESS_INCOMPATIBLE','reason':'prior attempt accidentally applied the released one-month signal shift and then delayed from that later label, adding an unintended extra month'},'sources':src,'tests':rows,'decision':'P36_CAUSAL_EXECUTION_DELAY_SUPPORTED' if support else 'P36_CAUSAL_EXECUTION_DELAY_WEAK'}
    Path('artifacts').mkdir(exist_ok=True); Path(f'artifacts/p36_{ASSET.lower()}_causal_delay_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()

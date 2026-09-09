#!/usr/bin/env python3
import json, os
from pathlib import Path
import numpy as np
import pandas as pd
os.environ.setdefault('P36_CHILD','C2')
import p36_independent_proxy_validation as base

ASSET=os.environ.get('P36_ASSET','SOXX').strip().upper()
if ASSET not in {'SOXX','XSD'}: raise SystemExit(f'unsupported asset {ASSET}')
BP=50; N=2000; SEED=360036; WINDOWS={'2015_forward':'2015-01-01','2020_forward':'2020-01-01'}

def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')

def build():
    px={}; src={}
    for s in [ASSET,'QQQ']: px[s],src[s]=base.yahoo(s)
    common=pd.concat(px,axis=1,join='inner').dropna().sort_index()
    month_ends=pd.Series(common.index,index=common.index).groupby(common.index.to_period('M')).max().tolist(); m=common.loc[[pd.Timestamp(x) for x in month_ends]]
    rel=m[ASSET].pct_change(6)-m['QQQ'].pct_change(6)
    rows=[]
    for i in range(len(m)-1):
        dt,nxt=m.index[i],m.index[i+1]
        if pd.isna(rel.loc[dt]): continue
        ar=float(m.loc[nxt,ASSET]/m.loc[dt,ASSET]-1); qr=float(m.loc[nxt,'QQQ']/m.loc[dt,'QQQ']-1)
        rows.append((nxt,1 if rel.loc[dt]>0 else 0,ar,qr))
    return pd.DataFrame(rows,columns=['date','signal','asset_ret','qqq_ret']).set_index('date'),src

def path(q,sig):
    prev=None; cand=[]; matched=[]
    for (_,r),w in zip(q.iterrows(),sig):
        gross=w*r.asset_ret+(1-w)*r.qqq_ret; turn=1.0 if prev is None else abs(float(w)-float(prev)); cand.append(gross-turn*BP/10000); matched.append(0.5*r.asset_ret+0.5*r.qqq_ret); prev=w
    return cagr(cand)-cagr(matched)

def folds(q):
    out=[]
    for ids in np.array_split(np.arange(len(q)),5):
        z=q.iloc[ids]; out.append(path(z,z.signal.to_numpy()))
    return out

def main():
    f,src=build(); rng=np.random.default_rng(SEED); out={'schema':'research.p36_signal_permutation_null_r1','parent':'P36','asset':ASSET,'scientific_contract':{'economics':'unchanged six-month relative momentum asset-vs-QQQ monthly selector','cost_bps':BP,'matched_control':'static 50/50 asset+QQQ on identical months','null':'permute observed binary monthly selection labels across the same realized return months','replications':N,'seed':SEED,'windows':WINDOWS,'no_parameter_tuning':True},'sources':src,'windows':{}}
    for name,start in WINDOWS.items():
        q=f.loc[pd.Timestamp(start):]; actual=path(q,q.signal.to_numpy()); fs=folds(q); null=np.array([path(q,rng.permutation(q.signal.to_numpy())) for _ in range(N)],dtype=float)
        out['windows'][name]={'months':len(q),'actual_excess_cagr':actual,'positive_folds':int(sum(x>0 for x in fs)),'fold_excess':fs,'null_mean':float(null.mean()),'null_p05':float(np.quantile(null,.05)),'null_p95':float(np.quantile(null,.95)),'p_null_ge_actual':float(np.mean(null>=actual)),'actual_percentile':float(np.mean(null<actual))}
    z=out['windows']['2020_forward']; out['decision']='P36_SIGNAL_TIMING_SUPPORTED_AGAINST_PERMUTATION_NULL' if z['actual_excess_cagr']>0 and z['positive_folds']>=3 and z['p_null_ge_actual']<=.05 else 'P36_SIGNAL_TIMING_NOT_DISTINGUISHED_FROM_PERMUTATION_NULL'
    Path('artifacts').mkdir(exist_ok=True); Path(f'artifacts/p36_{ASSET.lower()}_signal_permutation_null_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()

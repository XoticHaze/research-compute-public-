from __future__ import annotations
import hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
import p13_semiconductor_stock_specific_residual as p13
import p13_twofactor_residual_r1 as tf

def phash(close):
    x=close.sort_index().sort_index(axis=1).copy(); payload=x.to_csv(date_format='%Y-%m-%d',float_format='%.12g').encode(); return hashlib.sha256(payload).hexdigest()
def cagr(x):
    x=np.asarray(x,float); return float(np.prod(1+x)**(12/len(x))-1)
def candidate(close):
    pos=p13.month_end_indices(close.index); rows=[]
    for j in range(len(pos)-1):
        sig,nxt=pos[j],pos[j+1]; entry,exit_=sig+1,nxt+1
        if sig<p13.LOOKBACK or exit_>=len(close) or close.index[entry]<pd.Timestamp('2019-01-01'): continue
        raw={}; one={}; two={}
        for n in p13.UNIVERSE:
            now,then=close.iloc[sig][n],close.iloc[sig-p13.LOOKBACK][n]
            if np.isfinite(now) and np.isfinite(then) and then>0: raw[n]=float(now/then-1)
            s1=p13.stock_specific_residual_score(close,n,sig); s2=tf.score_twofactor(close,n,sig)
            if np.isfinite(s1): one[n]=s1
            if np.isfinite(s2): two[n]=s2
        common=set(raw).intersection(one).intersection(two)
        if len(common)<8: continue
        pick=sorted(common,key=lambda n:two[n],reverse=True)[:p13.TOP_N]; r=p13.basket_return(close,pick,entry,exit_)
        if np.isfinite(r): rows.append((close.index[entry],r-.005))
    f=pd.DataFrame(rows,columns=['entry','ret']); recent=f[f.entry>=pd.Timestamp('2022-01-01')]
    return {'months':len(f),'full_cagr':cagr(f.ret),'recent_months':len(recent),'2022_forward_cagr':cagr(recent.ret)}
def pull(threads):
    tickers=p13.UNIVERSE+p13.BENCHMARKS; raw=yf.download(tickers,start=p13.START,end=p13.END,auto_adjust=True,progress=False,group_by='column',threads=threads)
    if raw.empty or not isinstance(raw.columns,pd.MultiIndex): raise SystemExit('download unavailable')
    close=raw['Close'].copy().sort_index().dropna(how='all'); return {'threads':threads,'hash':phash(close),'shape':[int(close.shape[0]),int(close.shape[1])],'na_cells':int(close.isna().sum().sum()),'candidate':candidate(close)}
def main():
    pulls=[pull(True) for _ in range(3)]+[pull(False) for _ in range(3)]; hashes=[x['hash'] for x in pulls]; cagrs=[x['candidate']['2022_forward_cagr'] for x in pulls]; stable=len(set(hashes))==1 and max(cagrs)-min(cagrs)<1e-12
    out={'schema':'research.p13_source_repeatability_r1','parent':'P13','scientific_contract':{'source':'Yahoo via yfinance 0.2.65 auto_adjust=True','same_request_repeats':6,'thread_modes':[True,False],'exact_request':[p13.START,p13.END,p13.UNIVERSE+p13.BENCHMARKS],'candidate_check':'exact frozen two-factor intersection/top3 50-bp formulation','no_parameter_search':True},'pulls':pulls,'unique_panel_hashes':len(set(hashes)),'candidate_recent_cagr_range':[min(cagrs),max(cagrs)],'decision':'P13_SOURCE_REPEATABLE_WITHIN_EXECUTION' if stable else 'P13_SOURCE_OR_REQUEST_NOT_REPEATABLE'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p13_source_repeatability_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()

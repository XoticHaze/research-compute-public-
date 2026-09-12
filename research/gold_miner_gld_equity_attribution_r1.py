from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

TICKERS=["GDX","RING","GLD","SPY"]
START="2013-01-01"; END="2026-09-12"; COST=0.0025
OUT=Path("research/artifacts/gold_miner_gld_equity_attribution_r1.json")


def prep(close):
    r=close.resample("ME").last().pct_change(fill_method=None).dropna()
    for c in r.columns:
        if len(r[c])>=2:
            r.iloc[0,r.columns.get_loc(c)]-=COST
            r.iloc[-1,r.columns.get_loc(c)]-=COST
    return r


def fit(q,target):
    q=q[[target,"GLD","SPY"]].dropna()
    if len(q)<24:return {"months":len(q),"annualized_alpha":None,"alpha_t":None,"betas":{}}
    y=q[target].to_numpy(float); X=np.c_[np.ones(len(q)),q[["GLD","SPY"]].to_numpy(float)]
    b,*_=np.linalg.lstsq(X,y,rcond=None); e=y-X@b; dof=len(y)-3
    s2=float(e@e/dof); cov=s2*np.linalg.inv(X.T@X); se=float(np.sqrt(cov[0,0]))
    return {"months":int(len(q)),"annualized_alpha":float(b[0]*12),"alpha_t":float(b[0]/se) if se>0 else None,"betas":{"GLD":float(b[1]),"SPY":float(b[2])}}


def main():
    raw=yf.download(TICKERS,start=START,end=END,auto_adjust=True,progress=False,threads=False)
    if raw.empty: raise SystemExit("SOURCE_FAILURE_EMPTY")
    close=raw["Close"] if isinstance(raw.columns,pd.MultiIndex) else raw
    r=prep(close[TICKERS].dropna().astype(float))
    windows={"early_2013_2017":("2013-01-01","2017-12-31"),"middle_2018_2021":("2018-01-01","2021-12-31"),"recent_2022_plus":("2022-01-01",None)}
    results={}
    for t in ["GDX","RING"]:
        per={k:fit(r.loc[a:b],t) for k,(a,b) in windows.items()}
        full=fit(r,t); positives=sum((v["annualized_alpha"] or -999)>0 for v in per.values())
        results[t]={"full":full,"windows":per,"positive_windows":positives}
    passed=all((results[t]["full"]["annualized_alpha"] or -999)>0 and results[t]["positive_windows"]>=2 and (results[t]["windows"]["recent_2022_plus"]["annualized_alpha"] or -999)>0 for t in ["GDX","RING"])
    decision="GOLD_MINER_PRODUCER_RESIDUAL_SUPPORTED" if passed else "GOLD_MINER_PRODUCER_RESIDUAL_NOT_SUPPORTED"
    out={"schema":"research.gold_miner_gld_equity_attribution_r1.v1","workload_id":"GOLD_MINER_GLD_EQUITY_ATTRIBUTION_R1","parent":"CC-RF-GOLD-MINER-ATTRIBUTION-003","claim":"GDX and RING retain positive producer-over-metal residual alpha after fixed GLD plus SPY attribution across chronology, including the preserved early GDX window.","contract":{"symbols":TICKERS,"start":START,"end_exclusive":END,"endpoint_cost_bps_each":25,"factors":["GLD","SPY"],"windows":windows,"support_gate":"both implementations full alpha >0, recent 2022+ alpha >0, and at least 2/3 fixed windows positive; no miner/factor/date/cost rescue","parameter_search":False},"common_sample":{"months":int(len(r)),"first_month":str(r.index.min().date()),"last_month":str(r.index.max().date())},"results":results,"decision":decision,"scientific_consequence":"Preserve miner producer-over-metal residual as independently supported across both frozen implementations; continue only orthogonal falsification." if passed else "Reject the stronger independent producer-alpha claim under fixed GLD+SPY attribution. Preserve narrower historical miner evidence without miner, factor, date, or cost rescue.","boundaries":{"scientific_authority":True,"portfolio_ranking":False,"allocation_authority":False,"runtime":False,"broker":False,"live_trading":False}}
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps({"decision":decision,"GDX_full_alpha_pct":round((results['GDX']['full']['annualized_alpha'] or 0)*100,3),"RING_full_alpha_pct":round((results['RING']['full']['annualized_alpha'] or 0)*100,3),"GDX_positive_windows":results['GDX']['positive_windows'],"RING_positive_windows":results['RING']['positive_windows']},sort_keys=True))
if __name__=="__main__":main()

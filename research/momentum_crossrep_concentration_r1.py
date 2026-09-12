from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

PAIRS={"SPMO":"SPY","XMMO":"MDY","XSMO":"IJR","IDMO":"EFA"}
START="2016-01-01"; END="2026-09-12"; COST=0.0025; TAIL_FRAC=0.05
OUT=Path("research/artifacts/momentum_crossrep_concentration_r1.json")

def cagr(s):
    x=s.dropna().to_numpy(float)
    if len(x)<24:return None
    w=float(np.prod(1+x)); return None if w<=0 else w**(12/len(x))-1

def one(r,fund,ctl):
    q=r[[fund,ctl]].dropna().copy(); ex=q[fund]-q[ctl]
    n=max(1,int(math.ceil(len(q)*TAIL_FRAC))); strongest=ex.nlargest(n).index
    trimmed=q.drop(index=strongest)
    full_ex=(cagr(q[fund])-cagr(q[ctl])) if cagr(q[fund]) is not None and cagr(q[ctl]) is not None else None
    trim_ex=(cagr(trimmed[fund])-cagr(trimmed[ctl])) if cagr(trimmed[fund]) is not None and cagr(trimmed[ctl]) is not None else None
    blocks={}
    for name,a,b in [("2016_2019","2016-01-01","2019-12-31"),("2020_2022","2020-01-01","2022-12-31"),("2023_plus","2023-01-01",None)]:
        z=q.loc[a:b]; fc=cagr(z[fund]); cc=cagr(z[ctl]); blocks[name]=None if fc is None or cc is None else fc-cc
    positive=sum(v is not None and v>0 for v in blocks.values())
    return {"months":len(q),"full_excess_cagr":full_ex,"trimmed_excess_cagr":trim_ex,"removed_months":n,"positive_blocks":positive,"blocks":blocks}

def main():
    tickers=list(dict.fromkeys([x for p in PAIRS.items() for x in p]))
    raw=yf.download(tickers,start=START,end=END,auto_adjust=True,progress=False,threads=False)
    if raw.empty:raise SystemExit("SOURCE_FAILURE_EMPTY")
    close=raw["Close"] if isinstance(raw.columns,pd.MultiIndex) else raw
    monthly=close[tickers].resample("ME").last().pct_change(fill_method=None)
    for c in monthly.columns:
        s=monthly[c].dropna()
        if len(s)>=2:
            monthly.loc[s.index[0],c]-=COST; monthly.loc[s.index[-1],c]-=COST
    results={f:one(monthly,f,c) for f,c in PAIRS.items()}
    supported=sum((v["trimmed_excess_cagr"] or -999)>0 and v["positive_blocks"]>=2 for v in results.values())
    decision="MOMENTUM_CROSSREP_CONCENTRATION_ROBUST" if supported>=3 else "MOMENTUM_CROSSREP_CONCENTRATION_NOT_ROBUST"
    out={"schema":"research.momentum_crossrep_concentration_r1.v1","workload_id":"MOMENTUM_CROSSREP_CONCENTRATION_R1","parent":"CC-RF-MOMENTUM-CAUSAL-002","claim":"Matched-control momentum excess is not explained by the strongest 5% relative months across broad-, mid-, small-cap and developed-ex-US implementations.","contract":{"pairs":PAIRS,"start":START,"end_exclusive":END,"endpoint_cost_bps_each":25,"strongest_relative_month_fraction_removed":TAIL_FRAC,"fixed_blocks":["2016-2019","2020-2022","2023+"],"support_rule":"at least 3/4 representations retain positive trimmed matched-control CAGR excess and >=2/3 positive chronology blocks; no product/date/tail-fraction rescue"},"results":results,"representations_supported":supported,"decision":decision,"scientific_consequence":"Cross-representation momentum concentration robustness survives; common momentum evidence is not confined to a few strongest matched-relative months." if supported>=3 else "Do not generalize momentum robustness across representations after strongest-period removal; preserve individual survivor evidence only, without product/date/tail rescue.","boundaries":{"scientific_authority":True,"portfolio_ranking":False,"allocation_authority":False,"runtime":False,"broker":False,"live_trading":False}}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps({"decision":decision,"representations_supported":supported,**{f:{"full_pp":round((v['full_excess_cagr'] or 0)*100,3),"trim_pp":round((v['trimmed_excess_cagr'] or 0)*100,3),"positive_blocks":v['positive_blocks']} for f,v in results.items()}},sort_keys=True))
if __name__=="__main__":main()

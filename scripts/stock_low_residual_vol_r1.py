from __future__ import annotations

import hashlib, json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import numpy as np
import pandas as pd

PANELS={
"industrial_machinery":(("CAT","DE","ETN","PH","ITW","EMR","ROK","DOV"),"XLI"),
"software":(("MSFT","ORCL","ADBE","CRM","INTU","NOW"),"IGV"),
"insurance":(("PGR","CB","ALL","TRV","AFL","MET","AIG","PRU"),"KIE"),
"retail":(("WMT","COST","TGT","LOW","HD","TJX","ROST","DG"),"XRT"),
}
START="2014-01-01"; EST=126; HOLD=21; DELAY=1; COST=50.0; FOLDS=6; MIN_TRAIN=756; PURGE=148
OUT=Path("results/stock_low_residual_vol_r1.json")

def _d(x):
 for f in ("%m/%d/%Y","%Y-%m-%d","%b %d, %Y"):
  try:return datetime.strptime(str(x).strip(),f).date()
  except ValueError:pass
 raise ValueError(x)
def _p(x):return float(str(x or '').strip().replace('$','').replace(',',''))
def load(s,etf=False):
 q=urlencode({"assetclass":"etf" if etf else "stocks","fromdate":START,"todate":(date.today()+timedelta(days=2)).isoformat(),"limit":5000})
 u=f"https://api.nasdaq.com/api/quote/{s}/historical?{q}"
 r=Request(u,headers={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/147 Safari/537.36","Accept":"application/json, text/plain, */*","Referer":f"https://www.nasdaq.com/market-activity/{'etf' if etf else 'stocks'}/{s.lower()}/historical","Origin":"https://www.nasdaq.com"})
 with urlopen(r,timeout=45) as z:p=json.loads(z.read().decode())
 rows=(((p.get('data') or {}).get('tradesTable') or {}).get('rows') or [])
 v=sorted({_d(x['date']):_p(x['close']) for x in rows}.items())
 if len(v)<1500: raise RuntimeError(f"{s}: rows={len(v)}")
 return pd.Series([x[1] for x in v],index=pd.DatetimeIndex(pd.to_datetime([x[0] for x in v],utc=True)),name=s,dtype=float)
def folds(n):
 e=np.linspace(MIN_TRAIN,n-(HOLD+DELAY+1),FOLDS+1,dtype=int);return [(int(e[i]),int(e[i+1])) for i in range(FOLDS)]
def main():
 results=[]; pooled=[]; fingerprints={}
 for name,(stocks,etf) in PANELS.items():
  raw={s:load(s,False) for s in stocks};raw[etf]=load(etf,True)
  common=raw[etf].index
  for s in stocks:common=common.intersection(raw[s].index)
  common=common.sort_values();px=pd.DataFrame({s:raw[s].reindex(common) for s in (*stocks,etf)},index=common)
  if len(common)<1500 or px.isna().any().any():raise RuntimeError(f"{name}: common/missing")
  fingerprints[name]=hashlib.sha256("\n".join(f"{d.date()}|"+"|".join(f"{px.at[d,s]:.8f}" for s in (*stocks,etf)) for d in common).encode()).hexdigest()
  ret=px.pct_change();fs=folds(len(common));rows=[]
  for fi,(a,b) in enumerate(fs,1):
   if fi<2:continue
   safe=b-(DELAY+HOLD);i=a
   while i<safe:
    hist=slice(i-EST,i);x=ret[etf].iloc[hist].to_numpy();scores={}
    if len(x)<EST or not np.isfinite(x).all(): i+=HOLD;continue
    xv=float(np.var(x));
    if xv<=1e-12:i+=HOLD;continue
    for s in stocks:
     y=ret[s].iloc[hist].to_numpy()
     if not np.isfinite(y).all():continue
     beta=float(np.cov(y,x,ddof=0)[0,1]/xv);res=y-beta*x;scores[s]=float(np.std(res,ddof=0))
    if len(scores)<4:i+=HOLD;continue
    k=max(1,int(np.ceil(len(scores)*.25)));chosen=sorted(scores,key=scores.get)[:k];ex=i+DELAY;out=ex+HOLD
    stock_ret=float(np.mean([px[s].iloc[out]/px[s].iloc[ex]-1 for s in chosen]));etf_ret=float(px[etf].iloc[out]/px[etf].iloc[ex]-1)
    row={"industry":name,"fold":fi,"chosen":chosen,"net_bps":stock_ret*10000-COST,"industry_excess_bps":(stock_ret-etf_ret)*10000};rows.append(row);pooled.append(row);i+=HOLD
  if not rows:raise RuntimeError(f"{name}: no trades")
  fr=[]
  for fi in range(2,7):
   rr=[r for r in rows if r['fold']==fi];fr.append({"fold":fi,"trades":len(rr),"net_mean_bps":None if not rr else float(np.mean([r['net_bps'] for r in rr])),"industry_excess_mean_bps":None if not rr else float(np.mean([r['industry_excess_bps'] for r in rr]))})
  net=float(np.mean([r['net_bps'] for r in rows]));ex=float(np.mean([r['industry_excess_bps'] for r in rows]));pos=sum((r['industry_excess_mean_bps'] if r['industry_excess_mean_bps'] is not None else -1e99)>0 for r in fr);passed=bool(len(rows)>=20 and net>0 and ex>0 and pos>=3)
  results.append({"industry":name,"industry_etf":etf,"periods":len(rows),"mean_net_50bps":net,"mean_matched_industry_excess_bps":ex,"positive_excess_folds":pos,"gate_pass":passed,"folds":fr})
 fam=sum(r['gate_pass'] for r in results);pooled_ex=float(np.mean([r['industry_excess_bps'] for r in pooled]))
 out={"schema":"research.stock_low_residual_vol.v1","experiment_id":"CC-RF-STOCK-LOW-RESIDUAL-VOL-001","generated_at":datetime.now(timezone.utc).isoformat(),"source":"Nasdaq raw daily close","panels":results,"pooled":{"periods":len(pooled),"mean_matched_industry_excess_bps":pooled_ex},"decision":{"passing_industries":fam,"required":3,"pooled_industry_excess_positive":pooled_ex>0,"discovery_gate_pass":bool(fam>=3 and pooled_ex>0),"promotion_blocked_by_current_panel_survivorship":True},"source_fingerprints":fingerprints,"contract":{"causal_beta_and_residual_vol_window":EST,"bottom_residual_vol_pct":.25,"delay":DELAY,"hold":HOLD,"round_trip_cost_bps":COST,"folds":FOLDS,"purge":PURGE},"boundaries":{"allocation_authority":False,"runtime_mutation":False,"live_trading_change":False}}
 OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n");print(json.dumps(out,indent=2,sort_keys=True))
if __name__=='__main__':main()

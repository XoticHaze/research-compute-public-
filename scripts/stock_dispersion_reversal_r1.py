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
START="2014-01-01"; SPY="SPY"; LOOK=20; HOLD=20; DELAY=1; COST=50.0; FOLDS=6; MIN_TRAIN=756; PURGE=22
OUT=Path("results/stock_dispersion_reversal_r1.json")

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
 with urlopen(r,timeout=45) as z: p=json.loads(z.read().decode())
 rows=(((p.get('data') or {}).get('tradesTable') or {}).get('rows') or [])
 v=sorted({_d(x['date']):_p(x['close']) for x in rows}.items())
 if len(v)<1500: raise RuntimeError(f"{s}: rows={len(v)}")
 return pd.Series([x[1] for x in v],index=pd.DatetimeIndex(pd.to_datetime([x[0] for x in v],utc=True)),name=s,dtype=float)
def folds(n):
 e=np.linspace(MIN_TRAIN,n-(HOLD+DELAY+1),FOLDS+1,dtype=int); return [(int(e[i]),int(e[i+1])) for i in range(FOLDS)]
def main():
 spy=load(SPY,True); results=[]; pooled=[]; fingerprints={}
 for name,(stocks,etf) in PANELS.items():
  raw={s:load(s,False) for s in stocks}; raw[etf]=load(etf,True)
  common=spy.index.intersection(raw[etf].index)
  for s in stocks: common=common.intersection(raw[s].index)
  common=common.sort_values()
  if len(common)<1500: raise RuntimeError(f"{name}: common={len(common)}")
  px=pd.DataFrame({s:raw[s].reindex(common) for s in (*stocks,etf)},index=common); sp=spy.reindex(common)
  if px.isna().any().any() or sp.isna().any(): raise RuntimeError(f"{name}: missing common")
  fingerprints[name]=hashlib.sha256("\n".join(f"{d.date()}|"+"|".join(f"{px.at[d,s]:.8f}" for s in (*stocks,etf))+f"|{sp.loc[d]:.8f}" for d in common).encode()).hexdigest()
  mom=px.pct_change(LOOK); rel=mom[list(stocks)].sub(mom[etf],axis=0); disp=rel.std(axis=1,ddof=0); fs=folds(len(common)); rows=[]; next_ok={s:0 for s in stocks}
  for fi,(a,b) in enumerate(fs,1):
   if fi<2: continue
   safe=b-(DELAY+HOLD); prior=disp.shift(1).iloc[:a-PURGE].dropna()
   if len(prior)<252: raise RuntimeError(f"{name} fold{fi}: prior={len(prior)}")
   gate=float(prior.quantile(.70))
   for i in range(a,safe):
    if not np.isfinite(disp.iloc[i]) or float(disp.iloc[i])<=gate: continue
    ranks=rel.iloc[i].rank(pct=True,method='average')
    for s in stocks:
     ex=i+DELAY; out=ex+HOLD
     if ex<next_ok[s] or not np.isfinite(ranks[s]) or float(ranks[s])>.25: continue
     sg=float(px[s].iloc[out]/px[s].iloc[ex]-1)*10000; eg=float(px[etf].iloc[out]/px[etf].iloc[ex]-1)*10000; bg=float(sp.iloc[out]/sp.iloc[ex]-1)*10000
     row={"industry":name,"symbol":s,"fold":fi,"net_bps":sg-COST,"industry_excess_bps":sg-eg,"spy_excess_bps":sg-bg}; rows.append(row); pooled.append(row); next_ok[s]=out
  if not rows: raise RuntimeError(f"{name}: no trades")
  fr=[]
  for fi in range(2,7):
   rr=[r for r in rows if r['fold']==fi]; fr.append({"fold":fi,"trades":len(rr),"net_mean_bps":None if not rr else float(np.mean([r['net_bps'] for r in rr])),"industry_excess_mean_bps":None if not rr else float(np.mean([r['industry_excess_bps'] for r in rr]))})
  net=float(np.mean([r['net_bps'] for r in rows])); ex=float(np.mean([r['industry_excess_bps'] for r in rows])); pos=sum((r['industry_excess_mean_bps'] if r['industry_excess_mean_bps'] is not None else -1e99)>0 for r in fr)
  passed=bool(len(rows)>=20 and net>0 and ex>0 and pos>=3)
  results.append({"industry":name,"industry_etf":etf,"trades":len(rows),"mean_net_50bps":net,"mean_matched_industry_excess_bps":ex,"positive_excess_folds":pos,"gate_pass":passed,"folds":fr})
 fam=sum(r['gate_pass'] for r in results); spy_ex=float(np.mean([r['spy_excess_bps'] for r in pooled]))
 out={"schema":"research.stock_dispersion_reversal.v1","experiment_id":"CC-RF-STOCK-DISPERSION-REVERSAL-001","generated_at":datetime.now(timezone.utc).isoformat(),"source":"Nasdaq raw daily close","panels":results,"pooled":{"trades":len(pooled),"mean_matched_spy_excess_bps":spy_ex},"decision":{"passing_industries":fam,"required":3,"pooled_spy_excess_positive":spy_ex>0,"discovery_gate_pass":bool(fam>=3 and spy_ex>0),"promotion_blocked_by_current_panel_survivorship":True},"source_fingerprints":fingerprints,"contract":{"lookback":LOOK,"dispersion_threshold_prior_q":.70,"bottom_cross_section_pct":.25,"delay":DELAY,"hold":HOLD,"round_trip_cost_bps":COST,"folds":FOLDS,"purge":PURGE},"boundaries":{"allocation_authority":False,"runtime_mutation":False,"live_trading_change":False}}
 OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n"); print(json.dumps(out,indent=2,sort_keys=True))
if __name__=='__main__':main()

from __future__ import annotations

import hashlib, itertools, json
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
START="2014-01-01"; LOOK=60; ZENTRY=2.0; HOLD=20; DELAY=1; LEG_COST_BPS=25.0; ROUND_TRIP_PAIR_COST_BPS=100.0
FOLDS=6; MIN_TRAIN=756; PURGE=82
OUT=Path("results/stock_pair_spread_reversion_r1.json")

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
 results=[]; pooled=[]; fingerprints={}
 for name,(stocks,etf) in PANELS.items():
  raw={s:load(s,False) for s in stocks}; raw[etf]=load(etf,True)
  common=raw[etf].index
  for s in stocks: common=common.intersection(raw[s].index)
  common=common.sort_values()
  if len(common)<1500: raise RuntimeError(f"{name}: common={len(common)}")
  px=pd.DataFrame({s:raw[s].reindex(common) for s in (*stocks,etf)},index=common)
  if px.isna().any().any(): raise RuntimeError(f"{name}: missing common")
  fingerprints[name]=hashlib.sha256("\n".join(f"{d.date()}|"+"|".join(f"{px.at[d,s]:.8f}" for s in (*stocks,etf)) for d in common).encode()).hexdigest()
  logs=np.log(px[list(stocks)]); fs=folds(len(common)); rows=[]; pair_next={tuple(sorted(p)):0 for p in itertools.combinations(stocks,2)}
  for fi,(a,b) in enumerate(fs,1):
   if fi<2: continue
   safe=b-(DELAY+HOLD)
   for i in range(a,safe):
    for s1,s2 in itertools.combinations(stocks,2):
     key=tuple(sorted((s1,s2)))
     if i < pair_next[key]: continue
     hist=(logs[s1]-logs[s2]).iloc[i-LOOK:i]
     if len(hist)<LOOK or not np.isfinite(hist).all(): continue
     sd=float(hist.std(ddof=0))
     if sd<=1e-12: continue
     z=float(((logs[s1].iloc[i]-logs[s2].iloc[i])-hist.mean())/sd)
     if abs(z)<ZENTRY: continue
     ex=i+DELAY; out=ex+HOLD
     r1=float(px[s1].iloc[out]/px[s1].iloc[ex]-1); r2=float(px[s2].iloc[out]/px[s2].iloc[ex]-1)
     # Dollar-neutral pair: long the relative loser, short the relative winner.
     gross_pair=((r2-r1)/2.0 if z>0 else (r1-r2)/2.0)*10000
     net=gross_pair-ROUND_TRIP_PAIR_COST_BPS
     row={"industry":name,"pair":f"{s1}/{s2}","fold":fi,"entry_z":z,"gross_pair_bps":gross_pair,"net_pair_bps":net}
     rows.append(row); pooled.append(row); pair_next[key]=out
  if not rows: raise RuntimeError(f"{name}: no trades")
  fr=[]
  for fi in range(2,7):
   rr=[r for r in rows if r['fold']==fi]
   fr.append({"fold":fi,"trades":len(rr),"net_mean_bps":None if not rr else float(np.mean([r['net_pair_bps'] for r in rr]))})
  net=float(np.mean([r['net_pair_bps'] for r in rows])); pos=sum((r['net_mean_bps'] if r['net_mean_bps'] is not None else -1e99)>0 for r in fr)
  passed=bool(len(rows)>=30 and net>0 and pos>=3)
  results.append({"industry":name,"industry_etf":etf,"pairs":len(list(itertools.combinations(stocks,2))),"trades":len(rows),"mean_net_pair_bps":net,"positive_net_folds":pos,"gate_pass":passed,"folds":fr})
 fam=sum(r['gate_pass'] for r in results); pooled_net=float(np.mean([r['net_pair_bps'] for r in pooled]))
 out={"schema":"research.stock_pair_spread_reversion.v1","experiment_id":"CC-RF-STOCK-PAIR-SPREAD-REVERSION-001","generated_at":datetime.now(timezone.utc).isoformat(),"source":"Nasdaq raw daily close","panels":results,"pooled":{"trades":len(pooled),"mean_net_pair_bps":pooled_net},"decision":{"passing_industries":fam,"required":3,"pooled_net_positive":pooled_net>0,"discovery_gate_pass":bool(fam>=3 and pooled_net>0),"promotion_blocked_by_current_panel_survivorship":True},"source_fingerprints":fingerprints,"contract":{"spread":"log_price_difference","causal_normalization_lookback":LOOK,"entry_abs_z":ZENTRY,"delay":DELAY,"hold":HOLD,"leg_one_way_cost_bps":LEG_COST_BPS,"pair_round_trip_cost_bps":ROUND_TRIP_PAIR_COST_BPS,"dollar_neutral_half_notional_per_leg":True,"folds":FOLDS,"purge":PURGE},"boundaries":{"allocation_authority":False,"runtime_mutation":False,"live_trading_change":False}}
 OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n"); print(json.dumps(out,indent=2,sort_keys=True))
if __name__=='__main__':main()

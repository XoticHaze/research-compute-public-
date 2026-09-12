from __future__ import annotations

import hashlib, json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import numpy as np
import pandas as pd

SECTORS=("XLB","XLE","XLF","XLI","XLK","XLP","XLU","XLV","XLY")
SPY="SPY"; START="1999-01-01"; LOOK=252; SKIP=21; HOLD=21; TOP=3; COST_BPS=20.0; MIN_TRAIN=1008; FOLDS=6; PURGE=295
OUT=Path("results/sector_etf_momentum_rotation_r1.json")

def _d(x):
 for f in ("%m/%d/%Y","%Y-%m-%d","%b %d, %Y"):
  try:return datetime.strptime(str(x).strip(),f).date()
  except ValueError:pass
 raise ValueError(x)
def _p(x):return float(str(x or '').strip().replace('$','').replace(',',''))
def load(s):
 q=urlencode({"assetclass":"etf","fromdate":START,"todate":(date.today()+timedelta(days=2)).isoformat(),"limit":10000})
 u=f"https://api.nasdaq.com/api/quote/{s}/historical?{q}"
 r=Request(u,headers={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/147 Safari/537.36","Accept":"application/json, text/plain, */*","Referer":f"https://www.nasdaq.com/market-activity/etf/{s.lower()}/historical","Origin":"https://www.nasdaq.com"})
 with urlopen(r,timeout=45) as z:p=json.loads(z.read().decode())
 rows=(((p.get('data') or {}).get('tradesTable') or {}).get('rows') or [])
 v=sorted({_d(x['date']):_p(x['close']) for x in rows}.items())
 if len(v)<3000:raise RuntimeError(f"{s}: rows={len(v)}")
 return pd.Series([x[1] for x in v],index=pd.DatetimeIndex(pd.to_datetime([x[0] for x in v],utc=True)),name=s,dtype=float)
def folds(n):
 e=np.linspace(MIN_TRAIN,n-(HOLD+1),FOLDS+1,dtype=int);return [(int(e[i]),int(e[i+1])) for i in range(FOLDS)]
def cagr(rs):
 if not rs:return None
 wealth=float(np.prod([1+r for r in rs]));years=len(rs)*HOLD/252.0
 return (wealth**(1/years)-1)*100 if wealth>0 and years>0 else None
def main():
 raw={s:load(s) for s in (*SECTORS,SPY)};common=raw[SPY].index
 for s in SECTORS:common=common.intersection(raw[s].index)
 common=common.sort_values();px=pd.DataFrame({s:raw[s].reindex(common) for s in (*SECTORS,SPY)},index=common)
 if len(common)<3000 or px.isna().any().any():raise RuntimeError(f"common={len(common)} missing={int(px.isna().sum().sum())}")
 fp=hashlib.sha256("\n".join(f"{d.date()}|"+"|".join(f"{px.at[d,s]:.8f}" for s in (*SECTORS,SPY)) for d in common).encode()).hexdigest()
 fs=folds(len(common));rows=[]
 for fi,(a,b) in enumerate(fs,1):
  if fi<2:continue
  i=a
  while i<b-(HOLD+1):
   sig_i=i-1
   if sig_i-LOOK<0:i+=HOLD;continue
   scores={s:float(px[s].iloc[sig_i-SKIP]/px[s].iloc[sig_i-LOOK]-1) for s in SECTORS}
   chosen=sorted(scores,key=scores.get,reverse=True)[:TOP];ex=i;out=i+HOLD
   strat=float(np.mean([px[s].iloc[out]/px[s].iloc[ex]-1 for s in chosen]))-COST_BPS/10000.0
   ew=float(np.mean([px[s].iloc[out]/px[s].iloc[ex]-1 for s in SECTORS]))
   spy=float(px[SPY].iloc[out]/px[SPY].iloc[ex]-1)
   rows.append({"fold":fi,"entry":str(common[ex].date()),"chosen":chosen,"net_return":strat,"ew_return":ew,"spy_return":spy,"ew_excess":strat-ew,"spy_excess":strat-spy});i+=HOLD
 if not rows:raise RuntimeError("no periods")
 fr=[]
 for fi in range(2,7):
  rr=[r for r in rows if r['fold']==fi]
  fr.append({"fold":fi,"periods":len(rr),"strategy_cagr_pct":cagr([r['net_return'] for r in rr]),"ew_cagr_pct":cagr([r['ew_return'] for r in rr]),"spy_cagr_pct":cagr([r['spy_return'] for r in rr]),"mean_ew_excess_bps":float(np.mean([r['ew_excess'] for r in rr])*10000) if rr else None,"mean_spy_excess_bps":float(np.mean([r['spy_excess'] for r in rr])*10000) if rr else None})
 pos_ew=sum((r['mean_ew_excess_bps'] if r['mean_ew_excess_bps'] is not None else -1e99)>0 for r in fr);pos_spy=sum((r['mean_spy_excess_bps'] if r['mean_spy_excess_bps'] is not None else -1e99)>0 for r in fr)
 sc=cagr([r['net_return'] for r in rows]);ec=cagr([r['ew_return'] for r in rows]);pc=cagr([r['spy_return'] for r in rows]);ex_ew=sc-ec;ex_spy=sc-pc
 out={"schema":"research.sector_etf_momentum_rotation.v1","experiment_id":"CC-RF-SECTOR-MOMENTUM-ROTATION-001","generated_at":datetime.now(timezone.utc).isoformat(),"source":"Nasdaq raw daily ETF close","common_start":str(common[0].date()),"common_end":str(common[-1].date()),"periods":len(rows),"strategy_after_cost_cagr_pct":sc,"equal_weight_sector_cagr_pct":ec,"spy_cagr_pct":pc,"excess_vs_equal_weight_cagr_pp":ex_ew,"excess_vs_spy_cagr_pp":ex_spy,"positive_excess_folds_vs_equal_weight":pos_ew,"positive_excess_folds_vs_spy":pos_spy,"folds":fr,"decision":{"gate_pass":bool(ex_ew>1.0 and ex_spy>0 and pos_ew>=4 and pos_spy>=3),"required_excess_vs_equal_weight_cagr_pp":1.0,"required_positive_ew_folds":4,"required_positive_spy_folds":3},"contract":{"universe":SECTORS,"lookback_sessions":LOOK,"skip_recent_sessions":SKIP,"top_n":TOP,"rebalance_hold_sessions":HOLD,"round_trip_cost_bps":COST_BPS,"folds":FOLDS,"purge":PURGE},"source_fingerprint":fp,"boundaries":{"allocation_authority":False,"runtime_mutation":False,"live_trading_change":False}}
 OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n");print(json.dumps(out,indent=2,sort_keys=True))
if __name__=='__main__':main()

from __future__ import annotations
import hashlib,json
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
import numpy as np,pandas as pd
STOCKS=("ACGL","WRB","CINF","HIG","L","GL","RNR","AIZ");IND="KIE";BROAD="SPY";START="2014-01-01";EST=126;HOLD=21;DELAY=1;COST=50.;FOLDS=6;MIN_TRAIN=756
OUT=Path("results/insurance_low_residual_vol_disjoint_r1.json")
def _d(x):
 for f in ("%m/%d/%Y","%Y-%m-%d","%b %d, %Y"):
  try:return datetime.strptime(str(x).strip(),f).date()
  except ValueError:pass
 raise ValueError(x)
def _p(x):return float(str(x or '').strip().replace('$','').replace(',',''))
def load(s,etf=False):
 q=urlencode({"assetclass":"etf" if etf else "stocks","fromdate":START,"todate":(date.today()+timedelta(days=2)).isoformat(),"limit":5000});u=f"https://api.nasdaq.com/api/quote/{s}/historical?{q}";r=Request(u,headers={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/147 Safari/537.36","Accept":"application/json, text/plain, */*","Referer":f"https://www.nasdaq.com/market-activity/{'etf' if etf else 'stocks'}/{s.lower()}/historical","Origin":"https://www.nasdaq.com"})
 with urlopen(r,timeout=45) as z:p=json.loads(z.read().decode())
 rows=(((p.get('data') or {}).get('tradesTable') or {}).get('rows') or []);v=sorted({_d(x['date']):_p(x['close']) for x in rows}.items())
 if len(v)<1500:raise RuntimeError(f"{s}: rows={len(v)}")
 return pd.Series([x[1] for x in v],index=pd.DatetimeIndex(pd.to_datetime([x[0] for x in v],utc=True)),name=s,dtype=float)
def folds(n):
 e=np.linspace(MIN_TRAIN,n-(HOLD+DELAY+1),FOLDS+1,dtype=int);return [(int(e[i]),int(e[i+1])) for i in range(FOLDS)]
def main():
 raw={s:load(s,False) for s in STOCKS};raw[IND]=load(IND,True);raw[BROAD]=load(BROAD,True);common=raw[IND].index.intersection(raw[BROAD].index)
 for s in STOCKS:common=common.intersection(raw[s].index)
 common=common.sort_values();px=pd.DataFrame({s:raw[s].reindex(common) for s in (*STOCKS,IND,BROAD)},index=common);ret=px.pct_change();rows=[]
 for fi,(a,b) in enumerate(folds(len(common)),1):
  if fi<2:continue
  safe=b-(DELAY+HOLD);i=a
  while i<safe:
   x=ret[IND].iloc[i-EST:i].to_numpy()
   if len(x)<EST or not np.isfinite(x).all() or np.var(x)<=1e-12:i+=HOLD;continue
   xv=float(np.var(x));scores={}
   for s in STOCKS:
    y=ret[s].iloc[i-EST:i].to_numpy()
    if not np.isfinite(y).all():continue
    beta=float(np.cov(y,x,ddof=0)[0,1]/xv);scores[s]=float(np.std(y-beta*x,ddof=0))
   if len(scores)<len(STOCKS):i+=HOLD;continue
   k=max(1,int(np.ceil(len(scores)*.25)));chosen=sorted(scores,key=scores.get)[:k];ex=i+DELAY;out=ex+HOLD;sr=float(np.mean([px[s].iloc[out]/px[s].iloc[ex]-1 for s in chosen]));ir=float(px[IND].iloc[out]/px[IND].iloc[ex]-1);br=float(px[BROAD].iloc[out]/px[BROAD].iloc[ex]-1)
   rows.append({"fold":fi,"chosen":chosen,"net_bps":sr*1e4-COST,"industry_excess_bps":(sr-ir)*1e4,"spy_excess_bps":(sr-br)*1e4});i+=HOLD
 fr=[]
 for fi in range(2,7):
  rr=[r for r in rows if r['fold']==fi];fr.append({"fold":fi,"periods":len(rr),"industry_excess_mean_bps":float(np.mean([r['industry_excess_bps'] for r in rr])),"spy_excess_mean_bps":float(np.mean([r['spy_excess_bps'] for r in rr]))})
 net=float(np.mean([r['net_bps'] for r in rows]));iex=float(np.mean([r['industry_excess_bps'] for r in rows]));sex=float(np.mean([r['spy_excess_bps'] for r in rows]));pi=sum(r['industry_excess_mean_bps']>0 for r in fr);ps=sum(r['spy_excess_mean_bps']>0 for r in fr);fp=hashlib.sha256("\n".join(f"{d.date()}|"+"|".join(f"{px.at[d,s]:.8f}" for s in (*STOCKS,IND,BROAD)) for d in common).encode()).hexdigest()
 out={"schema":"research.insurance_low_residual_vol_disjoint.v1","experiment_id":"CC-RF-INSURANCE-LOW-RESIDUAL-VOL-DISJOINT-001","generated_at":datetime.now(timezone.utc).isoformat(),"source":"Nasdaq raw daily close","disjoint_from_discovery_panel":True,"stocks":STOCKS,"common_start":str(common[0].date()),"common_end":str(common[-1].date()),"periods":len(rows),"mean_net_50bps":net,"mean_kie_excess_bps":iex,"mean_spy_excess_bps":sex,"positive_kie_excess_folds":pi,"positive_spy_excess_folds":ps,"folds":fr,"decision":{"confirmation_pass":bool(net>0 and iex>0 and sex>=0 and pi>=3),"requires_positive_net":True,"requires_positive_kie_excess":True,"requires_nonnegative_spy_excess":True,"requires_kie_positive_folds":3},"contract":{"causal_beta_and_residual_vol_window":EST,"bottom_residual_vol_pct":.25,"delay":DELAY,"hold":HOLD,"round_trip_cost_bps":COST,"industry_control":IND,"broad_control":BROAD},"source_fingerprint":fp,"boundaries":{"allocation_authority":False,"runtime_mutation":False,"live_trading_change":False}}
 OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n");print(json.dumps(out,indent=2,sort_keys=True))
if __name__=='__main__':main()

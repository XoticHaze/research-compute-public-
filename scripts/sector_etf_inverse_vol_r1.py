from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
import numpy as np,pandas as pd
SECTORS=("XLB","XLE","XLF","XLI","XLK","XLP","XLU","XLV","XLY");SPY="SPY";VOL=63;HOLD=21;ONE_WAY_COST_BPS=10.0;MIN_TRAIN=1008;FOLDS=6
OUT=Path("results/sector_etf_inverse_vol_r1.json")
def load(s):
 u=f"https://query1.finance.yahoo.com/v8/finance/chart/{s}?period1=915148800&period2=1798761600&interval=1d&events=history&includeAdjustedClose=true";r=Request(u,headers={"User-Agent":"Mozilla/5.0"})
 with urlopen(r,timeout=45) as z:p=json.loads(z.read().decode())
 x=((p.get('chart') or {}).get('result') or [None])[0]
 if not x:raise RuntimeError(f"{s}: no result")
 ts=x.get('timestamp') or []; a=(((x.get('indicators') or {}).get('adjclose') or [{}])[0].get('adjclose') or []);v=[(t,q) for t,q in zip(ts,a) if q is not None and np.isfinite(float(q))]
 ser=pd.Series([float(q) for _,q in v],index=pd.DatetimeIndex(pd.to_datetime([t for t,_ in v],unit='s',utc=True)).normalize(),name=s).sort_index();ser=ser[~ser.index.duplicated(keep='last')]
 if len(ser)<3000:raise RuntimeError(f"{s}: rows={len(ser)}")
 return ser
def folds(n):
 e=np.linspace(MIN_TRAIN,n-(HOLD+1),FOLDS+1,dtype=int);return [(int(e[i]),int(e[i+1])) for i in range(FOLDS)]
def cagr(rs):
 w=float(np.prod([1+r for r in rs]));y=len(rs)*HOLD/252.;return (w**(1/y)-1)*100 if rs and w>0 else None
def maxdd(rs):
 w=np.cumprod(1+np.array(rs,float));pk=np.maximum.accumulate(w);return float(np.min(w/pk-1))*100 if len(w) else None
def main():
 raw={s:load(s) for s in (*SECTORS,SPY)};common=raw[SPY].index
 for s in SECTORS:common=common.intersection(raw[s].index)
 common=common.sort_values();px=pd.DataFrame({s:raw[s].reindex(common) for s in (*SECTORS,SPY)},index=common);ret=px.pct_change();rows=[];prev=np.repeat(1/len(SECTORS),len(SECTORS));fs=folds(len(common))
 for fi,(a,b) in enumerate(fs,1):
  if fi<2:continue
  i=a
  while i<b-(HOLD+1):
   hist=ret[list(SECTORS)].iloc[i-VOL:i]
   if len(hist)<VOL or hist.isna().any().any():i+=HOLD;continue
   vol=hist.std(ddof=0).to_numpy();inv=1/vol;w=inv/inv.sum();turn=.5*float(np.abs(w-prev).sum());out=i+HOLD
   sr=np.array([px[s].iloc[out]/px[s].iloc[i]-1 for s in SECTORS]);strat=float(w@sr)-turn*ONE_WAY_COST_BPS/10000.;ew=float(sr.mean());spy=float(px[SPY].iloc[out]/px[SPY].iloc[i]-1)
   rows.append({"fold":fi,"return":strat,"ew":ew,"spy":spy,"turnover":turn,"ew_excess":strat-ew,"spy_excess":strat-spy});prev=w;i+=HOLD
 fr=[]
 for fi in range(2,7):
  rr=[r for r in rows if r['fold']==fi];fr.append({"fold":fi,"periods":len(rr),"mean_ew_excess_bps":float(np.mean([r['ew_excess'] for r in rr])*10000),"mean_spy_excess_bps":float(np.mean([r['spy_excess'] for r in rr])*10000)})
 s=cagr([r['return'] for r in rows]);e=cagr([r['ew'] for r in rows]);p=cagr([r['spy'] for r in rows]);pe=sum(r['mean_ew_excess_bps']>0 for r in fr);ps=sum(r['mean_spy_excess_bps']>0 for r in fr);mdd=maxdd([r['return'] for r in rows]);emdd=maxdd([r['ew'] for r in rows])
 fp=hashlib.sha256("\n".join(f"{d.date()}|"+"|".join(f"{px.at[d,x]:.8f}" for x in (*SECTORS,SPY)) for d in common).encode()).hexdigest()
 out={"schema":"research.sector_etf_inverse_vol.v1","experiment_id":"CC-RF-SECTOR-INVERSE-VOL-001","generated_at":datetime.now(timezone.utc).isoformat(),"source":"Yahoo adjusted daily close","common_start":str(common[0].date()),"common_end":str(common[-1].date()),"periods":len(rows),"strategy_after_cost_cagr_pct":s,"equal_weight_cagr_pct":e,"spy_cagr_pct":p,"excess_vs_equal_weight_cagr_pp":s-e,"excess_vs_spy_cagr_pp":s-p,"strategy_max_drawdown_pct":mdd,"equal_weight_max_drawdown_pct":emdd,"drawdown_improvement_pp":mdd-emdd,"mean_turnover":float(np.mean([r['turnover'] for r in rows])),"positive_ew_excess_folds":pe,"positive_spy_excess_folds":ps,"folds":fr,"decision":{"gate_pass":bool(s-e>0.5 and s-p>0 and pe>=3 and mdd>=emdd),"required_excess_vs_equal_weight_cagr_pp":0.5,"required_positive_ew_folds":3,"requires_nonnegative_excess_vs_spy":true,"requires_no_worse_drawdown_than_equal_weight":true},"contract":{"trailing_vol_sessions":VOL,"rebalance_hold_sessions":HOLD,"inverse_vol_no_cap":true,"one_way_turnover_cost_bps":ONE_WAY_COST_BPS,"folds":FOLDS},"source_fingerprint":fp,"boundaries":{"allocation_authority":false,"runtime_mutation":false,"live_trading_change":false}}
 OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n");print(json.dumps(out,indent=2,sort_keys=True))
if __name__=='__main__':main()

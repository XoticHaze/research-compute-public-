from __future__ import annotations
import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
SYMS=("SPY","QQQ","TLT","GLD","DBC"); COSTS=(25,50,100); WINDOWS={"full":None,"2015_forward":"2015-01-01","2020_forward":"2020-01-01"}
def cagr(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')
def met(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); v=float(r.std(ddof=1)*math.sqrt(12)); dd=float((e/e.cummax()-1).min()); a=float(r.mean()*12); return {"cagr":cagr(r),"vol":v,"sharpe_rf0":a/v if v else None,"max_drawdown":dd,"calmar":cagr(r)/abs(dd) if dd<0 else None}
def main():
 raw=yf.download(list(SYMS),start="2006-01-01",auto_adjust=True,progress=False,threads=False); c=raw['Close'].dropna(how='any').astype(float); ret=c.pct_change(); rv=ret.rolling(63,min_periods=63).std(); last=pd.Timestamp(c.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cutoff=last.to_period('M').start_time-pd.Timedelta(days=1); m=c.resample('ME').last(); m=m[m.index<=cutoff]; vm=rv.resample('ME').last().reindex(m.index)
 rows=[]; prev=np.repeat(1/len(SYMS),len(SYMS))
 for i in range(len(m)-1):
  dt=m.index[i]; nxt=m.index[i+1]; vol=vm.loc[dt,list(SYMS)].to_numpy(float)
  if not np.isfinite(vol).all() or (vol<=0).any(): continue
  inv=1/vol; w=inv/inv.sum(); r=(m.loc[nxt,list(SYMS)]/m.loc[dt,list(SYMS)]-1).to_numpy(float); turn=.5*float(abs(w-prev).sum()); rows.append({"date":nxt,"gross":float(w@r),"turnover":turn,"matched":float(np.mean(r)),"spy":float(r[0]),"qqq":float(r[1]),"max_weight":float(w.max())}); prev=w
 f=pd.DataFrame(rows).set_index('date'); out={"schema":"research.p85_inverse_vol_r1","parent":"P85","hypothesis":"A fixed monthly inverse-63-day-volatility allocation across a diversified liquid ETF universe creates durable after-cost excess and risk efficiency versus static equal weight.","contract":{"universe":list(SYMS),"signal":"inverse trailing 63-trading-day realized volatility","allocation":"fully invested normalized inverse volatility","rebalance":"monthly","costs_bps":list(COSTS),"matched_control":"same-universe static equal weight","opportunity_controls":["SPY","QQQ"],"windows":WINDOWS,"folds":5,"no_parameter_search":True},"source":{"provider":"Yahoo Finance via yfinance; research-only","last_complete_month_end":str(cutoff.date()),"panel_sha256":hashlib.sha256(c.reset_index().to_csv(index=False).encode()).hexdigest()},"tests":{}}
 for name,start in WINDOWS.items():
  q=f if start is None else f.loc[start:]; z={"months":len(q),"start":str(q.index.min().date()),"end":str(q.index.max().date()),"mean_max_weight":float(q.max_weight.mean()),"controls":{"matched":met(q.matched),"spy":met(q.spy),"qqq":met(q.qqq)},"costs":{}}; ids=np.array_split(np.arange(len(q)),5)
  for bp in COSTS:
   net=q.gross-q.turnover*bp/10000; mm=met(net); folds=[]
   for j,x in enumerate(ids,1):
    a=q.iloc[x]; n=a.gross-a.turnover*bp/10000; folds.append({"fold":j,"excess_cagr":cagr(n)-cagr(a.matched)})
   z['costs'][str(bp)]={"candidate":mm,"excess_cagr_vs_matched":mm['cagr']-z['controls']['matched']['cagr'],"excess_cagr_vs_spy":mm['cagr']-z['controls']['spy']['cagr'],"excess_cagr_vs_qqq":mm['cagr']-z['controls']['qqq']['cagr'],"sharpe_delta_vs_matched":mm['sharpe_rf0']-z['controls']['matched']['sharpe_rf0'],"max_drawdown_delta_vs_matched":mm['max_drawdown']-z['controls']['matched']['max_drawdown'],"positive_matched_folds":sum(x['excess_cagr']>0 for x in folds),"folds":folds}
  out['tests'][name]=z
 p=out['tests']['2020_forward']['costs']['50']; out['decision']='P85_INVERSE_VOL_SUPPORTED' if p['excess_cagr_vs_matched']>0 and p['positive_matched_folds']>=3 and p['sharpe_delta_vs_matched']>0 else 'P85_INVERSE_VOL_NOT_SUPPORTED'; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p85_inverse_vol_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True,allow_nan=False))
if __name__=='__main__': main()

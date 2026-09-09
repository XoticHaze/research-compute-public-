from __future__ import annotations
import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
SYMS=("XLB","XLE","XLF","XLI","XLK","XLP","XLU","XLV","XLY"); COSTS=(25,50,100); WINDOWS={"full":None,"2015_forward":"2015-01-01","2020_forward":"2020-01-01"}
def cagr(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')
def met(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); v=float(r.std(ddof=1)*math.sqrt(12)); dd=float((e/e.cummax()-1).min()); a=float(r.mean()*12); return {"cagr":cagr(r),"vol":v,"sharpe_rf0":a/v if v else None,"max_drawdown":dd}
def main():
 raw=yf.download(list(SYMS)+["SPY"],start="1999-01-01",auto_adjust=True,progress=False,threads=False); c=raw['Close'].dropna(how='any').astype(float); last=pd.Timestamp(c.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cutoff=last.to_period('M').start_time-pd.Timedelta(days=1); m=c.resample('ME').last(); m=m[m.index<=cutoff]
 rows=[]; prev=np.zeros(len(SYMS))
 for i in range(1,len(m)-1):
  dt=m.index[i]; nxt=m.index[i+1]; past=(m.loc[dt,list(SYMS)]/m.iloc[i-1][list(SYMS)]-1).sort_values(); chosen=set(past.index[:3]); w=np.array([1/3 if s in chosen else 0 for s in SYMS]); r=(m.loc[nxt,list(SYMS)]/m.loc[dt,list(SYMS)]-1).to_numpy(float); turn=.5*float(abs(w-prev).sum()); rows.append({"date":nxt,"gross":float(w@r),"turnover":turn,"matched":float(np.mean(r)),"spy":float(m.loc[nxt,'SPY']/m.loc[dt,'SPY']-1)}); prev=w
 f=pd.DataFrame(rows).set_index('date'); out={"schema":"research.p84_sector_reversal_r1","parent":"P84","hypothesis":"Monthly selection of the three worst-performing sector ETFs from the prior month captures a cross-sectional reversal premium after realistic costs.","contract":{"universe":list(SYMS),"signal":"bottom 3 prior-month total returns","rebalance":"monthly","costs_bps":list(COSTS),"matched_control":"same-universe static equal weight","opportunity_control":"SPY","windows":WINDOWS,"folds":5,"no_parameter_search":True},"source":{"provider":"Yahoo Finance via yfinance; research-only","last_complete_month_end":str(cutoff.date()),"panel_sha256":hashlib.sha256(c.reset_index().to_csv(index=False).encode()).hexdigest()},"tests":{}}
 for name,start in WINDOWS.items():
  q=f if start is None else f.loc[start:]; z={"months":len(q),"start":str(q.index.min().date()),"end":str(q.index.max().date()),"controls":{"matched":met(q.matched),"spy":met(q.spy)},"costs":{}}
  ids=np.array_split(np.arange(len(q)),5)
  for bp in COSTS:
   net=q.gross-q.turnover*bp/10000; mm=met(net); folds=[]
   for j,x in enumerate(ids,1):
    a=q.iloc[x]; n=a.gross-a.turnover*bp/10000; folds.append({"fold":j,"excess_cagr":cagr(n)-cagr(a.matched)})
   z['costs'][str(bp)]={"candidate":mm,"excess_cagr_vs_matched":mm['cagr']-z['controls']['matched']['cagr'],"excess_cagr_vs_spy":mm['cagr']-z['controls']['spy']['cagr'],"sharpe_delta_vs_matched":mm['sharpe_rf0']-z['controls']['matched']['sharpe_rf0'],"max_drawdown_delta_vs_matched":mm['max_drawdown']-z['controls']['matched']['max_drawdown'],"positive_matched_folds":sum(x['excess_cagr']>0 for x in folds),"folds":folds}
  out['tests'][name]=z
 p=out['tests']['2020_forward']['costs']['50']; out['decision']='P84_SECTOR_REVERSAL_SUPPORTED' if p['excess_cagr_vs_matched']>0 and p['positive_matched_folds']>=3 and p['sharpe_delta_vs_matched']>0 else 'P84_SECTOR_REVERSAL_NOT_SUPPORTED'; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p84_sector_reversal_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True,allow_nan=False))
if __name__=='__main__': main()

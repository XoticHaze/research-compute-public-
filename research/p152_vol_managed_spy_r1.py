from __future__ import annotations
import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
COSTS=(25,50,100)
WINDOWS={'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}
TARGET_VOL=0.10

def cagr(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')
def stats(r):
 r=pd.Series(r,dtype=float).dropna(); eq=(1+r).cumprod(); vol=float(r.std(ddof=1)*math.sqrt(12)); return {'cagr':cagr(r),'sharpe_rf0':float(r.mean()*12/vol) if vol else None,'maxdd':float((eq/eq.cummax()-1).min())}
def evaluate(q,cost_bps):
 z=q.copy(); z['net']=z.gross-z.turnover*cost_bps/10000; mx=float(z.exposure.mean()); z['matched']=mx*z.spy
 out={k:stats(z[k]) for k in ('net','matched','spy')}; out.update({'excess_matched':out['net']['cagr']-out['matched']['cagr'],'excess_spy':out['net']['cagr']-out['spy']['cagr'],'months':len(z),'mean_exposure':mx,'mean_turnover':float(z.turnover.mean())})
 folds=[]
 for j,idx in enumerate(np.array_split(np.arange(len(z)),5),1):
  a=z.iloc[idx]; e=float(a.exposure.mean()); m=e*a.spy; folds.append({'fold':j,'matched_excess':cagr(a.net)-cagr(m),'spy_excess':cagr(a.net)-cagr(a.spy)})
 out['positive_matched_folds']=sum(x['matched_excess']>0 for x in folds); out['positive_spy_folds']=sum(x['spy_excess']>0 for x in folds); out['folds']=folds; return out

def main():
 px=yf.download('SPY',start='2000-01-01',auto_adjust=True,progress=False,threads=False)['Close']
 if isinstance(px,pd.DataFrame): px=px.iloc[:,0]
 px=px.dropna().astype(float); last=pd.Timestamp(px.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cut=last.to_period('M').start_time-pd.Timedelta(days=1); px=px.loc[px.index<=cut]
 dr=px.pct_change(fill_method=None); rv=dr.rolling(63).std(ddof=1)*math.sqrt(252); m=px.resample('ME').last(); mr=m.pct_change(fill_method=None)
 rows=[]; prev=0.0
 for i,dt in enumerate(m.index[:-1]):
  daily=px.index[px.index<=dt]
  if len(daily)<63: continue
  sig=float(rv.loc[daily[-1]])
  if not np.isfinite(sig) or sig<=0: continue
  exposure=min(1.0,TARGET_VOL/sig); nxt=m.index[i+1]; r=float(mr.loc[nxt]); turnover=abs(exposure-prev)
  rows.append({'return_month':nxt,'exposure':exposure,'gross':exposure*r,'turnover':turnover,'spy':r,'signal_realized_vol':sig}); prev=exposure
 q=pd.DataFrame(rows).set_index('return_month'); tests={w:{str(c):evaluate(q.loc[pd.Timestamp(s):],c) for c in COSTS} for w,s in WINDOWS.items()}; a=tests['2015']['50']; b=tests['2020']['50']
 decision='P152_VOL_MANAGED_SPY_SUPPORTED_FOR_INDEPENDENT_VALIDATION' if a['excess_matched']>0 and a['positive_matched_folds']>=3 and b['excess_matched']>0 and b['positive_matched_folds']>=3 else 'P152_VOL_MANAGED_SPY_NOT_SUPPORTED'
 out={'schema':'research.p152_vol_managed_spy_r1','parent':'P152','hypothesis':'A fixed 10% target-vol, no-leverage SPY rule using trailing 63-session realized volatility improves after-cost return versus static SPY at the same average capital usage and improves drawdown efficiency.','contract':{'signal':'trailing 63-session SPY realized volatility observed at completed month end','exposure':'min(1, 10%/realized_vol)','rebalance':'monthly; residual cash','cost_bps':list(COSTS),'matched_control':'static SPY at evaluated mean exposure','opportunity_control':'full SPY','windows':list(WINDOWS),'folds':5,'no_target_lookback_cap_cost_or_window_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cut.date()),'panel_sha256':hashlib.sha256(px.reset_index().to_csv(index=False).encode()).hexdigest()},'tests':tests,'decision':decision}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p152_vol_managed_spy_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()

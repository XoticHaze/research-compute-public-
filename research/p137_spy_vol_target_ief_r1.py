from __future__ import annotations
import json,math,hashlib
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
TARGET=.10; COSTS=(25,50,100)
def cagr(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1)
def metrics(r):
 r=pd.Series(r,dtype=float).dropna(); eq=(1+r).cumprod(); vol=float(r.std(ddof=0)*math.sqrt(12)); cg=cagr(r); mdd=float((eq/eq.cummax()-1).min()); return {'cagr':cg,'vol':vol,'sharpe_rf0':float(r.mean()*12/vol) if vol else None,'maxdd':mdd,'calmar':float(cg/abs(mdd)) if mdd<0 else None}
def main():
 d=yf.download(['SPY','IEF'],start='2003-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna().astype(float); last=pd.Timestamp(d.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cut=last.to_period('M').start_time-pd.Timedelta(days=1); d=d.loc[d.index<=cut]; m=d.resample('ME').last(); ret=m.pct_change(fill_method=None); rv=(d.SPY.pct_change(fill_method=None).rolling(63,min_periods=50).std(ddof=0)*math.sqrt(252)).resample('ME').last(); rows=[]; prev=.0
 for i,dt in enumerate(m.index[:-1]):
  if pd.isna(rv.loc[dt]) or rv.loc[dt]<=0: continue
  nxt=m.index[i+1]; rr=ret.loc[nxt]
  if rr.isna().any(): continue
  w=min(1.0,TARGET/float(rv.loc[dt])); gross=w*float(rr.SPY)+(1-w)*float(rr.IEF); turn=abs(w-prev); rows.append({'date':nxt,'spy_weight':w,'gross':gross,'turnover':turn,'matched':.6*float(rr.SPY)+.4*float(rr.IEF),'spy':float(rr.SPY)}); prev=w
 q=pd.DataFrame(rows).set_index('date'); tests={}
 for w,s in {'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}.items():
  z=q.loc[pd.Timestamp(s):]; tests[w]={}
  for c in COSTS:
   net=z.gross-z.turnover*c/10000; cm,mm,sm=metrics(net),metrics(z.matched),metrics(z.spy); tests[w][str(c)]={'candidate':cm,'matched_60_40':mm,'spy':sm,'excess_matched':cm['cagr']-mm['cagr'],'excess_spy':cm['cagr']-sm['cagr'],'annualized_turnover':float(z.turnover.mean()*12),'mean_spy_weight':float(z.spy_weight.mean())}
 a=tests['2015']['50']; decision='P137_VOL_TARGET_SUPPORTED_FOR_INDEPENDENT_VALIDATION' if a['candidate']['sharpe_rf0']>a['matched_60_40']['sharpe_rf0'] and a['candidate']['maxdd']>a['matched_60_40']['maxdd'] and a['excess_matched']>0 else 'P137_VOL_TARGET_NOT_SUPPORTED'
 out={'schema':'research.p137_spy_vol_target_ief_r1','parent':'P137','hypothesis':'A fixed ex-ante 10% annualized SPY volatility target, measured from prior 63 trading days and parking residual weight in IEF, creates superior after-cost risk-adjusted fund utility versus static 60/40 SPY/IEF.','contract':{'target_vol':TARGET,'realized_vol_window_days':63,'max_spy_weight':1.0,'residual_asset':'IEF','rebalance':'monthly using prior completed month-end volatility','cost_bps_per_weight_turnover':list(COSTS),'matched_control':'static 60/40 SPY/IEF','opportunity_control':'SPY','windows':['2010','2015','2020'],'no_target_window_weight_or_cost_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cut.date()),'panel_sha256':hashlib.sha256(d.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()},'tests':tests,'decision':decision}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p137_spy_vol_target_ief_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()

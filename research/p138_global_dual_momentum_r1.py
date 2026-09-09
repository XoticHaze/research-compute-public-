from __future__ import annotations
import json,hashlib,math
from pathlib import Path
import pandas as pd,numpy as np,yfinance as yf
EQ=('SPY','VEA','VWO'); SAFE='IEF'; COSTS=(25,50,100)
def cagr(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1)
def metrics(r):
 r=pd.Series(r,dtype=float).dropna(); eq=(1+r).cumprod(); vol=float(r.std(ddof=0)*math.sqrt(12)); cg=cagr(r); mdd=float((eq/eq.cummax()-1).min()); return {'cagr':cg,'vol':vol,'sharpe_rf0':float(r.mean()*12/vol) if vol else None,'maxdd':mdd,'calmar':float(cg/abs(mdd)) if mdd<0 else None}
def main():
 syms=list(EQ)+[SAFE]; d=yf.download(syms,start='2006-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna().astype(float); last=pd.Timestamp(d.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cut=last.to_period('M').start_time-pd.Timedelta(days=1); d=d.loc[d.index<=cut]; m=d.resample('ME').last(); mom=m.pct_change(12); ret=m.pct_change(fill_method=None); rows=[]; prev=None
 for i,dt in enumerate(m.index[:-1]):
  if mom.loc[dt].isna().any(): continue
  winner=max(EQ,key=lambda s:(float(mom.loc[dt,s]),s)); asset=winner if float(mom.loc[dt,winner])>float(mom.loc[dt,SAFE]) else SAFE; nxt=m.index[i+1]; rr=ret.loc[nxt]
  if rr.isna().any(): continue
  turn=1.0 if prev is None or asset!=prev else 0.0; rows.append({'date':nxt,'asset':asset,'gross':float(rr[asset]),'turnover':turn,'matched':.6*float(rr.SPY)+.4*float(rr.IEF),'spy':float(rr.SPY)}); prev=asset
 q=pd.DataFrame(rows).set_index('date'); tests={}
 for w,s in {'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}.items():
  z=q.loc[pd.Timestamp(s):]; tests[w]={}
  for c in COSTS:
   net=z.gross-z.turnover*c/10000; cm,mm,sm=metrics(net),metrics(z.matched),metrics(z.spy); tests[w][str(c)]={'candidate':cm,'matched_60_40':mm,'spy':sm,'excess_matched':cm['cagr']-mm['cagr'],'excess_spy':cm['cagr']-sm['cagr'],'annualized_state_changes':float(z.turnover.mean()*12)}
 a=tests['2015']['50']; decision='P138_GLOBAL_DUAL_MOMENTUM_SUPPORTED_FOR_INDEPENDENT_VALIDATION' if a['excess_matched']>0 and a['candidate']['sharpe_rf0']>a['matched_60_40']['sharpe_rf0'] and a['candidate']['maxdd']>a['matched_60_40']['maxdd'] else 'P138_GLOBAL_DUAL_MOMENTUM_NOT_SUPPORTED'
 out={'schema':'research.p138_global_dual_momentum_r1','parent':'P138','hypothesis':'Prior completed-month 12-month relative momentum among SPY/VEA/VWO, conditioned on beating IEF absolute momentum, creates durable after-cost fund utility.','contract':{'equity_candidates':list(EQ),'defensive_asset':SAFE,'lookback_months':12,'rule':'highest equity 12m return if above IEF 12m return, else IEF','rebalance':'monthly','cost_bps_per_state_change':list(COSTS),'matched_control':'static 60/40 SPY/IEF','opportunity_control':'SPY','windows':['2010','2015','2020'],'no_lookback_threshold_weight_or_cost_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cut.date()),'panel_sha256':hashlib.sha256(d.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()},'tests':tests,'decision':decision}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p138_global_dual_momentum_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()

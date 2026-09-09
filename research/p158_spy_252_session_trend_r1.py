from __future__ import annotations
import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
C=(25,50,100); W={'2005':'2005-01-01','2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}
def cg(r): r=pd.Series(r).dropna(); return float((1+r).prod()**(12/len(r))-1)
def st(r):
 r=pd.Series(r).dropna(); e=(1+r).cumprod(); v=float(r.std(ddof=1)*math.sqrt(12)); return {'cagr':cg(r),'sharpe_rf0':float(r.mean()*12/v) if v else None,'maxdd':float((e/e.cummax()-1).min())}
def ev(q,c):
 z=q.copy(); z['net']=z.gross-z.turnover*c/10000; ex=float(z.pos.mean()); z['matched']=ex*z.spy; o={k:st(z[k]) for k in ['net','matched','spy']}; o.update({'excess_matched':o['net']['cagr']-o['matched']['cagr'],'excess_spy':o['net']['cagr']-o['spy']['cagr'],'months':len(z),'mean_exposure':ex,'mean_turnover':float(z.turnover.mean())}); f=[]
 for j,ix in enumerate(np.array_split(np.arange(len(z)),5),1):
  a=z.iloc[ix]; e=float(a.pos.mean()); f.append({'fold':j,'matched_excess':cg(a.net)-cg(e*a.spy),'spy_excess':cg(a.net)-cg(a.spy)})
 o['positive_matched_folds']=sum(x['matched_excess']>0 for x in f); o['positive_spy_folds']=sum(x['spy_excess']>0 for x in f); o['folds']=f; return o
def main():
 px=yf.download('SPY',start='1995-01-01',auto_adjust=True,progress=False,threads=False)['Close']; px=px.iloc[:,0] if isinstance(px,pd.DataFrame) else px; px=px.dropna().astype(float); last=pd.Timestamp(px.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cut=last.to_period('M').start_time-pd.Timedelta(days=1); px=px.loc[px.index<=cut]; sma=px.rolling(252).mean(); m=px.resample('ME').last(); mr=m.pct_change(fill_method=None); rows=[]; prev=0.
 for i,dt in enumerate(m.index[:-1]):
  ix=px.index[px.index<=dt]
  if len(ix)<252: continue
  d=ix[-1]; pos=float(px.loc[d]>sma.loc[d]); nxt=m.index[i+1]; rr=float(mr.loc[nxt]); rows.append({'return_month':nxt,'gross':pos*rr,'turnover':abs(pos-prev),'pos':pos,'spy':rr}); prev=pos
 q=pd.DataFrame(rows).set_index('return_month'); tests={k:{str(c):ev(q.loc[pd.Timestamp(s):],c) for c in C} for k,s in W.items()}; a=tests['2015']['50']; b=tests['2020']['50']; d='P158_SPY252_TREND_SUPPORTED_FOR_INDEPENDENT_VALIDATION' if a['excess_matched']>0 and a['positive_matched_folds']>=3 and b['excess_matched']>0 and b['positive_matched_folds']>=3 else 'P158_SPY252_TREND_NOT_SUPPORTED'; out={'schema':'research.p158_spy_252_session_trend_r1','parent':'P158','hypothesis':'The predeclared 252-session price-above-SMA trend mechanism, evaluated on SPY as an external liquid equity representation while canonical MES/ES history is blocked, creates after-cost excess versus static SPY at identical average capital usage.','contract':{'asset':'SPY','signal':'completed-month close above trailing 252-session adjusted-close SMA','position':'SPY next month if signal true else cash','cost_bps':list(C),'matched_control':'static SPY at evaluated mean exposure','opportunity_control':'full SPY','windows':list(W),'folds':5,'no_lookback_threshold_cost_or_window_search':True,'scope':'representation-transfer discriminator only; not substitute for canonical MES/ES dated-contract confirmation'},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cut.date()),'panel_sha256':hashlib.sha256(px.reset_index().to_csv(index=False).encode()).hexdigest()},'tests':tests,'decision':d}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p158_spy_252_session_trend_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()

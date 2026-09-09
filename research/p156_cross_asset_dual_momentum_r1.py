from __future__ import annotations
import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
A=['SPY','IEF','GLD']; C=(25,50,100); W={'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}
def cg(r): r=pd.Series(r).dropna(); return float((1+r).prod()**(12/len(r))-1)
def st(r):
 r=pd.Series(r).dropna(); e=(1+r).cumprod(); v=float(r.std(ddof=1)*math.sqrt(12)); return {'cagr':cg(r),'sharpe_rf0':float(r.mean()*12/v) if v else None,'maxdd':float((e/e.cummax()-1).min())}
def ev(q,c):
 z=q.copy(); z['net']=z.gross-z.turnover*c/10000; mw={a:float(z['w_'+a].mean()) for a in A}; z['matched']=sum(mw[a]*z['r_'+a] for a in A); o={k:st(z[k]) for k in ['net','matched','spy']}; o.update({'excess_matched':o['net']['cagr']-o['matched']['cagr'],'excess_spy':o['net']['cagr']-o['spy']['cagr'],'months':len(z),'mean_turnover':float(z.turnover.mean()),'mean_weights':mw}); f=[]
 for j,ix in enumerate(np.array_split(np.arange(len(z)),5),1):
  x=z.iloc[ix]; fw={a:float(x['w_'+a].mean()) for a in A}; m=sum(fw[a]*x['r_'+a] for a in A); f.append({'fold':j,'matched_excess':cg(x.net)-cg(m),'spy_excess':cg(x.net)-cg(x.spy)})
 o['positive_matched_folds']=sum(x['matched_excess']>0 for x in f); o['positive_spy_folds']=sum(x['spy_excess']>0 for x in f); o['folds']=f; return o
def main():
 px=yf.download(A,start='2004-11-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna().astype(float); last=pd.Timestamp(px.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cut=last.to_period('M').start_time-pd.Timedelta(days=1); px=px.loc[px.index<=cut]; m=px.resample('ME').last(); r=m.pct_change(fill_method=None); mom=m/m.shift(12)-1; prev={a:0. for a in A}; pc=1.; rows=[]
 for i,dt in enumerate(m.index[:-1]):
  sig=mom.loc[dt,A]
  if sig.isna().any(): continue
  best=str(sig.idxmax()); invest=float(sig[best]>0); w={a:(invest if a==best else 0.) for a in A}; cash=1-invest; nxt=m.index[i+1]; rr=r.loc[nxt,A]; to=.5*(sum(abs(w[a]-prev[a]) for a in A)+abs(cash-pc)); row={'return_month':nxt,'gross':sum(w[a]*float(rr[a]) for a in A),'turnover':to,'spy':float(rr.SPY)}; row.update({'w_'+a:w[a] for a in A}); row.update({'r_'+a:float(rr[a]) for a in A}); rows.append(row); prev=w; pc=cash
 q=pd.DataFrame(rows).set_index('return_month'); tests={k:{str(c):ev(q.loc[pd.Timestamp(s):],c) for c in C} for k,s in W.items()}; a=tests['2015']['50']; b=tests['2020']['50']; d='P156_CROSS_ASSET_DUAL_MOMENTUM_SUPPORTED_FOR_INDEPENDENT_VALIDATION' if a['excess_matched']>0 and a['positive_matched_folds']>=3 and b['excess_matched']>0 and b['positive_matched_folds']>=3 else 'P156_CROSS_ASSET_DUAL_MOMENTUM_NOT_SUPPORTED'; out={'schema':'research.p156_cross_asset_dual_momentum_r1','parent':'P156','hypothesis':'Monthly absolute-and-relative 12-month momentum across SPY, IEF and GLD, holding the strongest positive asset or cash, creates after-cost excess versus a static portfolio with the same average asset weights and versus SPY.','contract':{'assets':A,'signal':'completed-month 12-month total return','selection':'highest positive momentum asset, else cash','cost_bps':list(C),'matched_control':'static SPY/IEF/GLD at evaluated mean dynamic weights with residual cash','opportunity_control':'SPY','windows':list(W),'folds':5,'no_asset_horizon_threshold_cost_or_window_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cut.date()),'panel_sha256':hashlib.sha256(px.reset_index().to_csv(index=False).encode()).hexdigest()},'tests':tests,'decision':d}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p156_cross_asset_dual_momentum_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()

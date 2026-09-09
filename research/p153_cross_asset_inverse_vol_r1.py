from __future__ import annotations
import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
ASSETS=['SPY','IEF','GLD']; COSTS=(25,50,100); WINDOWS={'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}
def cagr(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')
def stats(r):
 r=pd.Series(r,dtype=float).dropna(); eq=(1+r).cumprod(); vol=float(r.std(ddof=1)*math.sqrt(12)); return {'cagr':cagr(r),'sharpe_rf0':float(r.mean()*12/vol) if vol else None,'maxdd':float((eq/eq.cummax()-1).min())}
def evaluate(q,cost_bps):
 z=q.copy(); z['net']=z.gross-z.turnover*cost_bps/10000
 mw={a:float(z[f'w_{a}'].mean()) for a in ASSETS}; z['matched']=sum(mw[a]*z[f'r_{a}'] for a in ASSETS)
 out={k:stats(z[k]) for k in ('net','matched','spy')}; out.update({'excess_matched':out['net']['cagr']-out['matched']['cagr'],'excess_spy':out['net']['cagr']-out['spy']['cagr'],'months':len(z),'mean_turnover':float(z.turnover.mean()),'mean_weights':mw})
 folds=[]
 for j,idx in enumerate(np.array_split(np.arange(len(z)),5),1):
  a=z.iloc[idx]; fw={x:float(a[f'w_{x}'].mean()) for x in ASSETS}; m=sum(fw[x]*a[f'r_{x}'] for x in ASSETS)
  folds.append({'fold':j,'matched_excess':cagr(a.net)-cagr(m),'spy_excess':cagr(a.net)-cagr(a.spy)})
 out['positive_matched_folds']=sum(f['matched_excess']>0 for f in folds); out['positive_spy_folds']=sum(f['spy_excess']>0 for f in folds); out['folds']=folds; return out
def main():
 px=yf.download(ASSETS,start='2004-11-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna().astype(float); last=pd.Timestamp(px.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cut=last.to_period('M').start_time-pd.Timedelta(days=1); px=px.loc[px.index<=cut]
 dr=px.pct_change(fill_method=None); rv=dr.rolling(63).std(ddof=1)*math.sqrt(252); m=px.resample('ME').last(); mr=m.pct_change(fill_method=None); rows=[]; prev={a:0.0 for a in ASSETS}
 for i,dt in enumerate(m.index[:-1]):
  daily=px.index[px.index<=dt]
  if len(daily)<63: continue
  v=rv.loc[daily[-1],ASSETS]
  if v.isna().any() or (v<=0).any(): continue
  inv=1/v; w=(inv/inv.sum()).to_dict(); nxt=m.index[i+1]; rr=mr.loc[nxt,ASSETS]
  turnover=0.5*sum(abs(float(w[a])-prev[a]) for a in ASSETS); gross=sum(float(w[a])*float(rr[a]) for a in ASSETS)
  row={'return_month':nxt,'gross':gross,'turnover':turnover,'spy':float(rr['SPY'])}; row.update({f'w_{a}':float(w[a]) for a in ASSETS}); row.update({f'r_{a}':float(rr[a]) for a in ASSETS}); rows.append(row); prev={a:float(w[a]) for a in ASSETS}
 q=pd.DataFrame(rows).set_index('return_month'); tests={w:{str(c):evaluate(q.loc[pd.Timestamp(s):],c) for c in COSTS} for w,s in WINDOWS.items()}; a=tests['2015']['50']; b=tests['2020']['50']
 decision='P153_CROSS_ASSET_INVOL_SUPPORTED_FOR_INDEPENDENT_VALIDATION' if a['excess_matched']>0 and a['positive_matched_folds']>=3 and b['excess_matched']>0 and b['positive_matched_folds']>=3 and a['net']['sharpe_rf0']>a['matched']['sharpe_rf0'] else 'P153_CROSS_ASSET_INVOL_NOT_SUPPORTED'
 out={'schema':'research.p153_cross_asset_inverse_vol_r1','parent':'P153','hypothesis':'A fixed monthly inverse-vol allocation across SPY, IEF and GLD using trailing 63-session realized volatility creates after-cost excess and better risk efficiency versus a static portfolio with the same average asset weights, with SPY retained as opportunity-cost control.','contract':{'assets':ASSETS,'signal':'trailing 63-session realized volatility at completed month end','weights':'normalized inverse volatility, fully invested','rebalance':'monthly','cost_bps':list(COSTS),'matched_control':'static SPY/IEF/GLD portfolio at evaluated mean dynamic weights','opportunity_control':'SPY','windows':list(WINDOWS),'folds':5,'no_asset_lookback_weight_cap_cost_or_window_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cut.date()),'panel_sha256':hashlib.sha256(px.reset_index().to_csv(index=False).encode()).hexdigest()},'tests':tests,'decision':decision}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p153_cross_asset_inverse_vol_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()

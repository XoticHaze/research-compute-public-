from __future__ import annotations
import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
SECTORS=['XLB','XLE','XLF','XLI','XLK','XLP','XLU','XLV','XLY']
COSTS=(25,50,100)
WINDOWS={'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}

def cagr(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')
def stats(r):
 r=pd.Series(r,dtype=float).dropna(); eq=(1+r).cumprod(); vol=float(r.std(ddof=1)*math.sqrt(12)); return {'cagr':cagr(r),'sharpe_rf0':float(r.mean()*12/vol) if vol else None,'maxdd':float((eq/eq.cummax()-1).min())}
def evaluate(q,cost_bps):
 z=q.copy(); z['net']=z.gross-z.turnover*cost_bps/10000
 risky=float(z.risky_exposure.mean()); z['matched']=risky*z.ew_sector
 out={k:stats(z[k]) for k in ('net','matched','spy')}
 out.update({'excess_matched':out['net']['cagr']-out['matched']['cagr'],'excess_spy':out['net']['cagr']-out['spy']['cagr'],'months':len(z),'mean_risky_exposure':risky,'mean_turnover':float(z.turnover.mean())})
 folds=[]
 for j,idx in enumerate(np.array_split(np.arange(len(z)),5),1):
  a=z.iloc[idx]; rr=float(a.risky_exposure.mean()); m=rr*a.ew_sector
  folds.append({'fold':j,'matched_excess':cagr(a.net)-cagr(m),'spy_excess':cagr(a.net)-cagr(a.spy)})
 out['positive_matched_folds']=sum(x['matched_excess']>0 for x in folds); out['positive_spy_folds']=sum(x['spy_excess']>0 for x in folds); out['folds']=folds
 return out

def main():
 tickers=SECTORS+['SPY']
 px=yf.download(tickers,start='2000-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna(how='all').astype(float)
 last=pd.Timestamp(px.index.max()); last=last.tz_localize(None) if last.tzinfo else last
 cut=last.to_period('M').start_time-pd.Timedelta(days=1); px=px.loc[px.index<=cut]
 m=px.resample('ME').last().dropna(); r=m.pct_change(fill_method=None)
 mom=(m.shift(1)/m.shift(12)-1)[SECTORS]  # prior 11 completed months, skipping current signal month
 prev_w={s:0.0 for s in SECTORS}; rows=[]
 for i,dt in enumerate(m.index[:-1]):
  sig=mom.loc[dt]
  if i<12 or sig.isna().any(): continue
  positive=sig[sig>0].sort_values(ascending=False).head(2).index.tolist()
  w={s:(1.0/len(positive) if s in positive and positive else 0.0) for s in SECTORS}
  risky=sum(w.values()); turnover=0.5*(sum(abs(w[s]-prev_w[s]) for s in SECTORS)+abs((1-risky)-(1-sum(prev_w.values()))))
  nxt=m.index[i+1]; rr=r.loc[nxt]; gross=sum(w[s]*float(rr[s]) for s in SECTORS)
  rows.append({'return_month':nxt,'gross':gross,'turnover':turnover,'risky_exposure':risky,'ew_sector':float(rr[SECTORS].mean()),'spy':float(rr['SPY'])})
  prev_w=w
 q=pd.DataFrame(rows).set_index('return_month')
 tests={w:{str(c):evaluate(q.loc[pd.Timestamp(start):],c) for c in COSTS} for w,start in WINDOWS.items()}
 a=tests['2015']['50']; b=tests['2020']['50']
 decision='P151_SECTOR_CROSS_SECTIONAL_SUPPORTED_FOR_INDEPENDENT_VALIDATION' if a['excess_matched']>0 and a['excess_spy']>0 and a['positive_matched_folds']>=3 and b['excess_matched']>0 and b['positive_matched_folds']>=3 else 'P151_SECTOR_CROSS_SECTIONAL_NOT_SUPPORTED'
 out={'schema':'research.p151_sector_cross_sectional_momentum_r1','parent':'P151','hypothesis':'A fixed cross-sectional 12-1 momentum rule across nine SPDR sectors, holding up to the top two positive-momentum sectors next month and otherwise cash, creates after-cost excess versus exposure-matched static sector beta and SPY.','contract':{'universe':SECTORS,'signal':'rank prior 11 completed months via price[t-1]/price[t-12]-1','selection':'up to top two sectors with positive signal, equal weight; residual cash','rebalance':'monthly using only completed-month data','cost_bps':list(COSTS),'matched_control':'mean risky exposure times equal-weight nine-sector basket','opportunity_control':'SPY','windows':list(WINDOWS),'folds':5,'no_asset_horizon_threshold_weight_or_cost_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cut.date()),'panel_sha256':hashlib.sha256(px.reset_index().to_csv(index=False).encode()).hexdigest()},'tests':tests,'decision':decision}
 Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p151_sector_cross_sectional_momentum_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()

from __future__ import annotations
import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
S=['XLB','XLE','XLF','XLI','XLK','XLP','XLU','XLV','XLY']; COSTS=(25,50,100); W={'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}
def cagr(r): r=pd.Series(r).dropna(); return float((1+r).prod()**(12/len(r))-1)
def st(r):
 r=pd.Series(r).dropna(); e=(1+r).cumprod(); v=float(r.std(ddof=1)*math.sqrt(12)); return {'cagr':cagr(r),'sharpe_rf0':float(r.mean()*12/v) if v else None,'maxdd':float((e/e.cummax()-1).min())}
def ev(q,c):
 z=q.copy(); z['net']=z.gross-z.turnover*c/10000; z['matched']=z.ew; o={k:st(z[k]) for k in ['net','matched','spy']}; o.update({'excess_matched':o['net']['cagr']-o['matched']['cagr'],'excess_spy':o['net']['cagr']-o['spy']['cagr'],'months':len(z),'mean_turnover':float(z.turnover.mean())}); f=[]
 for j,idx in enumerate(np.array_split(np.arange(len(z)),5),1):
  a=z.iloc[idx]; f.append({'fold':j,'matched_excess':cagr(a.net)-cagr(a.matched),'spy_excess':cagr(a.net)-cagr(a.spy)})
 o['positive_matched_folds']=sum(x['matched_excess']>0 for x in f); o['positive_spy_folds']=sum(x['spy_excess']>0 for x in f); o['folds']=f; return o
def main():
 px=yf.download(S+['SPY'],start='2000-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna().astype(float); last=pd.Timestamp(px.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cut=last.to_period('M').start_time-pd.Timedelta(days=1); px=px.loc[px.index<=cut]; dr=px.pct_change(fill_method=None); rv=dr[S].rolling(63).std(ddof=1)*math.sqrt(252); m=px.resample('ME').last(); mr=m.pct_change(fill_method=None); prev={s:0 for s in S}; rows=[]
 for i,dt in enumerate(m.index[:-1]):
  ix=px.index[px.index<=dt]
  if len(ix)<63: continue
  v=rv.loc[ix[-1]]
  if v.isna().any(): continue
  pick=v.nsmallest(3).index; w={s:(1/3 if s in pick else 0) for s in S}; nxt=m.index[i+1]; rr=mr.loc[nxt]; to=.5*sum(abs(w[s]-prev[s]) for s in S); rows.append({'return_month':nxt,'gross':sum(w[s]*float(rr[s]) for s in S),'turnover':to,'ew':float(rr[S].mean()),'spy':float(rr.SPY)}); prev=w
 q=pd.DataFrame(rows).set_index('return_month'); tests={k:{str(c):ev(q.loc[pd.Timestamp(s):],c) for c in COSTS} for k,s in W.items()}; a=tests['2015']['50']; b=tests['2020']['50']; d='P155_SECTOR_LOWVOL_SUPPORTED_FOR_INDEPENDENT_VALIDATION' if a['excess_matched']>0 and a['positive_matched_folds']>=3 and b['excess_matched']>0 and b['positive_matched_folds']>=3 else 'P155_SECTOR_LOWVOL_NOT_SUPPORTED'; out={'schema':'research.p155_sector_lowvol_r1','parent':'P155','hypothesis':'Monthly selection of the three lowest trailing-63-session-volatility SPDR sectors creates after-cost excess versus the fully invested equal-weight sector basket and SPY.','contract':{'universe':S,'signal':'trailing 63-session realized volatility at completed month end','selection':'three lowest volatility sectors, equal weight','cost_bps':list(COSTS),'matched_control':'equal-weight nine-sector basket','opportunity_control':'SPY','windows':list(W),'folds':5,'no_asset_lookback_topk_cost_or_window_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cut.date()),'panel_sha256':hashlib.sha256(px.reset_index().to_csv(index=False).encode()).hexdigest()},'tests':tests,'decision':d}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p155_sector_lowvol_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()

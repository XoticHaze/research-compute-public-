from __future__ import annotations
import json,math,hashlib
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
U=('XLE','XLF','XLK','XLV','XLY','XLP','XLI','XLB','XLU'); COSTS=(25,50,100)
def cagr(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')
def stats(r):
 r=pd.Series(r,dtype=float).dropna(); eq=(1+r).cumprod(); vol=float(r.std(ddof=1)*math.sqrt(12)) if len(r)>1 else float('nan'); ann=float(r.mean()*12) if len(r) else float('nan'); return {'cagr':cagr(r),'sharpe_rf0':ann/vol if vol and np.isfinite(vol) else None,'maxdd':float((eq/eq.cummax()-1).min()) if len(eq) else None}
def evaluate(q,cost):
 z=q.copy(); z['net']=z.gross-z.turnover*cost/10000; out={k:stats(z[k]) for k in ('net','matched','spy')}; out['excess_matched']=out['net']['cagr']-out['matched']['cagr']; out['excess_spy']=out['net']['cagr']-out['spy']['cagr']; out['months']=len(z); out['avg_turnover']=float(z.turnover.mean()); fs=[]
 for j,ii in enumerate(np.array_split(np.arange(len(z)),5),1):
  a=z.iloc[ii]; fs.append({'fold':j,'matched_excess':cagr(a.net)-cagr(a.matched),'spy_excess':cagr(a.net)-cagr(a.spy)})
 out['positive_matched_folds']=sum(x['matched_excess']>0 for x in fs); out['positive_spy_folds']=sum(x['spy_excess']>0 for x in fs); out['folds']=fs; return out
def main():
 px=yf.download(list((*U,'SPY')),start='2006-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna().astype(float); last=pd.Timestamp(px.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cut=last.to_period('M').start_time-pd.Timedelta(days=1); px=px.loc[px.index<=cut]; m=px.resample('ME').last(); r=m.pct_change(fill_method=None); prev={s:0. for s in U}; rows=[]
 for i,dt in enumerate(m.index[:-1]):
  sig=r.loc[dt,list(U)]
  if sig.isna().any(): continue
  nxt=m.index[i+1]; rr=r.loc[nxt,list(U)]
  if rr.isna().any(): continue
  chosen=list(sig.sort_values(ascending=True,kind='mergesort').head(2).index); w={s:(.5 if s in chosen else 0.) for s in U}; turn=.5*sum(abs(w[s]-prev[s]) for s in U); gross=sum(w[s]*float(rr[s]) for s in U); rows.append({'signal_month':dt,'return_month':nxt,'gross':gross,'turnover':turn,'matched':float(rr.mean()),'spy':float(r.loc[nxt,'SPY']),'chosen':'|'.join(chosen)}); prev=w
 q=pd.DataFrame(rows).set_index('return_month'); windows={'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}; tests={w:{str(c):evaluate(q.loc[pd.Timestamp(s):],c) for c in COSTS} for w,s in windows.items()}; a=tests['2015']['50']; b=tests['2020']['50']; decision='P135_SECTOR_REVERSAL_SUPPORTED_FOR_INDEPENDENT_VALIDATION' if a['excess_matched']>0 and a['positive_matched_folds']>=3 and b['excess_spy']>0 and b['positive_spy_folds']>=3 else 'P135_SECTOR_REVERSAL_NOT_SUPPORTED'
 out={'schema':'research.p135_sector_reversal_r1','parent':'P135','hypothesis':'One-month cross-sectional sector reversal: buy the two worst-performing legacy SPDR sectors from the prior completed month for the next month.','contract':{'universe':list(U),'signal':'prior completed-month return ascending','top_k':2,'cost_bps_turnover':list(COSTS),'matched_control':'equal-weight same sector universe','opportunity_control':'SPY','windows':list(windows),'folds':5,'no_lookback_topk_weight_or_cost_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cut.date()),'panel_sha256':hashlib.sha256(px.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()},'tests':tests,'decision':decision}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p135_sector_reversal_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()

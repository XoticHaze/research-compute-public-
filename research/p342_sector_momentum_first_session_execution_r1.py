from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
SECTORS=['XLB','XLE','XLF','XLI','XLK','XLP','XLU','XLV','XLY']; ALL=SECTORS+['SPY']; START='2003-01-01'; END='2026-09-10'; COST_BPS=25; TOP_K=3
raw=yf.download(ALL,start=START,end=END,auto_adjust=True,progress=False,threads=False)
daily=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[ALL].dropna(how='all')
month_end=daily.resample('ME').last(); first=daily.groupby(daily.index.to_period('M')).first(); first.index=first.index.to_timestamp('M')
score=month_end.shift(1)/month_end.shift(12)-1
rows=[]
for i,dt in enumerate(first.index[:-1]):
    if dt not in score.index: continue
    s=score.loc[dt,SECTORS].dropna(); p0=first.loc[dt,SECTORS].dropna(); ndt=first.index[i+1]; p1=first.loc[ndt,SECTORS].dropna(); avail=s.index.intersection(p0.index).intersection(p1.index)
    if len(avail)<TOP_K: continue
    top=s.loc[avail].nlargest(TOP_K).index; rr=p1.loc[avail]/p0.loc[avail]-1; spy=float(first.loc[ndt,'SPY']/first.loc[dt,'SPY']-1)
    rows.append((dt,float(rr.loc[top].mean()),float(rr.mean()),spy,tuple(top)))
z=pd.DataFrame(rows,columns=['date','gross','matched','spy','top']).set_index('date'); prev=set(); net=[]; turns=[]
for _,r in z.iterrows():
    cur=set(r.top); turn=1.0 if not prev else 1.0-len(prev&cur)/TOP_K; net.append(r.gross-turn*COST_BPS/10000); turns.append(turn); prev=cur
z['strategy']=net; z['turnover']=turns
def stats(s):
    s=s.dropna(); w=(1+s).cumprod(); yrs=len(s)/12; sd=s.std(); return {'months':int(len(s)),'cagr':float(w.iloc[-1]**(1/yrs)-1),'sharpe':float(s.mean()/sd*math.sqrt(12)) if sd>0 else 0.0,'max_drawdown':float((w/w.cummax()-1).min())}
res={}
for name,start in {'2005_plus':'2005-01-01','2010_plus':'2010-01-01','2015_plus':'2015-01-01','2020_plus':'2020-01-01'}.items():
    q=z.loc[start:].dropna(); a,b,c=stats(q.strategy),stats(q.matched),stats(q.spy); res[name]={'strategy':a,'matched':b,'spy':c,'matched_excess_cagr':a['cagr']-b['cagr'],'spy_gap_cagr':a['cagr']-c['cagr'],'mean_turnover':float(q.turnover.mean())}
q=z.loc['2005-01-01':].dropna(); folds=[stats(f.strategy)['cagr']-stats(f.matched)['cagr'] for f in np.array_split(q,5)]; passed=all(res[k]['matched_excess_cagr']>0 for k in res) and sum(x>0 for x in folds)>=4
decision='P342_FIRST_SESSION_EXECUTION_SUPPORTED' if passed else 'P342_FIRST_SESSION_EXECUTION_NOT_SUPPORTED'
out={'schema':'research.p342_sector_momentum_first_session_execution_r1','parent':'P330/P339/P341','claim':'Orthogonal implementation/causality adjudicator: hold the frozen nine-sector top-3 12-1-equivalent rule fixed, form the signal only from completed prior month-end closes, delay executable entry to the first trading-session close of the next month, hold to the next first-session close, and charge 25bp one-way turnover. No universe, lookback, top-k, cost, date, threshold, or allocation tuning.','universe':SECTORS,'cost_bps':COST_BPS,'execution_timing':'signal from prior month-end; enter first trading-session close; rebalance next first-session close','results':res,'chronology_fold_matched_excess_cagr':folds,'positive_folds':sum(x>0 for x in folds),'decision_rule':'Support practical timing robustness only if after-cost matched excess is positive in every fixed window and >=4/5 chronology folds. Failure narrows the survivor to month-boundary-sensitive implementation evidence without parameter rescue; it does not erase prior source/representation passes.','decision':decision,'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p342_sector_momentum_first_session_execution_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
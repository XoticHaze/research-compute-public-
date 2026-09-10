from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf

SECTORS=['XLB','XLC','XLE','XLF','XLI','XLK','XLP','XLRE','XLU','XLV','XLY']
ALL=SECTORS+['SPY']
START='2001-01-01'; END='2026-09-10'; COST_BPS=25; TOP_K=3
raw=yf.download(ALL,start=START,end=END,auto_adjust=True,progress=False,threads=False)
close=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[ALL]
px=close.resample('ME').last().dropna(how='all')
ret=px.pct_change()
# 12-1 momentum: price at t-1 divided by price at t-12, formed with information known at month-end t.
score=px.shift(1)/px.shift(12)-1
rows=[]
for dt in ret.index:
    s=score.loc[dt,SECTORS].dropna()
    rr=ret.loc[dt,SECTORS].dropna()
    avail=s.index.intersection(rr.index)
    if len(avail)<TOP_K: continue
    top=s.loc[avail].nlargest(TOP_K).index
    strat=float(rr.loc[top].mean())
    base=float(rr.loc[avail].mean())
    spy=float(ret.loc[dt,'SPY']) if pd.notna(ret.loc[dt,'SPY']) else np.nan
    rows.append((dt,strat,base,spy,tuple(top)))
z=pd.DataFrame(rows,columns=['date','gross','equal_sector','spy','top']).set_index('date')
# Charge turnover using equal-weight top-3 sleeves. Initial entry is fully charged.
prev=set(); net=[]; turns=[]
for _,r in z.iterrows():
    cur=set(r['top'])
    overlap=len(prev & cur) if prev else 0
    turnover=1.0 if not prev else 1.0-overlap/TOP_K
    net.append(r['gross']-turnover*COST_BPS/10000)
    turns.append(turnover)
    prev=cur
z['strategy']=net; z['turnover']=turns

def stats(s):
    s=s.dropna(); w=(1+s).cumprod(); yrs=len(s)/12; sd=s.std()
    return {'months':int(len(s)),'cagr':float(w.iloc[-1]**(1/yrs)-1),'sharpe':float(s.mean()/sd*math.sqrt(12)) if sd>0 else 0.0,'max_drawdown':float((w/w.cummax()-1).min())}
res={}
for name,start in {'2005_plus':'2005-01-01','2010_plus':'2010-01-01','2015_plus':'2015-01-01','2020_plus':'2020-01-01'}.items():
    q=z.loc[start:].dropna(subset=['strategy','equal_sector','spy'])
    a,b,c=stats(q.strategy),stats(q.equal_sector),stats(q.spy)
    res[name]={'strategy':a,'equal_sector_matched':b,'spy_context':c,'matched_excess_cagr':a['cagr']-b['cagr'],'spy_opportunity_gap_cagr':a['cagr']-c['cagr'],'mean_monthly_turnover':float(q.turnover.mean())}
q=z.loc['2005-01-01':].dropna(subset=['strategy','equal_sector'])
folds=[]
for f in np.array_split(q,5):
    folds.append(stats(f.strategy)['cagr']-stats(f.equal_sector)['cagr'])
passed=all(res[k]['matched_excess_cagr']>0 for k in res) and sum(x>0 for x in folds)>=3
decision='P330_SECTOR_CROSSSECTIONAL_MOMENTUM_SUPPORTED' if passed else 'P330_SECTOR_CROSSSECTIONAL_MOMENTUM_NOT_SUPPORTED'
out={'schema':'research.p330_sector_crosssectional_momentum_r1','parent':'P330','claim':'Test a fixed cross-sectional industry-allocation architecture: monthly select the top 3 available US sector ETFs by lagged 12-1 momentum, equal-weight them, and compare after 25bp turnover friction against the contemporaneous equal-weight sector universe plus SPY opportunity context. Fixed sector set, top-k, signal horizon, rebalance cadence, costs, windows, and chronology folds; no tuning or replacement search.','sector_universe':SECTORS,'top_k':TOP_K,'cost_bps':COST_BPS,'results':res,'chronology_fold_matched_excess_cagr':folds,'positive_folds':sum(x>0 for x in folds),'decision_rule':'Support only if after-cost matched excess CAGR is positive in all fixed windows and >=3/5 chronology folds. Failure rejects this fixed sector-ranking formulation without top-k, lookback, sector-set, rebalance, or cost rescue.','decision':decision,'limitations':['ETF sector proxies rather than constituent-level industry selection','XLRE and XLC have shorter histories so the available matched sector set expands through time','single adjusted-price provider','no portfolio ranking/allocation/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True)
Path('research/artifacts/p330_sector_crosssectional_momentum_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps(out,sort_keys=True))

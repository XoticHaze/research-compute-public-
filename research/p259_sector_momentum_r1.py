from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

SECTORS=['XLB','XLE','XLF','XLI','XLK','XLP','XLU','XLV','XLY']
ALL=SECTORS+['SPY']
WINDOWS={'2005':'2005-01-01','2010':'2010-01-01','2020':'2020-01-01','2022':'2022-01-01'}
TOPK=3; TURNOVER_BP=25

def metrics(r):
    q=pd.Series(r,dtype=float).dropna(); e=(1+q).cumprod(); n=len(q)
    ann=float(q.mean()*12); vol=float(q.std(ddof=1)*math.sqrt(12))
    return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1),'maxdd':float((e/e.cummax()-1).min()),'sharpe_rf0':float(ann/vol) if vol else None}

raw=yf.download(ALL,start='2003-01-01',end='2026-09-03',auto_adjust=True,progress=False,threads=False)
close=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
m=close[ALL].dropna().resample('ME').last(); r=m.pct_change(); mom=m[SECTORS].shift(1)/m[SECTORS].shift(12)-1
prev={s:0.0 for s in SECTORS}; rows=[]
for i in range(len(m)-1):
    dt=m.index[i]; nxt=m.index[i+1]; score=mom.loc[dt]
    if score.isna().any() or r.loc[nxt,SECTORS].isna().any(): continue
    chosen=score.sort_values(ascending=False).head(TOPK).index
    w={s:(1/TOPK if s in chosen else 0.0) for s in SECTORS}
    turnover=0.5*sum(abs(w[s]-prev[s]) for s in SECTORS)
    gross=sum(w[s]*float(r.loc[nxt,s]) for s in SECTORS)
    net=gross-turnover*TURNOVER_BP/10000
    matched=float(r.loc[nxt,SECTORS].mean()); spy=float(r.loc[nxt,'SPY'])
    rows.append((nxt,net,matched,spy,turnover,','.join(chosen)))
    prev=w
z=pd.DataFrame(rows,columns=['date','candidate','matched','spy','turnover','chosen']).set_index('date'); out={}
for name,start in WINDOWS.items():
    q=z.loc[z.index>=pd.Timestamp(start)].copy(); cm=metrics(q.candidate); mm=metrics(q.matched); sm=metrics(q.spy); folds=[]
    for j,ix in enumerate(np.array_split(np.arange(len(q)),5),1):
        a=metrics(q.candidate.iloc[ix]); b=metrics(q.matched.iloc[ix]); s=metrics(q.spy.iloc[ix])
        folds.append({'fold':j,'vs_matched_cagr':a['cagr']-b['cagr'],'vs_spy_cagr':a['cagr']-s['cagr']})
    out[name]={'candidate':cm,'matched_equal_sector':mm,'spy':sm,'matched_excess_cagr':cm['cagr']-mm['cagr'],'vs_spy_cagr':cm['cagr']-sm['cagr'],'positive_matched_folds':sum(x['vs_matched_cagr']>0 for x in folds),'average_monthly_turnover':float(q.turnover.mean()),'folds':folds}
a=out['2005']; b=out['2010']; c=out['2020']; d=out['2022']
support=(a['matched_excess_cagr']>0 and b['matched_excess_cagr']>0 and c['matched_excess_cagr']>0 and d['matched_excess_cagr']>0 and a['positive_matched_folds']>=4 and c['vs_spy_cagr']>0 and d['vs_spy_cagr']>0 and a['candidate']['maxdd']>=a['matched_equal_sector']['maxdd']-0.10)
res={'schema':'research.p259_sector_momentum_r1','parent':'P259','claim':'A prospectively fixed 12-1 cross-sectional momentum selector across the nine long-history US sector ETFs creates durable after-cost excess versus the same-universe equal-weight control and recent SPY opportunity cost.','contract':{'universe':SECTORS,'signal':'month-end 12-1 total-return momentum = prior-month close / close 12 months earlier - 1','selection':'top 3 equally weighted for next month','turnover_cost_bps':TURNOVER_BP,'matched_control':'monthly equal-weight return of same sector universe','opportunity_control':'SPY','windows':WINDOWS,'folds':5,'gate':'positive matched excess all windows; >=4/5 positive 2005+ matched folds; positive SPY excess 2020+ and 2022+; maxDD no worse than matched by >10pp','no_universe_horizon_topk_window_threshold_or_parameter_search':True},'tests':out,'decision':'P259_SECTOR_MOMENTUM_SUPPORTED' if support else 'P259_SECTOR_MOMENTUM_NOT_SUPPORTED','limitations':['ETF histories and adjusted prices are Yahoo research data','matched equal-weight control is not charged an additional turnover estimate, making the alpha test conservative for the candidate'],'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p259_sector_momentum_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(res,sort_keys=True))

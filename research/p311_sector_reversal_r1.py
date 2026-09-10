from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

SECTORS=['XLB','XLE','XLF','XLI','XLK','XLP','XLU','XLV','XLY']
SYMS=SECTORS+['SPY']; START='2003-01-01'; END='2026-09-10'; COST_BPS=25; BOTTOM_K=3
raw=yf.download(SYMS,start=START,end=END,auto_adjust=True,progress=False,threads=False)
px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[SYMS].dropna(); month_px=px.resample('ME').last(); ret=month_px.pct_change()
signal=ret[SECTORS].shift(1)
weights=pd.DataFrame(0.0,index=month_px.index,columns=SECTORS)
for dt,row in signal.iterrows():
    valid=row.dropna()
    if len(valid)>=BOTTOM_K:
        pick=valid.nsmallest(BOTTOM_K).index; weights.loc[dt,pick]=1.0/BOTTOM_K
w=weights.fillna(0.0); gross=(w*ret[SECTORS]).sum(axis=1); turnover=w.diff().abs().sum(axis=1).fillna(w.abs().sum(axis=1)); net=gross-turnover*(COST_BPS/10000); matched=ret[SECTORS].mean(axis=1); spy=ret.SPY
valid=(w.sum(axis=1)>0)&net.notna()&matched.notna()&spy.notna(); net=net[valid]; matched=matched[valid]; spy=spy[valid]
def stats(s):
    s=s.dropna(); w=(1+s).cumprod(); yrs=len(s)/12; sd=s.std(); return {'months':int(len(s)),'cagr':float(w.iloc[-1]**(1/yrs)-1),'sharpe':float(s.mean()/sd*math.sqrt(12)) if sd>0 else 0.0,'max_drawdown':float((w/w.cummax()-1).min())}
def win(a):
    n=net.loc[net.index>=pd.Timestamp(a)]; b=matched.loc[n.index]; s=spy.loc[n.index]; ns,bs,ss=stats(n),stats(b),stats(s); return {'model':ns,'matched_equal_sector':bs,'spy':ss,'matched_excess_cagr':ns['cagr']-bs['cagr'],'spy_excess_cagr':ns['cagr']-ss['cagr'],'drawdown_delta_vs_matched':ns['max_drawdown']-bs['max_drawdown']}
results={k:win(v) for k,v in {'2005_plus':'2005-01-01','2015_plus':'2015-01-01','2020_plus':'2020-01-01'}.items()}; z=pd.DataFrame({'m':net,'b':matched}).loc['2005-01-01':].dropna(); folds=[stats(p.m)['cagr']-stats(p.b)['cagr'] for p in np.array_split(z,5)]
passes=(all(results[k]['matched_excess_cagr']>0 for k in results) and sum(x>0 for x in folds)>=3 and all(results[k]['drawdown_delta_vs_matched']>=-0.05 for k in results)); decision='P311_SECTOR_REVERSAL_SUPPORTED' if passes else 'P311_SECTOR_REVERSAL_NOT_SUPPORTED'
out={'schema':'research.p311_sector_reversal_r1','parent':'P311','claim':'Test one orthogonal cross-sectional sector architecture: monthly equal-weight bottom-3 of nine long-history SPDR sectors by prior-month return, after 25 bp turnover cost, against equal-weight same-sector matched control and SPY. No horizon, k, universe, window, or cost tuning.','universe':SECTORS,'signal':'prior-month return, select bottom 3','bottom_k':BOTTOM_K,'cost_bps':COST_BPS,'results':results,'chronology_fold_matched_excess_cagr':folds,'positive_folds':sum(x>0 for x in folds),'decision_rule':'Support only if after-cost matched excess CAGR is positive in 2005+, 2015+, 2020+, >=3/5 chronology folds positive, and max drawdown is not >5pp worse than matched in any fixed window.','decision':decision,'limitations':['fixed ETF sector universe','same adjusted-price provider','single predeclared reversal architecture','no parameter rescue','no allocation/ranking/product/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p311_sector_reversal_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))

from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

SECTORS=['XLB','XLE','XLF','XLI','XLK','XLP','XLU','XLV','XLY']
SYMS=SECTORS+['SPY']
START='2003-01-01'; END='2026-09-10'; COST_BPS=25; TOP_K=3
raw=yf.download(SYMS,start=START,end=END,auto_adjust=True,progress=False,threads=False)
px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[SYMS].dropna()
month_px=px.resample('ME').last(); ret=month_px.pct_change(); mom=month_px[SECTORS].shift(1)/month_px[SECTORS].shift(12)-1
weights=pd.DataFrame(0.0,index=month_px.index,columns=SECTORS)
for dt,row in mom.iterrows():
    valid=row.dropna()
    if len(valid)>=TOP_K:
        top=valid.nlargest(TOP_K).index
        weights.loc[dt,top]=1.0/TOP_K
# weights decided from information available through previous month; apply to current month return
w=weights.shift(1).fillna(0.0)
gross=(w*ret[SECTORS]).sum(axis=1)
turnover=w.diff().abs().sum(axis=1).fillna(w.abs().sum(axis=1))
net=gross-turnover*(COST_BPS/10000)
matched=ret[SECTORS].mean(axis=1)
spy=ret.SPY
valid=(w.sum(axis=1)>0)&net.notna()&matched.notna()&spy.notna()
net=net[valid]; matched=matched[valid]; spy=spy[valid]

def stats(s):
    s=s.dropna(); wealth=(1+s).cumprod(); yrs=len(s)/12; sd=s.std()
    return {'months':int(len(s)),'cagr':float(wealth.iloc[-1]**(1/yrs)-1),'sharpe':float(s.mean()/sd*math.sqrt(12)) if sd>0 else 0.0,'max_drawdown':float((wealth/wealth.cummax()-1).min())}

def win(start):
    n=net.loc[net.index>=pd.Timestamp(start)]; b=matched.loc[n.index]; s=spy.loc[n.index]
    ns,bs,ss=stats(n),stats(b),stats(s)
    return {'model':ns,'matched_equal_sector':bs,'spy':ss,'matched_excess_cagr':ns['cagr']-bs['cagr'],'spy_excess_cagr':ns['cagr']-ss['cagr'],'drawdown_delta_vs_matched':ns['max_drawdown']-bs['max_drawdown']}

windows={k:win(v) for k,v in {'2005_plus':'2005-01-01','2015_plus':'2015-01-01','2020_plus':'2020-01-01'}.items()}
z=pd.DataFrame({'m':net,'b':matched}).loc['2005-01-01':].dropna(); folds=[]
for part in np.array_split(z,5): folds.append(stats(part.m)['cagr']-stats(part.b)['cagr'])
passes=(all(windows[k]['matched_excess_cagr']>0 for k in windows) and sum(x>0 for x in folds)>=3 and all(windows[k]['drawdown_delta_vs_matched']>=-0.05 for k in windows))
decision='P310_SECTOR_CROSSSECTION_MOMENTUM_SUPPORTED' if passes else 'P310_SECTOR_CROSSSECTION_MOMENTUM_NOT_SUPPORTED'
out={'schema':'research.p310_sector_crosssection_momentum_r1','parent':'P310','claim':'Test one fixed cross-sectional sector-selection architecture: monthly top-3 of nine long-history SPDR sectors by 12-to-1 momentum, equal-weight, 25 bp turnover cost, against equal-weight same-sector matched control and SPY opportunity control. No top-k/lookback/universe/window tuning.','universe':SECTORS,'signal':'12-to-1 month momentum using information available through prior month','top_k':TOP_K,'cost_bps':COST_BPS,'results':windows,'chronology_fold_matched_excess_cagr':folds,'positive_folds':sum(x>0 for x in folds),'decision_rule':'Support only if after-cost matched excess CAGR is positive in 2005+, 2015+, and 2020+, at least 3/5 chronological folds are positive, and model max drawdown is not more than 5 percentage points worse than the matched sector baseline in any fixed window.','decision':decision,'limitations':['fixed ETF sector universe, not point-in-time constituent selection','same adjusted-price provider','one predeclared cross-sectional architecture only','no parameter/weight/window rescue','no allocation/ranking/product/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p310_sector_crosssection_momentum_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))

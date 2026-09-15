import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

TICKERS=['XLB','XLE','XLF','XLI','XLK','XLP','XLU','XLV','XLY']
START='2007-01-01'; COST=0.001
OUT=Path('artifacts/sector-overnight-gap-intraday-r1'); OUT.mkdir(parents=True,exist_ok=True)
px=yf.download(TICKERS,start=START,auto_adjust=True,progress=False,group_by='column')
opens=px['Open'][TICKERS].dropna(how='all'); closes=px['Close'][TICKERS].reindex(opens.index)
# Information at each day's open: overnight gap from prior close to today's open.
gap=opens/closes.shift(1)-1
intraday=closes/opens-1
valid=gap.notna() & intraday.notna()
# Frozen signal: top 3 positive overnight gaps; if fewer than 3 positive, hold available positives; otherwise cash.
ranks=gap.rank(axis=1,ascending=False,method='first')
sel=(ranks<=3)&(gap>0)&valid
n=sel.sum(axis=1)
gross=(intraday.where(sel).sum(axis=1)/n.replace(0,np.nan)).fillna(0)
# Equal-weight same-universe intraday matched control.
ctrl=intraday.where(valid).mean(axis=1).fillna(0)
# One round trip per active day, 10 bp one-way.
net=gross-(n>0).astype(float)*(2*COST)
ctrl_net=ctrl-2*COST

def stats(r):
 r=r.dropna(); yrs=len(r)/252
 wealth=(1+r).cumprod(); cagr=float(wealth.iloc[-1]**(1/yrs)-1) if yrs>0 else float('nan')
 dd=float((wealth/wealth.cummax()-1).min())
 sh=float(np.sqrt(252)*r.mean()/r.std()) if r.std()>0 else float('nan')
 return {'n':int(len(r)),'cagr':cagr,'max_dd':dd,'sharpe':sh}
windows=['2008-01-01','2012-01-01','2016-01-01','2020-01-01','2022-01-01']
res={'contract':{'signal':'top3 positive sector ETF overnight gaps known at open','hold':'same-day open-to-close','cost_one_way':COST,'primary_control':'equal-weight same 9 sector ETFs open-to-close, same round-trip cost','protected_boundary':'no ticker/top-k/gap-threshold/date/cost/control rescue'},'windows':{}}
for s in windows:
 c=stats(net.loc[s:]); b=stats(ctrl_net.loc[s:]); res['windows'][s]={'candidate':c,'control':b,'excess_cagr':c['cagr']-b['cagr']}
# Four fixed chronology folds from 2012 onward.
idx=net.loc['2012-01-01':].index; chunks=np.array_split(idx,4); folds=[]
for ch in chunks:
 c=stats(net.loc[ch]); b=stats(ctrl_net.loc[ch]); folds.append({'start':str(ch[0].date()),'end':str(ch[-1].date()),'candidate':c,'control':b,'excess_cagr':c['cagr']-b['cagr']})
res['folds']=folds
w=res['windows']; positives=sum(x['excess_cagr']>0 for x in folds)
# Support requires positive excess in 2012+ and 2020+, >=3/4 folds, and no worse max DD than control by >5pp in 2012+.
support=w['2012-01-01']['excess_cagr']>0 and w['2020-01-01']['excess_cagr']>0 and positives>=3 and w['2012-01-01']['candidate']['max_dd']>=w['2012-01-01']['control']['max_dd']-0.05
res['classification']='SECTOR_OVERNIGHT_GAP_INTRADAY_SUPPORTED' if support else 'SECTOR_OVERNIGHT_GAP_INTRADAY_REJECTED'
res['positive_folds']=positives
(OUT/'result.json').write_text(json.dumps(res,indent=2))
print(json.dumps(res,indent=2))

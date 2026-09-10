from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

SECTORS=['XLB','XLC','XLE','XLF','XLI','XLK','XLP','XLRE','XLU','XLV','XLY']
CONTROLS=['SPY','QQQ']
START='2009-01-01'; END='2026-09-10'; TOP=3; LOOKBACK_MONTHS=1
COSTS=[10.0,25.0,50.0]; WINDOWS={'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}

def metric(r):
    q=pd.Series(r,dtype=float).dropna(); e=(1+q).cumprod(); n=len(q)
    if n==0: return {'months':0,'cagr':None,'maxdd':None,'sharpe_rf0':None}
    vol=float(q.std(ddof=1)*math.sqrt(12)) if n>1 else 0.0; ann=float(q.mean()*12)
    return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1),'maxdd':float((e/e.cummax()-1).min()),'sharpe_rf0':float(ann/vol) if vol else None}

def turnover(a,b):
    return 0.5*sum(abs(b.get(s,0)-a.get(s,0)) for s in set(a)|set(b))

def folds(a,b,k=5):
    z=pd.DataFrame({'a':a,'b':b}).dropna(); out=[]
    for c in np.array_split(z,k):
        if len(c)>=6: out.append(metric(c.a)['cagr']-metric(c.b)['cagr'])
    return out

raw=yf.download(SECTORS+CONTROLS,start=START,end=END,auto_adjust=True,progress=False,threads=False)
px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[SECTORS+CONTROLS].dropna().sort_index()
m=px.resample('ME').last(); ret=m.pct_change(); score=m.pct_change(LOOKBACK_MONTHS).shift(1)
rows=[]; prev={}
for dt in m.index:
    s=score.loc[dt,SECTORS]
    if s.notna().sum()!=len(SECTORS): continue
    sel=sorted(SECTORS,key=lambda x:(s[x],x))[:TOP]
    w={x:1/TOP for x in sel}; t=turnover(prev,w); prev=w
    r=ret.loc[dt]
    if r[SECTORS+CONTROLS].isna().any(): continue
    gross=sum(wt*float(r[x]) for x,wt in w.items()); matched=float(r[SECTORS].mean())
    rows.append({'date':dt,**{f'model_{int(c)}':gross-t*c/10000 for c in COSTS},'matched':matched,'SPY':float(r.SPY),'QQQ':float(r.QQQ),'turnover':t,'selected':','.join(sel)})
r=pd.DataFrame(rows).set_index('date')
result={}
for name,start in WINDOWS.items():
    z=r.loc[r.index>=pd.Timestamp(start)]; m25=metric(z.model_25); mt=metric(z.matched); spy=metric(z.SPY); qqq=metric(z.QQQ); f=folds(z.model_25,z.matched)
    result[name]={'model_25bps':m25,'matched_equal_sector':mt,'SPY':spy,'QQQ':qqq,'matched_excess_cagr':m25['cagr']-mt['cagr'],'vs_SPY_cagr':m25['cagr']-spy['cagr'],'vs_QQQ_cagr':m25['cagr']-qqq['cagr'],'positive_matched_folds':sum(x>0 for x in f),'fold_count':len(f),'fold_excess_cagr':f,'matched_excess_10bps':metric(z.model_10)['cagr']-mt['cagr'],'matched_excess_50bps':metric(z.model_50)['cagr']-mt['cagr'],'mean_monthly_turnover':float(z.turnover.mean())}
p=result['2015']; q=result['2020']; s=result['2022']
passed=(p['matched_excess_cagr']>=0.01 and p['positive_matched_folds']>=4 and p['matched_excess_50bps']>0 and q['matched_excess_cagr']>0 and q['positive_matched_folds']>=3 and s['matched_excess_cagr']>0 and p['model_25bps']['maxdd']>=p['matched_equal_sector']['maxdd']-0.05)
out={'schema':'research.p279_sector_shortterm_reversal_r1','parent':'P279','hypothesis':'A prospectively fixed monthly cross-sectional short-term reversal rule that owns the prior-month bottom three US sector ETFs creates durable after-cost excess versus equal-weight exposure to the exact same sector universe.','parameters':{'sectors':SECTORS,'lookback_months':LOOKBACK_MONTHS,'top_n_losers':TOP,'rebalance':'month-end','costs_bps_per_one_way_turnover':COSTS,'primary_cost_bps':25.0,'windows':WINDOWS},'results':result,'decision_rule':'SUPPORTED_CANDIDATE only if 2015+ matched excess >=1pp CAGR, >=4/5 positive folds, positive matched excess at 50bps, positive 2020+ matched excess with >=3/5 folds, positive 2022+ matched excess, and max drawdown no more than 5pp worse than matched. Otherwise reject this frozen formulation without parameter rescue.','decision':'P279_SECTOR_SHORTTERM_REVERSAL_SUPPORTED_CANDIDATE' if passed else 'P279_SECTOR_SHORTTERM_REVERSAL_NOT_SUPPORTED','limitations':['Yahoo adjusted-price public research data','fixed one-month reversal signal only; no lookback/top-k/universe search','scientific evidence only; no portfolio allocation/ranking authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p279_sector_shortterm_reversal_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))

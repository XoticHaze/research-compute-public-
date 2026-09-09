from __future__ import annotations
import json, math, hashlib, io
from pathlib import Path
import numpy as np
import pandas as pd
import requests
import yfinance as yf

COSTS=(25,50,100)

def cagr(r):
    r=pd.Series(r,dtype=float).dropna()
    return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')

def stats(r):
    r=pd.Series(r,dtype=float).dropna(); eq=(1+r).cumprod()
    vol=float(r.std(ddof=1)*math.sqrt(12)) if len(r)>1 else float('nan')
    ann=float(r.mean()*12) if len(r) else float('nan')
    return {'cagr':cagr(r),'sharpe_rf0':ann/vol if vol and np.isfinite(vol) else None,'maxdd':float((eq/eq.cummax()-1).min()) if len(eq) else None}

def fred_dfii10():
    u='https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFII10'
    b=requests.get(u,timeout=30).content
    x=pd.read_csv(io.BytesIO(b)); x.columns=['date','real_yield']; x['date']=pd.to_datetime(x['date']); x['real_yield']=pd.to_numeric(x['real_yield'],errors='coerce'); x=x.dropna().set_index('date').sort_index()
    return x,b

def evaluate(q,cost):
    z=q.copy(); z['turnover']=(z.asset!=z.asset.shift()).astype(float); z.loc[z.index[0],'turnover']=1.0
    z['net']=z.gross-z.turnover*cost/10000
    out={k:stats(z[k]) for k in ('net','matched','qqq','spy')}
    out['excess_matched']=out['net']['cagr']-out['matched']['cagr']; out['excess_qqq']=out['net']['cagr']-out['qqq']['cagr']; out['excess_spy']=out['net']['cagr']-out['spy']['cagr']; out['avg_turnover']=float(z.turnover.mean()); out['months']=len(z)
    folds=[]
    for j,ii in enumerate(np.array_split(np.arange(len(z)),5),1):
        a=z.iloc[ii]; folds.append({'fold':j,'matched_excess':cagr(a.net)-cagr(a.matched),'qqq_excess':cagr(a.net)-cagr(a.qqq),'spy_excess':cagr(a.net)-cagr(a.spy)})
    out['positive_matched_folds']=sum(f['matched_excess']>0 for f in folds); out['positive_qqq_folds']=sum(f['qqq_excess']>0 for f in folds); out['positive_spy_folds']=sum(f['spy_excess']>0 for f in folds); out['folds']=folds
    return out

def main():
    ry,raw=fred_dfii10(); px=yf.download(['GLD','QQQ','SPY'],start='2007-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna().astype(float)
    last=pd.Timestamp(px.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cutoff=last.to_period('M').start_time-pd.Timedelta(days=1); px=px.loc[px.index<=cutoff]
    m=px.resample('ME').last(); r=m.pct_change(fill_method=None)
    rm=ry.resample('ME').last().reindex(m.index,method='ffill'); d3=rm.real_yield-rm.real_yield.shift(3)
    rows=[]
    for i,dt in enumerate(m.index[:-1]):
        if pd.isna(d3.loc[dt]): continue
        nxt=m.index[i+1]; rr=r.loc[nxt]
        if rr.isna().any(): continue
        # Economic sign hypothesis: falling real yields support gold; non-falling real yields favor growth equity.
        asset='GLD' if d3.loc[dt] < 0 else 'QQQ'
        rows.append({'signal_month':dt,'return_month':nxt,'real_yield':float(rm.loc[dt,'real_yield']),'real_yield_change_3m':float(d3.loc[dt]),'asset':asset,'gross':float(rr[asset]),'matched':float(.5*rr.GLD+.5*rr.QQQ),'qqq':float(rr.QQQ),'spy':float(rr.SPY)})
    q=pd.DataFrame(rows).set_index('return_month')
    windows={'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}; tests={}
    for w,s in windows.items(): tests[w]={str(c):evaluate(q.loc[pd.Timestamp(s):],c) for c in COSTS}
    t=tests['2015']['50']; u=tests['2020']['50']
    decision='P129_REAL_YIELD_ROTATION_SUPPORTED_FOR_INDEPENDENT_VALIDATION' if (t['excess_matched']>0 and t['positive_matched_folds']>=3 and u['excess_qqq']>0 and u['positive_qqq_folds']>=3) else 'P129_REAL_YIELD_ROTATION_NOT_SUPPORTED'
    out={'schema':'research.p129_real_yield_rotation_r1','parent':'P129','hypothesis':'Use only the sign of the prior completed month three-month change in 10Y TIPS real yield: falling real yields select GLD for the next month, otherwise QQQ.','contract':{'real_yield_series':'FRED DFII10','signal':'3 completed-month change < 0','assets':['GLD','QQQ'],'allocation':'100% selected asset monthly','cost_bps':list(COSTS),'matched_control':'static 50/50 GLD/QQQ','opportunity_controls':['QQQ','SPY'],'windows':list(windows),'folds':5,'no_threshold_horizon_weight_or_cost_search':True},'source':{'fred_sha256':hashlib.sha256(raw).hexdigest(),'price_provider':'Yahoo Finance via yfinance; research-only','price_panel_sha256':hashlib.sha256(px.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest(),'last_complete_month_end':str(cutoff.date())},'tests':tests,'decision':decision}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p129_real_yield_rotation_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()

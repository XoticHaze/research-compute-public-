"""Independent implementation replication of frozen UUP->SPY/EFA dollar-regime mechanism.
No parameter tuning: prior completed month UUP >= +2% => SPY next month, else EFA.
Transport repair after Stooq disabled anonymous ETF history: use Yahoo chart JSON directly,
without yfinance and without changing any frozen scientific parameter.
"""
import json, datetime as dt
import pandas as pd
import numpy as np
import requests

START='2011-01-01'; END='2026-09-16'; COST=.001

def yahoo_chart(ticker):
    p1=int(dt.datetime(2011,1,1,tzinfo=dt.timezone.utc).timestamp())
    p2=int(dt.datetime(2026,9,17,tzinfo=dt.timezone.utc).timestamp())
    url=f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}'
    resp=requests.get(url,params={'period1':p1,'period2':p2,'interval':'1d','events':'history','includeAdjustedClose':'true'},headers={'User-Agent':'Mozilla/5.0'},timeout=30)
    resp.raise_for_status()
    result=resp.json()['chart']['result'][0]
    ts=pd.to_datetime(result['timestamp'],unit='s',utc=True).tz_convert(None).normalize()
    q=result['indicators']['adjclose'][0]['adjclose']
    s=pd.Series(q,index=ts,dtype='float64').dropna().rename(ticker)
    if s.empty: raise RuntimeError(f'no Yahoo chart adjusted-close data for {ticker}')
    return s

px={t:yahoo_chart(t) for t in ['UUP','SPY','EFA']}
df=pd.concat(px.values(),axis=1).dropna()
m=df.resample('ME').last()
r=m.pct_change()
sig=(r.UUP.shift(1)>=.02).astype(float)
gross=sig*r.SPY+(1-sig)*r.EFA
turn=sig.diff().abs().fillna(sig.iloc[0])
net=gross-turn*COST

def stats(ret):
    ret=ret.dropna(); yrs=len(ret)/12
    eq=(1+ret).cumprod(); cagr=eq.iloc[-1]**(1/yrs)-1
    dd=(eq/eq.cummax()-1).min()
    return {'cagr':float(cagr),'max_drawdown':float(dd),'months':int(len(ret))}
def sl(a,b): return net.loc[a:b],sig.loc[a:b],r.loc[a:b]
def evaluate(a,b):
    rr,ss,raw=sl(a,b); p=float(ss.mean()); matched=p*raw.SPY+(1-p)*raw.EFA
    cs=stats(rr); ms=stats(matched)
    return {'candidate':cs,'matched':ms,'spy_participation':p,'excess_cagr_pp':100*(cs['cagr']-ms['cagr'])}
windows={'2012_plus':evaluate('2012-01-01',END),'2018_plus':evaluate('2018-01-01',END),'2022_plus':evaluate('2022-01-01',END)}
blocks={'2012_2015':evaluate('2012-01-01','2015-12-31'),'2016_2019':evaluate('2016-01-01','2019-12-31'),'2020_2022':evaluate('2020-01-01','2022-12-31'),'2023_plus':evaluate('2023-01-01',END)}
pos=sum(v['excess_cagr_pp']>0 for v in blocks.values())
w=windows['2012_plus']; support=(all(v['excess_cagr_pp']>0 for v in windows.values()) and pos>=3 and w['candidate']['max_drawdown']>=w['matched']['max_drawdown']-.05)
out={'schema':'research.uup_efa_dollar_regime_replication_r2.v2','replication':'independent direct Yahoo chart JSON implementation after Stooq anonymous transport failure','frozen_mechanism':'prior completed calendar-month UUP return >= +2% => SPY next month; otherwise EFA','cost_one_way':COST,'matched_control':'static SPY/EFA mixture matched to realized SPY participation','windows':windows,'blocks':blocks,'positive_blocks':pos,'decision':'UUP_EFA_DOLLAR_REGIME_REPLICATION_SUPPORTED' if support else 'UUP_EFA_DOLLAR_REGIME_REPLICATION_REJECTED','protected_boundary':'no UUP threshold/proxy/regional ETF/horizon/cost/date/control/block rescue','independence_note':'implementation/transport independent of yfinance; underlying vendor is Yahoo, so this is not an independent-vendor replication'}
print('RESULT_JSON='+json.dumps(out,sort_keys=True))

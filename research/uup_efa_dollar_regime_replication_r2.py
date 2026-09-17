"""Independent replication of frozen UUP->SPY/EFA dollar-regime mechanism.
No parameter tuning: prior completed month UUP >= +2% => SPY next month, else EFA.
Uses Stooq's public CSV endpoint directly, independent of the original yfinance implementation.
"""
import io, json
import pandas as pd
import numpy as np
import requests

START='2011-01-01'; END='2026-09-16'; COST=.001

def stooq(ticker):
    symbol=ticker.lower()+'.us'
    url=f'https://stooq.com/q/d/l/?s={symbol}&d1=20110101&d2=20260916&i=d'
    resp=requests.get(url,timeout=30)
    resp.raise_for_status()
    d=pd.read_csv(io.StringIO(resp.text),parse_dates=['Date']).set_index('Date').sort_index()
    if 'Close' not in d or d.empty:
        raise RuntimeError(f'no Stooq close data for {ticker}')
    return d['Close'].rename(ticker)

px={t:stooq(t) for t in ['UUP','SPY','EFA']}
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
out={'schema':'research.uup_efa_dollar_regime_replication_r2.v1','replication':'independent direct Stooq CSV data-source implementation','frozen_mechanism':'prior completed calendar-month UUP return >= +2% => SPY next month; otherwise EFA','cost_one_way':COST,'matched_control':'static SPY/EFA mixture matched to realized SPY participation','windows':windows,'blocks':blocks,'positive_blocks':pos,'decision':'UUP_EFA_DOLLAR_REGIME_REPLICATION_SUPPORTED' if support else 'UUP_EFA_DOLLAR_REGIME_REPLICATION_REJECTED','protected_boundary':'no UUP threshold/proxy/regional ETF/horizon/cost/date/control/block rescue'}
print('RESULT_JSON='+json.dumps(out,sort_keys=True))

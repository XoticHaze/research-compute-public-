"""Independent replication of frozen UUP->SPY/EFA dollar-regime mechanism.
No parameter tuning: prior completed month UUP >= +2% => SPY next month, else EFA.
Uses Stooq via pandas_datareader as an independent data-source implementation.
"""
import json, math, subprocess, sys
try:
 import pandas as pd, numpy as np
 from pandas_datareader import data as web
except ImportError:
 subprocess.check_call([sys.executable,'-m','pip','install','-q','pandas','numpy','pandas_datareader'])
 import pandas as pd, numpy as np
 from pandas_datareader import data as web

START='2011-01-01'; END='2026-09-16'; COST=.001
px={}
for t in ['UUP','SPY','EFA']:
 d=web.DataReader(t,'stooq',START,END).sort_index()
 px[t]=d['Close'].rename(t)
df=pd.concat(px.values(),axis=1).dropna()
m=df.resample('ME').last()
r=m.pct_change()
sig=(r.UUP.shift(1)>=.02).astype(float)
# Monthly close-to-close replication. Signal known after prior month close.
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
 # static control has no tactical switches; frozen comparison is exposure mixture
 cs=stats(rr); ms=stats(matched)
 return {'candidate':cs,'matched':ms,'spy_participation':p,'excess_cagr_pp':100*(cs['cagr']-ms['cagr'])}
windows={'2012_plus':evaluate('2012-01-01',END),'2018_plus':evaluate('2018-01-01',END),'2022_plus':evaluate('2022-01-01',END)}
blocks={'2012_2015':evaluate('2012-01-01','2015-12-31'),'2016_2019':evaluate('2016-01-01','2019-12-31'),'2020_2022':evaluate('2020-01-01','2022-12-31'),'2023_plus':evaluate('2023-01-01',END)}
pos=sum(v['excess_cagr_pp']>0 for v in blocks.values())
w=windows['2012_plus']; support=(all(v['excess_cagr_pp']>0 for v in windows.values()) and pos>=3 and w['candidate']['max_drawdown']>=w['matched']['max_drawdown']-.05)
out={'schema':'research.uup_efa_dollar_regime_replication_r2.v1','replication':'independent Stooq data-source implementation','frozen_mechanism':'prior completed calendar-month UUP return >= +2% => SPY next month; otherwise EFA','cost_one_way':COST,'matched_control':'static SPY/EFA mixture matched to realized SPY participation','windows':windows,'blocks':blocks,'positive_blocks':pos,'decision':'UUP_EFA_DOLLAR_REGIME_REPLICATION_SUPPORTED' if support else 'UUP_EFA_DOLLAR_REGIME_REPLICATION_REJECTED','protected_boundary':'no UUP threshold/proxy/regional ETF/horizon/cost/date/control/block rescue'}
print('RESULT_JSON='+json.dumps(out,sort_keys=True))

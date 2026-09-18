from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

T=['GDX','GLD','USO']; COST=.0025; N=1000; SEED=20260918
OUT=Path('research/artifacts/mr_gold_miner_volatility_information_b6_20260918.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
raw=yf.download(T,start='2011-01-01',end='2026-09-18',auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
px=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
m=px[T].resample('ME').last().dropna(); r=m.pct_change(fill_method=None)
parent=(m.USO.pct_change(6,fill_method=None)<0).shift(1)
gv=r.GDX.rolling(3).std(); vm=gv.rolling(36,min_periods=24).median(); b5=((m.USO.pct_change(6,fill_method=None)<0)&(gv<=vm)).shift(1)

def ev(sig,a='2015-01-01',b=None):
 q=pd.DataFrame({'gdx':r.GDX,'gld':r.GLD,'sig':sig}).loc[a:b].dropna(); w=q.sig.astype(float); sw=w.diff().abs().fillna(w.abs()); x=w*q.gdx+(1-w)*q.gld-COST*sw; p=float(w.mean()); ctl=p*q.gdx+(1-p)*q.gld; ctl.iloc[0]-=COST
 def met(z):
  eq=(1+z).cumprod(); return {'cagr_pct':100*float(eq.iloc[-1]**(12/len(z))-1),'max_drawdown_pct':100*float((eq/eq.cummax()-1).min())}
 cm,bm=met(x),met(ctl); return {'months':len(q),'gdx_participation':p,'switches':float(sw.sum()),'candidate':cm,'matched_control':bm,'excess_cagr_pp':cm['cagr_pct']-bm['cagr_pct']}

W={'2015+':('2015-01-01',None),'2017+':('2017-01-01',None),'2020+':('2020-01-01',None),'2022+':('2022-01-01',None)}
actual={k:ev(b5,*v) for k,v in W.items()}; par={k:ev(parent,*v) for k,v in W.items()}
# Placebo gates use no market information: independently retain the same number of parent-GDX months as B5 in each full history draw.
base=pd.DataFrame({'parent':parent,'b5':b5}).dropna(); eligible=base.index[base.parent.astype(bool)]; keep=int(base.b5.astype(bool).sum()); rng=np.random.default_rng(SEED)
place=[]
for _ in range(N):
 chosen=set(rng.choice(np.array(eligible,dtype='datetime64[ns]'),size=keep,replace=False)); sig=pd.Series(False,index=base.index); sig.loc[[x for x in eligible if np.datetime64(x) in chosen]]=True; sig=sig.reindex(m.index).fillna(False)
 place.append(ev(sig)['excess_cagr_pp'])
arr=np.array(place); a=actual['2015+']['excess_cagr_pp']; pct=float((arr<a).mean()); p95=float(np.quantile(arr,.95)); delta=a-p95
wins=sum(actual[k]['excess_cagr_pp']>par[k]['excess_cagr_pp'] for k in W)
passed=pct>=.95 and delta>0 and wins>=3 and actual['2022+']['excess_cagr_pp']>=par['2022+']['excess_cagr_pp']
out={'schema':'research.mr_gold_miner_volatility_information_b6_20260918.v1','question':'Does B5 volatility state add information beyond merely throttling parent GDX participation?','frozen':{'b5':'parent 6m USO<0 AND lagged 3m GDX vol <= trailing 36m median','placebo':'1000 seed-fixed market-information-free subsets retaining exactly B5 count of parent-GDX months','seed':SEED,'cost_bps_one_way':25,'control':'each signal static GDX/GLD mixture at identical realized GDX participation','promotion':'B5 long excess > placebo 95th percentile; empirical percentile >=95%; >=3/4 parent window wins; 2022+ excess non-worse','no_rescue':'no parameter/date/cost/control/seed changes'},'actual':actual,'parent':par,'placebo':{'n':N,'mean_excess_cagr_pp':float(arr.mean()),'p95_excess_cagr_pp':p95,'b5_percentile':pct,'b5_minus_p95_pp':delta},'window_wins_vs_parent':wins,'decision':'VOLATILITY_INFORMATION_SUPPORTED' if passed else 'PARTICIPATION_THROTTLE_EXPLANATION_SURVIVES','boundaries':{'protected_p01_holdout_read':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps({'decision':out['decision'],'b5_long_excess':round(a,3),'placebo_p95':round(p95,3),'b5_percentile':round(pct,4),'delta_p95':round(delta,3),'window_wins':wins,'b5_2022':round(actual['2022+']['excess_cagr_pp'],3),'parent_2022':round(par['2022+']['excess_cagr_pp'],3)},sort_keys=True))
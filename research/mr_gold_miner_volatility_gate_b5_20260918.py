from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import yfinance as yf
T=['GDX','GLD','USO']; COST=.0025
OUT=Path('research/artifacts/mr_gold_miner_volatility_gate_b5_20260918.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
raw=yf.download(T,start='2011-01-01',end='2026-09-18',auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
px=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
m=px[T].resample('ME').last().dropna(); r=m.pct_change(fill_method=None)
parent=(m.USO.pct_change(6,fill_method=None)<0).shift(1)
# Orthogonal risk-state test: only take the parent GDX state when prior completed-month
# 3m GDX realized volatility is below its trailing 36m median. All information is lagged.
gdx_vol=r.GDX.rolling(3).std(); vol_med=gdx_vol.rolling(36,min_periods=24).median()
chall=((m.USO.pct_change(6,fill_method=None)<0)&(gdx_vol<=vol_med)).shift(1)
def ev(sig,a,b=None):
 q=pd.DataFrame({'gdx':r.GDX,'gld':r.GLD,'sig':sig}).loc[a:b].dropna()
 if len(q)<18:return {'months':len(q)}
 w=q.sig.astype(float); sw=w.diff().abs().fillna(w.abs()); cand=w*q.gdx+(1-w)*q.gld-COST*sw; p=float(w.mean()); ctl=p*q.gdx+(1-p)*q.gld; ctl.iloc[0]-=COST
 def met(x):
  eq=(1+x).cumprod(); return {'cagr_pct':100*float(eq.iloc[-1]**(12/len(x))-1),'max_drawdown_pct':100*float((eq/eq.cummax()-1).min())}
 cm,bm=met(cand),met(ctl); return {'months':len(q),'gdx_participation':p,'switches':float(sw.sum()),'candidate':cm,'matched_control':bm,'excess_cagr_pp':cm['cagr_pct']-bm['cagr_pct']}
W={'2015+':('2015-01-01',None),'2017+':('2017-01-01',None),'2020+':('2020-01-01',None),'2022+':('2022-01-01',None)}
B={'2015_2017':('2015-01-01','2017-12-31'),'2018_2020':('2018-01-01','2020-12-31'),'2021_2023':('2021-01-01','2023-12-31'),'2024_plus':('2024-01-01',None)}
R={n:{'windows':{k:ev(s,*v) for k,v in W.items()},'blocks':{k:ev(s,*v) for k,v in B.items()}} for n,s in {'raw_oil_parent':parent,'low_vol_confirmation':chall}.items()}; p,c=R['raw_oil_parent'],R['low_vol_confirmation']
ld=c['windows']['2015+']['excess_cagr_pp']-p['windows']['2015+']['excess_cagr_pp']; ww=sum(c['windows'][k]['excess_cagr_pp']>p['windows'][k]['excess_cagr_pp'] for k in W); bw=sum(c['blocks'][k]['excess_cagr_pp']>p['blocks'][k]['excess_cagr_pp'] for k in B); dd=c['windows']['2015+']['candidate']['max_drawdown_pct']-p['windows']['2015+']['candidate']['max_drawdown_pct']
passed=ld>=1 and ww>=3 and bw>=3 and c['windows']['2022+']['excess_cagr_pp']>=p['windows']['2022+']['excess_cagr_pp'] and dd>=-5
out={'schema':'research.mr_gold_miner_volatility_gate_b5_20260918.v1','question':'Does a lagged low-volatility state improve the surviving raw-oil GDX/GLD timer?','non_alpha_explanation':'The volatility gate merely lowers GDX participation and does not add stable predictive information.','frozen':{'parent':'prior completed-month 6m USO change < 0','challenger':'parent AND prior completed-month 3m GDX realized vol <= trailing 36m median','cost_bps_one_way':25,'control':'each signal own static GDX/GLD mixture at identical realized GDX participation','windows':W,'blocks':B,'promotion':'incremental long excess >=1pp; >=3/4 window wins; >=3/4 block wins; 2022+ excess non-worse; drawdown deterioration <=5pp','no_rescue':'no lookback/threshold/ticker/date/cost/control changes'},'results':R,'incremental_long_excess_pp':ld,'challenger_wins_windows':ww,'challenger_wins_blocks':bw,'long_candidate_drawdown_delta_pp':dd,'decision':'FRONTIER_IMPROVED' if passed else 'HOLD_GENERIC_OIL_SURVIVOR','boundaries':{'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps({'decision':out['decision'],'long_delta':round(ld,3),'window_wins':ww,'block_wins':bw,'challenger_2022':round(c['windows']['2022+']['excess_cagr_pp'],3),'parent_2022':round(p['windows']['2022+']['excess_cagr_pp'],3),'dd_delta':round(dd,3),'candidate_long':c['windows']['2015+'],'parent_long':p['windows']['2015+']},sort_keys=True))
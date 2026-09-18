from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import yfinance as yf
T=['GDX','GLD','USO','SPY']; COST=.0025
OUT=Path('research/artifacts/mr_gold_miner_riskon_confirmation_b4_20260918.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
raw=yf.download(T,start='2011-01-01',end='2026-09-18',auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
px=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
m=px[T].resample('ME').last().dropna(); r=m.pct_change(fill_method=None)
parent=(m.USO.pct_change(6,fill_method=None)<0).shift(1)
chall=((m.USO.pct_change(6,fill_method=None)<0)&(m.SPY.pct_change(6,fill_method=None)>=0)).shift(1)
def ev(sig,a,b=None):
 q=pd.DataFrame({'gdx':r.GDX,'gld':r.GLD,'sig':sig}).loc[a:b].dropna();
 if len(q)<18:return {'months':len(q)}
 w=q.sig.astype(float); sw=w.diff().abs().fillna(w.abs()); cand=w*q.gdx+(1-w)*q.gld-COST*sw; p=float(w.mean()); ctl=p*q.gdx+(1-p)*q.gld; ctl.iloc[0]-=COST
 def met(x):
  eq=(1+x).cumprod(); return {'cagr_pct':100*float(eq.iloc[-1]**(12/len(x))-1),'max_drawdown_pct':100*float((eq/eq.cummax()-1).min())}
 cm,bm=met(cand),met(ctl); return {'months':len(q),'gdx_participation':p,'switches':float(sw.sum()),'candidate':cm,'matched_control':bm,'excess_cagr_pp':cm['cagr_pct']-bm['cagr_pct']}
W={'2013+':('2013-01-01',None),'2016+':('2016-01-01',None),'2020+':('2020-01-01',None),'2022+':('2022-01-01',None)}
B={'2013_2015':('2013-01-01','2015-12-31'),'2016_2018':('2016-01-01','2018-12-31'),'2019_2021':('2019-01-01','2021-12-31'),'2022_2024':('2022-01-01','2024-12-31'),'2025_plus':('2025-01-01',None)}
R={n:{'windows':{k:ev(s,*v) for k,v in W.items()},'blocks':{k:ev(s,*v) for k,v in B.items()}} for n,s in {'raw_oil_parent':parent,'riskon_confirmation':chall}.items()}; p,c=R['raw_oil_parent'],R['riskon_confirmation']
ld=c['windows']['2013+']['excess_cagr_pp']-p['windows']['2013+']['excess_cagr_pp']; ww=sum(c['windows'][k]['excess_cagr_pp']>p['windows'][k]['excess_cagr_pp'] for k in W); bw=sum(c['blocks'][k]['excess_cagr_pp']>p['blocks'][k]['excess_cagr_pp'] for k in B); dd=c['windows']['2013+']['candidate']['max_drawdown_pct']-p['windows']['2013+']['candidate']['max_drawdown_pct']
passed=ld>=1 and ww>=3 and bw>=3 and c['windows']['2022+']['excess_cagr_pp']>=p['windows']['2022+']['excess_cagr_pp'] and dd>=-5
out={'schema':'research.mr_gold_miner_riskon_confirmation_b4_20260918.v1','question':'Does requiring positive broad-equity six-month trend improve the surviving raw-oil GDX/GLD timer?','non_alpha_explanation':'The filter merely reduces GDX participation and does not add stable predictive information.','frozen':{'parent':'prior completed-month 6m USO change < 0','challenger':'parent AND prior completed-month 6m SPY change >= 0','cost_bps_one_way':25,'control':'each signal own static GDX/GLD mixture at identical realized GDX participation','windows':W,'blocks':B,'no_rescue':'no lookback/threshold/ticker/date/cost/control changes'},'results':R,'incremental_long_excess_pp':ld,'challenger_wins_windows':ww,'challenger_wins_blocks':bw,'long_candidate_drawdown_delta_pp':dd,'decision':'FRONTIER_IMPROVED' if passed else 'HOLD_GENERIC_OIL_SURVIVOR','boundaries':{'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps({'decision':out['decision'],'long_delta':round(ld,3),'window_wins':ww,'block_wins':bw,'challenger_2022':round(c['windows']['2022+']['excess_cagr_pp'],3),'parent_2022':round(p['windows']['2022+']['excess_cagr_pp'],3),'dd_delta':round(dd,3),'candidate_2013':c['windows']['2013+'],'parent_2013':p['windows']['2013+']},sort_keys=True))
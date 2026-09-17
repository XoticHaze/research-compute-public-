from __future__ import annotations
import json
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
T=['EFAV','EFA','ACWI']; COST=0.0025
x=yf.download(T,start='2012-01-01',auto_adjust=True,progress=False,threads=False)
if x.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=x['Close'] if isinstance(x.columns,pd.MultiIndex) else x
r=c[T].resample('ME').last().dropna().pct_change().dropna()
def charge(s):
 y=s.copy()
 if len(y): y.iloc[0]-=COST; y.iloc[-1]-=COST
 return y
def cagr(s): return float((1+s).prod()**(12/len(s))-1) if len(s) else float('nan')
def sh(s):
 sd=s.std(ddof=1); return float(np.sqrt(12)*s.mean()/sd) if len(s)>1 and sd>0 else float('nan')
def dd(s):
 w=(1+s).cumprod(); return float((w/w.cummax()-1).min()) if len(s) else float('nan')
def ev(a,b=None):
 q=charge(r.EFAV.loc[a:b]); ctl=charge(r.EFA.reindex(q.index)); opp=charge(r.ACWI.reindex(q.index))
 return {'months':int(len(q)),'efav_cagr':cagr(q),'efa_cagr':cagr(ctl),'acwi_cagr':cagr(opp),'matched_excess_pp':100*(cagr(q)-cagr(ctl)),'acwi_excess_pp':100*(cagr(q)-cagr(opp)),'efav_sharpe':sh(q),'efa_sharpe':sh(ctl),'efav_max_drawdown':dd(q),'efa_max_drawdown':dd(ctl)}
windows={k:ev(v) for k,v in {'2013+':'2013-01-01','2016+':'2016-01-01','2020+':'2020-01-01'}.items()}
folds=[]
for a,b in [('2013-01-01','2015-12-31'),('2016-01-01','2018-12-31'),('2019-01-01','2021-12-31'),('2022-01-01','2023-12-31'),('2024-01-01',None)]:
 z=ev(a,b); z['positive_matched_excess']=z['matched_excess_pp']>0; folds.append(z)
pos=sum(z['positive_matched_excess'] for z in folds)
passed=all(z['matched_excess_pp']>0 for z in windows.values()) and pos>=4
risk_benefit=all(z['efav_max_drawdown']>z['efa_max_drawdown'] for z in windows.values())
out={'schema':'research.p411_international_minvol.v1','workload_id':'P411_INTERNATIONAL_MINVOL_R1','parent':'INTERNATIONAL_MINIMUM_VOLATILITY','claim':'Prospectively fixed developed-ex-US minimum-volatility exposure via EFAV can deliver durable after-cost excess return over EFA, with ACWI opportunity-cost context, without timing or parameter search.','cost_bps_each_endpoint':25,'windows':windows,'folds':folds,'positive_folds':pos,'risk_benefit_all_windows':risk_benefit,'decision_rule':'ALPHA_SUPPORTED only if EFAV has positive matched excess in fixed 2013+/2016+/2020+ windows and >=4/5 chronology folds. Drawdown improvement is preserved separately and cannot rescue failed alpha.','decision':'INTERNATIONAL_MINVOL_ALPHA_SUPPORTED' if passed else 'INTERNATIONAL_MINVOL_ALPHA_NOT_SUPPORTED','scientific_consequence':('International minimum volatility earns initial alpha survivor status requiring orthogonal validation.' if passed else ('Reject standalone alpha claim while preserving consistent drawdown/risk-shaping evidence; do not parameter/product rescue.' if risk_benefit else 'Reject this exact international minimum-volatility alpha formulation; preserve only passing dimensions and do not parameter/product rescue.')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p411_international_minvol_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'positive_folds':pos,'risk_benefit_all_windows':risk_benefit,'windows':{k:round(v['matched_excess_pp'],3) for k,v in windows.items()}},sort_keys=True))

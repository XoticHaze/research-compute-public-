from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
OUT=Path('research/artifacts/p507_shareholder_yield_alpha_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
T=['PKW','SYLD','VTV','SPY']; COST=.0010
WINDOWS={'2015_plus':'2015-01-02','2018_plus':'2018-01-02','2020_plus':'2020-01-02'}
BLOCKS={'2015_2017':('2015-01-02','2017-12-29'),'2018_2020':('2018-01-02','2020-12-31'),'2021_2023':('2021-01-04','2023-12-29'),'2024_plus':('2024-01-02',None)}
raw=yf.download(T,start='2014-12-01',end='2026-09-11',auto_adjust=True,progress=False,threads=False)
c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
c=c[T].dropna(how='all')

def ret_stats(t,start,end=None):
 s=c[t].loc[c.index>=pd.Timestamp(start)]
 if end: s=s.loc[s.index<=pd.Timestamp(end)]
 s=s.dropna()
 if len(s)<2:return None
 years=(s.index[-1]-s.index[0]).days/365.2425
 r=s.pct_change(fill_method=None).dropna(); ann=float((s.iloc[-1]/s.iloc[0])**(1/years)-1-COST/years)
 vol=float(r.std(ddof=1)*math.sqrt(252)); sh=float(r.mean()*252/vol) if vol>0 else None
 w=(1+r).cumprod(); dd=float((w/w.cummax()-1).min())
 return {'cagr_after_cost':ann,'sharpe_rf0':sh,'max_drawdown':dd,'days':int(len(r))}

def alpha(candidate,start,end=None):
 px=c[[candidate,'VTV','SPY']].loc[c.index>=pd.Timestamp(start)]
 if end:px=px.loc[px.index<=pd.Timestamp(end)]
 rr=px.pct_change(fill_method=None).dropna()
 if len(rr)<60:return None
 y=rr[candidate].to_numpy(); X=np.column_stack([np.ones(len(rr)),rr[['VTV','SPY']].to_numpy()]); b=np.linalg.lstsq(X,y,rcond=None)[0]; resid=y-X@b
 n=len(y);k=3;s2=float(resid@resid/max(1,n-k));cov=s2*np.linalg.inv(X.T@X);se=float(np.sqrt(cov[0,0]));ann=float(b[0]*252-COST/max(1,(px.index[-1]-px.index[0]).days/365.2425))
 return {'annualized_alpha_after_cost':ann,'alpha_t':float(b[0]/se) if se>0 else None,'beta_vtv':float(b[1]),'beta_spy':float(b[2]),'days':int(n)}

def row(start,end=None):
 out={}
 for t in ['PKW','SYLD']:
  s=ret_stats(t,start,end); v=ret_stats('VTV',start,end); sp=ret_stats('SPY',start,end); a=alpha(t,start,end)
  out[t]={**s,'vs_vtv_cagr':s['cagr_after_cost']-v['cagr_after_cost'],'vs_spy_cagr':s['cagr_after_cost']-sp['cagr_after_cost'],'two_control_alpha':a}
 return out
wins={k:row(v) for k,v in WINDOWS.items()}; blocks={k:row(a,b) for k,(a,b) in BLOCKS.items()}
summary={}
for t in ['PKW','SYLD']:
 summary[t]={'positive_vtv_windows':sum(wins[k][t]['vs_vtv_cagr']>0 for k in wins),'positive_spy_windows':sum(wins[k][t]['vs_spy_cagr']>0 for k in wins),'positive_alpha_windows':sum(wins[k][t]['two_control_alpha']['annualized_alpha_after_cost']>0 for k in wins),'positive_alpha_blocks':sum(blocks[k][t]['two_control_alpha']['annualized_alpha_after_cost']>0 for k in blocks)}
supported=all(summary[t]['positive_vtv_windows']==3 and summary[t]['positive_alpha_windows']==3 and summary[t]['positive_alpha_blocks']>=3 for t in ['PKW','SYLD'])
decision='SHAREHOLDER_YIELD_ALPHA_SUPPORTED' if supported else 'SHAREHOLDER_YIELD_ALPHA_NOT_SUPPORTED'
out={'schema':'research.p507_shareholder_yield_alpha_r1.v1','workload_id':'P507_SHAREHOLDER_YIELD_ALPHA_R1','parent':'SHAREHOLDER_DISTRIBUTION_FACTOR','claim':'Two-implementation shareholder-distribution test: PKW buyback exposure and SYLD shareholder-yield exposure must retain after-cost excess versus value control VTV and positive residual alpha after jointly controlling VTV and SPY. Fixed windows/blocks and 10bp endpoint friction; no wrapper/date/control/cost rescue.','contract':{'implementations':['PKW','SYLD'],'value_control':'VTV','broad_control':'SPY','endpoint_cost_bps':10,'windows':WINDOWS,'chronology_blocks':BLOCKS,'support_rule':'both implementations positive versus VTV in 3/3 windows, positive VTV+SPY residual alpha in 3/3 windows, and positive residual alpha in >=3/4 chronology blocks','no_product_date_control_cost_or_threshold_search':True},'windows':wins,'blocks':blocks,'summary':summary,'decision':decision,'scientific_consequence':'Support only if both independent implementations clear the frozen value-attribution and chronology gate; otherwise reject durable shareholder-distribution alpha at the wrapper-family level without product substitution rescue.','boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':decision,'summary':summary,'windows':{k:{t:{'vs_vtv_pp':round(v[t]['vs_vtv_cagr']*100,3),'vs_spy_pp':round(v[t]['vs_spy_cagr']*100,3),'alpha_pp':round(v[t]['two_control_alpha']['annualized_alpha_after_cost']*100,3),'alpha_t':round(v[t]['two_control_alpha']['alpha_t'],2)} for t in ['PKW','SYLD']} for k,v in wins.items()},'blocks':{k:{t:round(v[t]['two_control_alpha']['annualized_alpha_after_cost']*100,3) for t in ['PKW','SYLD']} for k,v in blocks.items()}},sort_keys=True))

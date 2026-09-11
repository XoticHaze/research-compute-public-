from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
OUT=Path('research/artifacts/p508_equity_momentum_residual_r1.json');OUT.parent.mkdir(parents=True,exist_ok=True)
T=['MTUM','PDP','SPY','QQQ'];COST=.0010
WINDOWS={'2015_plus':'2015-01-02','2018_plus':'2018-01-02','2020_plus':'2020-01-02'}
BLOCKS={'2015_2017':('2015-01-02','2017-12-29'),'2018_2020':('2018-01-02','2020-12-31'),'2021_2023':('2021-01-04','2023-12-29'),'2024_plus':('2024-01-02',None)}
raw=yf.download(T,start='2014-12-01',end='2026-09-11',auto_adjust=True,progress=False,threads=False)
c=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[T].dropna(how='all')
def cagr(t,start,end=None):
 s=c[t].loc[c.index>=pd.Timestamp(start)];
 if end:s=s.loc[s.index<=pd.Timestamp(end)]
 s=s.dropna(); years=(s.index[-1]-s.index[0]).days/365.2425
 return float((s.iloc[-1]/s.iloc[0])**(1/years)-1-COST/years)
def fit(t,start,end=None):
 px=c[[t,'SPY','QQQ']].loc[c.index>=pd.Timestamp(start)]
 if end:px=px.loc[px.index<=pd.Timestamp(end)]
 r=px.pct_change(fill_method=None).dropna(); y=r[t].to_numpy();X=np.column_stack([np.ones(len(r)),r[['SPY','QQQ']].to_numpy()]);b=np.linalg.lstsq(X,y,rcond=None)[0];res=y-X@b;n=len(y);s2=float(res@res/max(1,n-3));se=float(np.sqrt(s2*np.linalg.inv(X.T@X)[0,0]));years=max(1,(px.index[-1]-px.index[0]).days/365.2425)
 return {'days':n,'annualized_alpha_after_cost':float(b[0]*252-COST/years),'alpha_t':float(b[0]/se) if se else None,'beta_spy':float(b[1]),'beta_qqq':float(b[2])}
def row(start,end=None):
 out={}
 for t in ['MTUM','PDP']:
  a=fit(t,start,end);out[t]={'cagr_after_cost':cagr(t,start,end),'vs_spy_cagr':cagr(t,start,end)-cagr('SPY',start,end),'vs_qqq_cagr':cagr(t,start,end)-cagr('QQQ',start,end),'residual':a}
 return out
w={k:row(v) for k,v in WINDOWS.items()};b={k:row(a,z) for k,(a,z) in BLOCKS.items()};summary={}
for t in ['MTUM','PDP']:
 summary[t]={'positive_alpha_windows':sum(w[k][t]['residual']['annualized_alpha_after_cost']>0 for k in w),'positive_alpha_blocks':sum(b[k][t]['residual']['annualized_alpha_after_cost']>0 for k in b),'positive_spy_windows':sum(w[k][t]['vs_spy_cagr']>0 for k in w)}
supported=all(summary[t]['positive_alpha_windows']==3 and summary[t]['positive_alpha_blocks']>=3 and summary[t]['positive_spy_windows']>=2 for t in ['MTUM','PDP'])
decision='EQUITY_MOMENTUM_RESIDUAL_SUPPORTED' if supported else 'EQUITY_MOMENTUM_RESIDUAL_NOT_SUPPORTED'
out={'schema':'research.p508_equity_momentum_residual_r1.v1','workload_id':'P508_EQUITY_MOMENTUM_RESIDUAL_R1','parent':'EQUITY_STOCK_LEVEL_MOMENTUM_FACTOR','claim':'Two-implementation stock-level momentum test using MTUM and PDP. Require after-cost residual alpha after jointly controlling SPY and QQQ across fixed windows and chronology blocks so broad equity or growth/technology loading cannot masquerade as momentum alpha. This is distinct from P266 industry cross-sectional selection.','contract':{'implementations':['MTUM','PDP'],'controls':['SPY','QQQ'],'endpoint_cost_bps':10,'windows':WINDOWS,'blocks':BLOCKS,'support_rule':'both implementations positive residual alpha in 3/3 fixed windows and >=3/4 chronology blocks and positive vs SPY CAGR in >=2/3 windows','no_product_date_control_cost_or_threshold_search':True},'windows':w,'blocks':b,'summary':summary,'decision':decision,'scientific_consequence':'Support only if both implementations clear the frozen residual and chronology gates; otherwise reject durable wrapper-level stock-momentum residual without changing products, controls, or dates.','boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False));print(json.dumps({'decision':decision,'summary':summary,'windows':{k:{t:{'vs_spy_pp':round(v[t]['vs_spy_cagr']*100,3),'vs_qqq_pp':round(v[t]['vs_qqq_cagr']*100,3),'alpha_pp':round(v[t]['residual']['annualized_alpha_after_cost']*100,3),'t':round(v[t]['residual']['alpha_t'],2)} for t in ['MTUM','PDP']} for k,v in w.items()},'blocks':{k:{t:round(v[t]['residual']['annualized_alpha_after_cost']*100,3) for t in ['MTUM','PDP']} for k,v in b.items()}},sort_keys=True))

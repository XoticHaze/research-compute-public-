from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
OUT=Path('research/artifacts/p510_free_cash_flow_yield_r1.json');OUT.parent.mkdir(parents=True,exist_ok=True)
T=['COWZ','CALF','IWB','VTV','IJR','IJS','SPY'];COST=.0010
WINDOWS={'2018_plus':'2018-01-02','2020_plus':'2020-01-02','2022_plus':'2022-01-03'}
BLOCKS={'2018_2020':('2018-01-02','2020-12-31'),'2021_2023':('2021-01-04','2023-12-29'),'2024_plus':('2024-01-02',None)}
raw=yf.download(T,start='2017-01-01',end='2026-09-11',auto_adjust=True,progress=False,threads=False)
c=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[T].dropna(how='all')
SPEC={'COWZ':['IWB','VTV'],'CALF':['IJR','IJS']}
def cagr(t,start,end=None):
 s=c[t].loc[c.index>=pd.Timestamp(start)];
 if end:s=s.loc[s.index<=pd.Timestamp(end)]
 s=s.dropna(); years=(s.index[-1]-s.index[0]).days/365.2425
 return float((s.iloc[-1]/s.iloc[0])**(1/years)-1-COST/years)
def fit(t,controls,start,end=None):
 px=c[[t,*controls]].loc[c.index>=pd.Timestamp(start)]
 if end:px=px.loc[px.index<=pd.Timestamp(end)]
 r=px.pct_change(fill_method=None).dropna();y=r[t].to_numpy();X=np.column_stack([np.ones(len(r)),r[controls].to_numpy()]);b=np.linalg.lstsq(X,y,rcond=None)[0];res=y-X@b;n=len(y);s2=float(res@res/max(1,n-len(b)));se=float(np.sqrt(s2*np.linalg.inv(X.T@X)[0,0]));years=max(1,(px.index[-1]-px.index[0]).days/365.2425)
 return {'days':n,'annualized_alpha_after_cost':float(b[0]*252-COST/years),'alpha_t':float(b[0]/se) if se else None,'betas':{controls[i]:float(b[i+1]) for i in range(len(controls))}}
def row(start,end=None):
 out={}
 for t,controls in SPEC.items():
  a=fit(t,controls,start,end);tc=cagr(t,start,end);out[t]={'cagr_after_cost':tc,'vs_primary_control_cagr':tc-cagr(controls[0],start,end),'vs_value_control_cagr':tc-cagr(controls[1],start,end),'residual':a}
 return out
w={k:row(v) for k,v in WINDOWS.items()};b={k:row(a,z) for k,(a,z) in BLOCKS.items()};summary={}
for t in SPEC:
 summary[t]={'positive_primary_windows':sum(w[k][t]['vs_primary_control_cagr']>0 for k in w),'positive_residual_windows':sum(w[k][t]['residual']['annualized_alpha_after_cost']>0 for k in w),'positive_residual_blocks':sum(b[k][t]['residual']['annualized_alpha_after_cost']>0 for k in b)}
supported=all(summary[t]['positive_primary_windows']==3 and summary[t]['positive_residual_windows']==3 and summary[t]['positive_residual_blocks']>=2 for t in SPEC)
decision='FREE_CASH_FLOW_YIELD_ALPHA_SUPPORTED' if supported else 'FREE_CASH_FLOW_YIELD_ALPHA_NOT_SUPPORTED'
out={'schema':'research.p510_free_cash_flow_yield_r1.v1','workload_id':'P510_FREE_CASH_FLOW_YIELD_R1','parent':'FREE_CASH_FLOW_YIELD_FACTOR','claim':'Independent capitalization implementations of free-cash-flow-yield selection: COWZ large/mid versus IWB+VTV controls and CALF small-cap versus IJR+IJS controls. Require after-cost residual alpha and matched size-control excess across fixed windows and chronology. No product/date/control/cost rescue.','contract':{'implementations':SPEC,'endpoint_cost_bps':10,'windows':WINDOWS,'blocks':BLOCKS,'support_rule':'both implementations positive versus primary size control in 3/3 windows, positive residual alpha in 3/3 windows and >=2/3 chronology blocks','no_product_date_control_cost_or_threshold_search':True},'windows':w,'blocks':b,'summary':summary,'decision':decision,'scientific_consequence':'Support a cross-cap free-cash-flow-yield family only if both independently matched implementations pass. Otherwise reject broad family durability and do not rescue by substituting wrappers or changing controls/windows.','boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False));print(json.dumps({'decision':decision,'summary':summary,'windows':{k:{t:{'vs_primary_pp':round(v[t]['vs_primary_control_cagr']*100,3),'vs_value_pp':round(v[t]['vs_value_control_cagr']*100,3),'alpha_pp':round(v[t]['residual']['annualized_alpha_after_cost']*100,3),'t':round(v[t]['residual']['alpha_t'],2)} for t in SPEC} for k,v in w.items()},'blocks':{k:{t:round(v[t]['residual']['annualized_alpha_after_cost']*100,3) for t in SPEC} for k,v in b.items()}},sort_keys=True))

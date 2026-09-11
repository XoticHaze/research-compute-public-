from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

OUT=Path('research/artifacts/p514_garp_dual_implementation_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
T=['SPGP','QGRO','SPY','VUG','VTV']; COST=.0010
WINDOWS={'2019_plus':'2019-01-02','2021_plus':'2021-01-04','2023_plus':'2023-01-03'}
BLOCKS={'2019_2021':('2019-01-02','2021-12-31'),'2022_2023':('2022-01-03','2023-12-29'),'2024_plus':('2024-01-02',None)}
CONTROLS=['SPY','VUG','VTV']
raw=yf.download(T,start='2018-01-01',end='2026-09-11',auto_adjust=True,progress=False,threads=False)
c=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[T].dropna(how='all')

def cagr(t,start,end=None):
    s=c[t].loc[c.index>=pd.Timestamp(start)]
    if end: s=s.loc[s.index<=pd.Timestamp(end)]
    s=s.dropna(); years=(s.index[-1]-s.index[0]).days/365.2425
    return float((s.iloc[-1]/s.iloc[0])**(1/years)-1-COST/years)

def fit(t,start,end=None):
    px=c[[t,*CONTROLS]].loc[c.index>=pd.Timestamp(start)]
    if end: px=px.loc[px.index<=pd.Timestamp(end)]
    r=px.pct_change(fill_method=None).dropna(); y=r[t].to_numpy(); X=np.column_stack([np.ones(len(r)),r[CONTROLS].to_numpy()])
    b=np.linalg.lstsq(X,y,rcond=None)[0]; res=y-X@b; n=len(y); dof=max(1,n-len(b)); s2=float(res@res/dof)
    inv=np.linalg.pinv(X.T@X); se=float(np.sqrt(max(0,s2*inv[0,0]))); years=max(1,(px.index[-1]-px.index[0]).days/365.2425)
    return {'days':n,'annualized_alpha_after_cost':float(b[0]*252-COST/years),'alpha_t':float(b[0]/se) if se else None,'betas':{CONTROLS[i]:float(b[i+1]) for i in range(len(CONTROLS))}}

def row(start,end=None):
    out={}
    for t in ['SPGP','QGRO']:
        tc=cagr(t,start,end); out[t]={'cagr_after_cost':tc,'vs_spy_cagr':tc-cagr('SPY',start,end),'residual':fit(t,start,end)}
    return out

w={k:row(v) for k,v in WINDOWS.items()}; b={k:row(a,z) for k,(a,z) in BLOCKS.items()}; summary={}
for t in ['SPGP','QGRO']:
    summary[t]={'positive_spy_windows':sum(w[k][t]['vs_spy_cagr']>0 for k in w),'positive_residual_windows':sum(w[k][t]['residual']['annualized_alpha_after_cost']>0 for k in w),'positive_residual_blocks':sum(b[k][t]['residual']['annualized_alpha_after_cost']>0 for k in b)}
supported=all(summary[t]['positive_spy_windows']==3 and summary[t]['positive_residual_windows']==3 and summary[t]['positive_residual_blocks']>=2 for t in summary)
decision='GARP_ALPHA_SUPPORTED' if supported else 'GARP_ALPHA_NOT_SUPPORTED'
out={'schema':'research.p514_garp_dual_implementation_r1.v1','workload_id':'P514_GARP_DUAL_IMPLEMENTATION_R1','parent':'GARP_FACTOR','claim':'Two prospectively fixed growth-at-reasonable-price implementations, SPGP and QGRO, must each show after-cost excess versus SPY and residual alpha after joint SPY+VUG+VTV controls across fixed windows and chronology.','contract':{'implementations':['SPGP','QGRO'],'controls':CONTROLS,'endpoint_cost_bps':10,'windows':WINDOWS,'blocks':BLOCKS,'support_rule':'both implementations positive vs SPY in 3/3 windows, positive residual alpha in 3/3 windows and >=2/3 chronology blocks','no_product_date_control_cost_threshold_or_weight_search':True},'windows':w,'blocks':b,'summary':summary,'decision':decision,'scientific_consequence':'Support GARP as an independent fund-model family only if both fixed implementations survive broad-market plus growth/value attribution. Otherwise reject broad GARP durability and do not rescue with alternate wrappers, dates, controls, or thresholds.','boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':decision,'summary':summary,'windows':{k:{t:{'vs_spy_pp':round(v[t]['vs_spy_cagr']*100,3),'alpha_pp':round(v[t]['residual']['annualized_alpha_after_cost']*100,3),'t':round(v[t]['residual']['alpha_t'],2)} for t in summary} for k,v in w.items()},'blocks':{k:{t:round(v[t]['residual']['annualized_alpha_after_cost']*100,3) for t in summary} for k,v in b.items()}},sort_keys=True))
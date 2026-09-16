from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

OUT=Path('research/artifacts/p516_dividend_quality_residual_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
T=['SCHD','SPY','VTV','QUAL']; COST=.0010
WINDOWS={'2013_plus':'2013-01-02','2018_plus':'2018-01-02','2022_plus':'2022-01-03'}
BLOCKS={'2013_2016':('2013-01-02','2016-12-30'),'2017_2020':('2017-01-03','2020-12-31'),'2021_2023':('2021-01-04','2023-12-29'),'2024_plus':('2024-01-02',None)}
CONTROLS=['SPY','VTV','QUAL']
raw=yf.download(T,start='2012-01-01',end='2026-09-11',auto_adjust=True,progress=False,threads=False)
c=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[T].dropna(how='all')

def cagr(t,start,end=None):
    s=c[t].loc[c.index>=pd.Timestamp(start)]
    if end: s=s.loc[s.index<=pd.Timestamp(end)]
    s=s.dropna(); years=(s.index[-1]-s.index[0]).days/365.2425
    return float((s.iloc[-1]/s.iloc[0])**(1/years)-1-COST/years)

def fit(start,end=None):
    px=c[['SCHD',*CONTROLS]].loc[c.index>=pd.Timestamp(start)]
    if end: px=px.loc[px.index<=pd.Timestamp(end)]
    r=px.pct_change(fill_method=None).dropna(); y=r['SCHD'].to_numpy(); X=np.column_stack([np.ones(len(r)),r[CONTROLS].to_numpy()])
    b=np.linalg.lstsq(X,y,rcond=None)[0]; res=y-X@b; n=len(y); dof=max(1,n-len(b)); s2=float(res@res/dof); inv=np.linalg.pinv(X.T@X); se=float(np.sqrt(max(0,s2*inv[0,0]))); years=max(1,(px.index[-1]-px.index[0]).days/365.2425)
    return {'days':n,'annualized_alpha_after_cost':float(b[0]*252-COST/years),'alpha_t':float(b[0]/se) if se else None,'betas':{CONTROLS[i]:float(b[i+1]) for i in range(len(CONTROLS))}}

def row(start,end=None):
    tc=cagr('SCHD',start,end)
    return {'cagr_after_cost':tc,'vs_spy_cagr':tc-cagr('SPY',start,end),'vs_vtv_cagr':tc-cagr('VTV',start,end),'vs_qual_cagr':tc-cagr('QUAL',start,end),'residual':fit(start,end)}

w={k:row(v) for k,v in WINDOWS.items()}; b={k:row(a,z) for k,(a,z) in BLOCKS.items()}
summary={'positive_spy_windows':sum(v['vs_spy_cagr']>0 for v in w.values()),'positive_residual_windows':sum(v['residual']['annualized_alpha_after_cost']>0 for v in w.values()),'positive_residual_blocks':sum(v['residual']['annualized_alpha_after_cost']>0 for v in b.values())}
supported=summary['positive_spy_windows']==3 and summary['positive_residual_windows']==3 and summary['positive_residual_blocks']>=3
decision='DIVIDEND_QUALITY_ALPHA_SUPPORTED' if supported else 'DIVIDEND_QUALITY_ALPHA_NOT_SUPPORTED'
out={'schema':'research.p516_dividend_quality_residual_r1.v1','workload_id':'P516_DIVIDEND_QUALITY_RESIDUAL_R1','parent':'DIVIDEND_QUALITY_FACTOR','claim':'SCHD quality-screened dividend selection must show after-cost SPY excess and residual alpha beyond joint SPY+VTV+QUAL exposures across fixed windows and chronology. This is distinct from prior dividend-growth tests.','contract':{'implementation':'SCHD','controls':CONTROLS,'endpoint_cost_bps':10,'windows':WINDOWS,'blocks':BLOCKS,'support_rule':'positive vs SPY and positive residual alpha in 3/3 fixed windows plus positive residual alpha in >=3/4 chronology blocks','no_wrapper_date_control_cost_threshold_or_weight_search':True},'windows':w,'blocks':b,'summary':summary,'decision':decision,'scientific_consequence':'Support dividend-quality selection only if the edge survives broad-market, value, and quality attribution. Otherwise reject independent dividend-quality alpha and do not rescue with alternate wrappers, dates, controls, or thresholds.','boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':decision,'summary':summary,'windows':{k:{'vs_spy_pp':round(v['vs_spy_cagr']*100,3),'vs_vtv_pp':round(v['vs_vtv_cagr']*100,3),'vs_qual_pp':round(v['vs_qual_cagr']*100,3),'alpha_pp':round(v['residual']['annualized_alpha_after_cost']*100,3),'t':round(v['residual']['alpha_t'],2)} for k,v in w.items()},'blocks':{k:round(v['residual']['annualized_alpha_after_cost']*100,3) for k,v in b.items()}},sort_keys=True))
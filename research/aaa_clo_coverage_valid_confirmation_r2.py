from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf

T=['JAAA','SGOV','SPMO','IJS','SPY','IJR','SRLN','HYG','SHY']
START='2015-01-01'; END='2026-09-10'; LB=24
CLO_EP=.0025; CORE_EP=.0010; LOAN_EP=.0010
BLOCKS={'2021_2022':('2021-01-01','2022-12-31'),'2023_2024':('2023-01-01','2024-12-31'),'2025_plus':('2025-01-01',None)}
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw

def mr(t):
    return c[t].dropna().resample('ME').last().pct_change().dropna().rename(t)
R={t:mr(t) for t in T}
p249=pd.concat([R['SPMO'],R['IJS']],axis=1).dropna().mean(axis=1).rename('p249')
p249_ctl=pd.concat([R['SPY'],R['IJR']],axis=1).dropna().mean(axis=1).rename('p249_ctl')
loan_src=pd.concat([R['SRLN'],R['HYG'],R['SHY']],axis=1).dropna()
bs=[]
for i in range(len(loan_src)):
    if i<LB: bs.append((np.nan,np.nan)); continue
    b=np.linalg.lstsq(loan_src[['HYG','SHY']].iloc[i-LB:i].values,loan_src['SRLN'].iloc[i-LB:i].values,rcond=None)[0]
    b=np.clip(b,0,1)
    if b.sum()>1: b=b/b.sum()
    bs.append(tuple(map(float,b)))
b=pd.DataFrame(bs,index=loan_src.index,columns=['hyg','shy']).shift(1)
loan_ctl=(b.hyg*loan_src.HYG+b.shy*loan_src.SHY).rename('loan_ctl')
x=pd.concat([p249,p249_ctl,R['SRLN'].rename('loan'),loan_ctl,R['JAAA'].rename('clo'),R['SGOV'].rename('clo_ctl')],axis=1).dropna().loc['2021-01-01':]
coverage={k:int(len(x.loc[a:b])) for k,(a,b) in BLOCKS.items()}
coverage_ok=all(v>=12 for v in coverage.values())
if not coverage_ok:
    out={'schema':'research.aaa_clo_coverage_valid_confirmation_r2','workload_id':'AAA_CLO_COVERAGE_VALID_CONFIRMATION_R2','coverage':coverage,'coverage_ok':False,'decision':'COVERAGE_GATE_FAILED','rule':'Performance must not be inspected unless every frozen chronology block has >=12 common observations. Dates/products/weights/controls/costs unchanged from R1.'}
    Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/aaa_clo_coverage_valid_confirmation_r2.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True)); raise SystemExit(0)

def endpoint(s,cost):
    y=s.copy(); y.iloc[0]-=cost; y.iloc[-1]-=cost; return y
for col,cost in [('p249',CORE_EP),('p249_ctl',CORE_EP),('loan',LOAN_EP),('loan_ctl',LOAN_EP),('clo',CLO_EP),('clo_ctl',CLO_EP)]: x[col]=endpoint(x[col],cost)
def stats(s):
    q=pd.Series(s,dtype=float).dropna(); n=len(q); w=(1+q).cumprod(); vol=q.std(ddof=1)*math.sqrt(12) if n>1 else np.nan
    return {'months':n,'cagr':float(w.iloc[-1]**(12/n)-1),'sharpe':float(q.mean()*12/vol) if np.isfinite(vol) and vol>0 else None,'max_drawdown':float((w/w.cummax()-1).min())}
def ev(q):
    core=q.p249; coreloan=.5*q.p249+.5*q.loan; coreclo=.5*q.p249+.5*q.clo; all3=(q.p249+q.loan+q.clo)/3
    ctl_cl=.5*q.p249_ctl+.5*q.clo_ctl; ctl_all=(q.p249_ctl+q.loan_ctl+q.clo_ctl)/3
    s={n:stats(v) for n,v in [('p249',core),('p249_p373',coreloan),('p249_clo',coreclo),('all3',all3),('clo',q.clo),('clo_ctl',q.clo_ctl),('ctl_cl',ctl_cl),('ctl_all',ctl_all)]}
    s['clo_excess']=s['clo']['cagr']-s['clo_ctl']['cagr']; s['p249_clo_excess']=s['p249_clo']['cagr']-s['ctl_cl']['cagr']; s['all3_excess']=s['all3']['cagr']-s['ctl_all']['cagr']
    s['vs_core']={'cagr':s['p249_clo']['cagr']-s['p249']['cagr'],'sharpe':s['p249_clo']['sharpe']-s['p249']['sharpe'],'maxdd':s['p249_clo']['max_drawdown']-s['p249']['max_drawdown']}
    s['vs_coreloan']={'cagr':s['all3']['cagr']-s['p249_p373']['cagr'],'sharpe':s['all3']['sharpe']-s['p249_p373']['sharpe'],'maxdd':s['all3']['max_drawdown']-s['p249_p373']['max_drawdown']}
    return s
full=ev(x); sub={k:ev(x.loc[a:b]) for k,(a,b) in BLOCKS.items()}; pos=sum(v['clo_excess']>0 for v in sub.values())
add=full['clo_excess']>0 and pos>=2 and full['p249_clo_excess']>0 and full['all3_excess']>0 and (full['vs_core']['sharpe']>0 or full['vs_core']['maxdd']>0) and (full['vs_coreloan']['sharpe']>0 or full['vs_coreloan']['maxdd']>0)
decision='ADDITIVE_COMPLEMENT' if add else 'NOT_ADDITIVE'
out={'schema':'research.aaa_clo_coverage_valid_confirmation_r2','workload_id':'AAA_CLO_COVERAGE_VALID_CONFIRMATION_R2','claim':'Coverage-valid confirmation of fixed JAAA/SGOV AAA CLO portfolio role beyond frozen P249 and P373.','coverage':coverage,'coverage_ok':coverage_ok,'contract':{'products':'JAAA/SGOV; P249=50/50 SPMO+IJS; P373=SRLN','blocks':BLOCKS,'min_months_per_block':12,'costs':'unchanged R1','no_rescue':True},'full_sample':full,'chronology':sub,'positive_clo_blocks':pos,'decision':decision,'decision_rule':'ADDITIVE only if standalone and both portfolio matched excess tests pass with >=2/3 positive blocks and risk improvement versus both cores. No rescue.'}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/aaa_clo_coverage_valid_confirmation_r2.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'coverage':coverage,'clo_excess_pp':round(100*full['clo_excess'],3),'positive_blocks':pos,'vs_coreloan':full['vs_coreloan']},sort_keys=True))

from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf

T=['AVDV','VSS','IDMO','EFA','SPMO','IJS','SPY','IJR','SRLN','HYG','SHY']
START='2015-01-01'; END='2026-09-10'; LB=24; EP=.0025
BLOCKS={'2020_2021':('2020-01-01','2021-12-31'),'2022_2023':('2022-01-01','2023-12-31'),'2024_plus':('2024-01-01',None)}
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw

def mr(t): return c[t].dropna().resample('ME').last().pct_change().dropna().rename(t)
R={t:mr(t) for t in T}
intl=pd.concat([R['AVDV'],R['IDMO']],axis=1).dropna().mean(axis=1).rename('intl')
intlctl=pd.concat([R['VSS'],R['EFA']],axis=1).dropna().mean(axis=1).rename('intlctl')
p249=pd.concat([R['SPMO'],R['IJS']],axis=1).dropna().mean(axis=1).rename('p249')
p249ctl=pd.concat([R['SPY'],R['IJR']],axis=1).dropna().mean(axis=1).rename('p249ctl')
loan_src=pd.concat([R['SRLN'],R['HYG'],R['SHY']],axis=1).dropna()
bs=[]
for i in range(len(loan_src)):
    if i<LB: bs.append((np.nan,np.nan)); continue
    b=np.linalg.lstsq(loan_src[['HYG','SHY']].iloc[i-LB:i].values,loan_src['SRLN'].iloc[i-LB:i].values,rcond=None)[0]; b=np.clip(b,0,1)
    if b.sum()>1: b=b/b.sum()
    bs.append(tuple(map(float,b)))
b=pd.DataFrame(bs,index=loan_src.index,columns=['hyg','shy']).shift(1)
loanctl=(b.hyg*loan_src.HYG+b.shy*loan_src.SHY).rename('loanctl')
x=pd.concat([R['AVDV'].rename('avdv'),R['VSS'].rename('avdvctl'),R['IDMO'].rename('idmo'),R['EFA'].rename('idmoctl'),intl,intlctl,p249,p249ctl,R['SRLN'].rename('loan'),loanctl],axis=1).dropna().loc['2020-01-01':]
coverage={k:int(len(x.loc[a:b])) for k,(a,b) in BLOCKS.items()}; coverage_ok=all(v>=12 for v in coverage.values())
if not coverage_ok:
    out={'schema':'research.avdv_idmo_coverage_valid_confirmation_r2','workload_id':'AVDV_IDMO_COVERAGE_VALID_CONFIRMATION_R2','coverage':coverage,'coverage_ok':False,'decision':'COVERAGE_GATE_FAILED','rule':'No performance inspection unless every frozen chronology block has >=12 common observations; products, 50/50 weight, controls, dates and costs unchanged.'}
    Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/avdv_idmo_coverage_valid_confirmation_r2.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True)); raise SystemExit(0)

def ep(s):
    y=s.copy(); y.iloc[0]-=EP; y.iloc[-1]-=EP; return y
def stats(s):
    q=ep(pd.Series(s,dtype=float).dropna()); n=len(q); w=(1+q).cumprod(); vol=q.std(ddof=1)*math.sqrt(12)
    return {'months':n,'cagr':float(w.iloc[-1]**(12/n)-1),'sharpe':float(q.mean()*12/vol) if vol>0 else None,'max_drawdown':float((w/w.cummax()-1).min())}
def ev(q):
    core=q.p249; coreloan=.5*q.p249+.5*q.loan; coreintl=.5*q.p249+.5*q.intl; all3=(q.p249+q.loan+q.intl)/3
    ci=.5*q.p249ctl+.5*q.intlctl; a3ctl=(q.p249ctl+q.loanctl+q.intlctl)/3
    ps,pls,pis,a3s=stats(core),stats(coreloan),stats(coreintl),stats(all3)
    ais,aic=stats(q.avdv),stats(q.avdvctl); ids,idc=stats(q.idmo),stats(q.idmoctl); ins,inc=stats(q.intl),stats(q.intlctl)
    return {'p249':ps,'p249_p373':pls,'p249_intl':pis,'all3':a3s,'avdv_excess':ais['cagr']-aic['cagr'],'idmo_excess':ids['cagr']-idc['cagr'],'intl_excess':ins['cagr']-inc['cagr'],'p249_intl_excess':pis['cagr']-stats(ci)['cagr'],'all3_excess':a3s['cagr']-stats(a3ctl)['cagr'],'vs_core':{'cagr':pis['cagr']-ps['cagr'],'sharpe':pis['sharpe']-ps['sharpe'],'maxdd':pis['max_drawdown']-ps['max_drawdown']},'vs_coreloan':{'cagr':a3s['cagr']-pls['cagr'],'sharpe':a3s['sharpe']-pls['sharpe'],'maxdd':a3s['max_drawdown']-pls['max_drawdown']}}
full=ev(x); sub={k:ev(x.loc[a:b]) for k,(a,b) in BLOCKS.items()}; pos=sum(v['intl_excess']>0 for v in sub.values())
add=full['intl_excess']>0 and pos>=2 and full['p249_intl_excess']>0 and full['all3_excess']>0 and (full['vs_core']['cagr']>0 or full['vs_core']['sharpe']>0 or full['vs_core']['maxdd']>0) and (full['vs_coreloan']['cagr']>0 or full['vs_coreloan']['sharpe']>0 or full['vs_coreloan']['maxdd']>0)
if add: decision='ADDITIVE_COMPLEMENT'
elif full['intl_excess']>0 and full['vs_core']['cagr']>0 and full['vs_coreloan']['cagr']>0: decision='RETURN_ENHANCER_WITH_CAVEAT'
elif full['intl_excess']<=0: decision='DEMOTED_WITH_CAVEAT'
else: decision='NEEDS_CONFIRMATION'
out={'schema':'research.avdv_idmo_coverage_valid_confirmation_r2','workload_id':'AVDV_IDMO_COVERAGE_VALID_CONFIRMATION_R2','claim':'Coverage-valid fixed 50/50 AVDV+IDMO portfolio utility beyond frozen P249 and P373.','coverage':coverage,'coverage_ok':coverage_ok,'contract':{'combo':'50/50 AVDV+IDMO','controls':'VSS/EFA','blocks':BLOCKS,'min_months_per_block':12,'costs':'unchanged R1','no_rescue':True},'full_sample':full,'chronology':sub,'positive_intl_blocks':pos,'decision':decision}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/avdv_idmo_coverage_valid_confirmation_r2.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'coverage':coverage,'intl_excess_pp':round(100*full['intl_excess'],3),'positive_blocks':pos,'vs_coreloan':full['vs_coreloan']},sort_keys=True))

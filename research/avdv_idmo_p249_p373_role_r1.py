from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
T=['AVDV','VSS','IDMO','EFA','SPMO','IJS','SPY','IJR','SRLN','HYG','SHY']; START='2015-01-01'; END='2026-09-10'; LB=24; EP=.0025
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
r=c[T].resample('ME').last().dropna().pct_change().dropna()
intl=.5*(r.AVDV+r.IDMO); intlctl=.5*(r.VSS+r.EFA); p249=.5*(r.SPMO+r.IJS); p249ctl=.5*(r.SPY+r.IJR)
bs=[]
for i in range(len(r)):
    if i<LB:bs.append((np.nan,np.nan));continue
    b=np.linalg.lstsq(r[['HYG','SHY']].iloc[i-LB:i].values,r.SRLN.iloc[i-LB:i].values,rcond=None)[0];b=np.clip(b,0,1)
    if b.sum()>1:b=b/b.sum()
    bs.append(tuple(map(float,b)))
b=pd.DataFrame(bs,index=r.index,columns=['hyg','shy']).shift(1);loanctl=b.hyg*r.HYG+b.shy*r.SHY
x=pd.DataFrame({'avdv':r.AVDV,'avdvctl':r.VSS,'idmo':r.IDMO,'idmoctl':r.EFA,'intl':intl,'intlctl':intlctl,'p249':p249,'p249ctl':p249ctl,'loan':r.SRLN,'loanctl':loanctl}).dropna().loc['2020-01-01':]
def ep(s):
    y=s.copy()
    if len(y):y.iloc[0]-=EP;y.iloc[-1]-=EP
    return y
def stats(s):
    q=ep(pd.Series(s,dtype=float).dropna());n=len(q)
    if n<2:return {'months':n,'cagr':None,'sharpe':None,'max_drawdown':None,'vol':None}
    w=(1+q).cumprod();vol=q.std(ddof=1)*math.sqrt(12);ann=q.mean()*12
    return {'months':n,'cagr':float(w.iloc[-1]**(12/n)-1),'sharpe':float(ann/vol) if vol else None,'max_drawdown':float((w/w.cummax()-1).min()),'vol':float(vol)}
def corr(a,b):
    z=pd.concat([a,b],axis=1).dropna();v=z.iloc[:,0].corr(z.iloc[:,1]) if len(z)>=3 else np.nan
    return float(v) if pd.notna(v) else None
def worst(s,n):
    z=(1+s).rolling(n).apply(np.prod,raw=True)-1;return float(z.min()) if z.notna().any() else None
def ev(q):
    core=q.p249; coreloan=.5*q.p249+.5*q.loan; coreintl=.5*q.p249+.5*q.intl; all3=(q.p249+q.loan+q.intl)/3
    cctl=q.p249ctl; ci=.5*q.p249ctl+.5*q.intlctl; a3ctl=(q.p249ctl+q.loanctl+q.intlctl)/3; neg=q.loc[q.p249<0]
    ps,pls,pis,a3s=stats(core),stats(coreloan),stats(coreintl),stats(all3); ais,aic=stats(q.avdv),stats(q.avdvctl); ids,idc=stats(q.idmo),stats(q.idmoctl); ins,inc=stats(q.intl),stats(q.intlctl)
    return {'p249':ps,'p249_plus_p373':pls,'p249_plus_intl':pis,'all3':a3s,'avdv_matched_excess_cagr':ais['cagr']-aic['cagr'],'idmo_matched_excess_cagr':ids['cagr']-idc['cagr'],'intl_matched_excess_cagr':ins['cagr']-inc['cagr'],'p249_intl_matched_excess_cagr':pis['cagr']-stats(ci)['cagr'],'all3_matched_excess_cagr':a3s['cagr']-stats(a3ctl)['cagr'],'impact_vs_p249':{'cagr_delta':pis['cagr']-ps['cagr'],'sharpe_delta':pis['sharpe']-ps['sharpe'],'maxdd_delta':pis['max_drawdown']-ps['max_drawdown']},'impact_vs_p249_p373':{'cagr_delta':a3s['cagr']-pls['cagr'],'sharpe_delta':a3s['sharpe']-pls['sharpe'],'maxdd_delta':a3s['max_drawdown']-pls['max_drawdown']},'return_corr':{'intl_p249':corr(q.intl,q.p249),'intl_p373':corr(q.intl,q.loan)},'residual_corr':{'intl_minus_control__p249_minus_control':corr(q.intl-q.intlctl,q.p249-q.p249ctl),'intl_minus_control__p373_minus_control':corr(q.intl-q.intlctl,q.loan-q.loanctl)},'downside_corr_when_p249_negative':{'intl_p249':corr(neg.intl,neg.p249),'intl_p373':corr(neg.intl,neg.loan)},'worst_12m':{'p249':worst(core,12),'p249_intl':worst(coreintl,12),'p249_p373':worst(coreloan,12),'all3':worst(all3,12)},'worst_24m':{'p249':worst(core,24),'p249_intl':worst(coreintl,24),'p249_p373':worst(coreloan,24),'all3':worst(all3,24)}}
blocks={'2020_2021':('2020-01-01','2021-12-31'),'2022_2023':('2022-01-01','2023-12-31'),'2024_plus':('2024-01-01',None)}
full=ev(x);sub={k:ev(x.loc[a:b]) for k,(a,b) in blocks.items()};coverage=all(v['p249']['months']>=12 for v in sub.values());pos=sum(v['intl_matched_excess_cagr']>0 for v in sub.values());i1=full['impact_vs_p249'];i2=full['impact_vs_p249_p373'];add=coverage and full['intl_matched_excess_cagr']>0 and pos>=2 and full['p249_intl_matched_excess_cagr']>0 and full['all3_matched_excess_cagr']>0 and (i1['cagr_delta']>0 or i1['sharpe_delta']>0 or i1['maxdd_delta']>0) and (i2['cagr_delta']>0 or i2['sharpe_delta']>0 or i2['maxdd_delta']>0)
if not coverage:decision='NEEDS_CONFIRMATION'
elif add:decision='ADDITIVE_COMPLEMENT'
elif full['intl_matched_excess_cagr']>0 and i1['cagr_delta']>0 and i2['cagr_delta']>0:decision='RETURN_ENHANCER_WITH_CAVEAT'
elif full['intl_matched_excess_cagr']<=0:decision='DEMOTED_WITH_CAVEAT'
elif abs(full['return_corr']['intl_p249'])>.85 and abs(full['return_corr']['intl_p373'])>.85:decision='REDUNDANT'
else:decision='NEEDS_CONFIRMATION'
out={'schema':'research.avdv_idmo_p249_p373_role_r1','workload_id':'AVDV_IDMO_P249_P373_PORTFOLIO_ROLE_R1','claim':'Test fixed 50/50 AVDV+IDMO for common-sample after-cost scientific portfolio utility beyond frozen P249 and P373 without reopening components or weights.','contract':{'international_combo':'50/50 AVDV+IDMO','component_controls':{'AVDV':'VSS','IDMO':'EFA'},'combo_control':'50/50 VSS+EFA','p249':'50/50 SPMO+IJS','p249_control':'50/50 SPY+IJR','p373':'SRLN','p373_control':'causal prior-24m HYG+SHY','endpoint_cost_bps_each':25,'blocks':blocks},'full_sample':full,'chronology':sub,'coverage_ok':coverage,'positive_intl_blocks':pos,'decision_rule':'ADDITIVE requires valid chronology, positive combo matched excess full sample and >=2/3 blocks, positive fixed-blend matched excess, and at least one CAGR/Sharpe/maxDD improvement versus both P249 and P249+P373. No rescue.','decision':decision,'scientific_consequence':'Preserve AVDV and IDMO component evidence and prior caveats if portfolio additivity fails. Coordinator retains ranking/allocation authority.','boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True);Path('research/artifacts/avdv_idmo_p249_p373_role_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False));print(json.dumps({'decision':decision,'months':full['p249']['months'],'intl_excess_pp':round(100*full['intl_matched_excess_cagr'],3),'impact_vs_p249':{k:round(v,4) for k,v in i1.items()},'impact_vs_p249_p373':{k:round(v,4) for k,v in i2.items()}},sort_keys=True))
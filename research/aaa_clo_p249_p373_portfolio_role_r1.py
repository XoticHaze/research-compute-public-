from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
T=['JAAA','SGOV','SPMO','IJS','SPY','IJR','SRLN','HYG','SHY']; START='2015-01-01'; END='2026-09-10'; LB=24
CLO_EP=.0025; CORE_EP=.0010; LOAN_EP=.0010
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
r=c[T].resample('ME').last().dropna().pct_change().dropna()
p249=.5*(r.SPMO+r.IJS); p249_ctl=.5*(r.SPY+r.IJR)
bs=[]
for i in range(len(r)):
    if i<LB: bs.append((np.nan,np.nan)); continue
    b=np.linalg.lstsq(r[['HYG','SHY']].iloc[i-LB:i].values,r.SRLN.iloc[i-LB:i].values,rcond=None)[0]; b=np.clip(b,0,1)
    if b.sum()>1:b=b/b.sum()
    bs.append(tuple(map(float,b)))
b=pd.DataFrame(bs,index=r.index,columns=['hyg','shy']).shift(1); loan_ctl=b.hyg*r.HYG+b.shy*r.SHY
x=pd.DataFrame({'p249':p249,'p249_ctl':p249_ctl,'loan':r.SRLN,'loan_ctl':loan_ctl,'clo':r.JAAA,'clo_ctl':r.SGOV}).dropna().loc['2021-01-01':]
def endpoint(s,cost):
    y=s.copy()
    if len(y):y.iloc[0]-=cost;y.iloc[-1]-=cost
    return y
for col,cost in [('p249',CORE_EP),('p249_ctl',CORE_EP),('loan',LOAN_EP),('loan_ctl',LOAN_EP),('clo',CLO_EP),('clo_ctl',CLO_EP)]:x[col]=endpoint(x[col],cost)
def stats(s):
    q=pd.Series(s,dtype=float).dropna(); w=(1+q).cumprod(); n=len(q); ann=q.mean()*12; vol=q.std(ddof=1)*math.sqrt(12)
    return {'months':int(n),'cagr':float(w.iloc[-1]**(12/n)-1),'sharpe':float(ann/vol) if vol else None,'max_drawdown':float((w/w.cummax()-1).min()),'vol':float(vol)}
def worst(s,n):
    z=(1+s).rolling(n).apply(np.prod,raw=True)-1
    return float(z.min()) if z.notna().any() else None
def ev(q):
    core=q.p249; coreloan=.5*q.p249+.5*q.loan; coreclo=.5*q.p249+.5*q.clo; all3=(q.p249+q.loan+q.clo)/3
    ctl_core=q.p249_ctl; ctl_cl=.5*q.p249_ctl+.5*q.clo_ctl; ctl_all=(q.p249_ctl+q.loan_ctl+q.clo_ctl)/3
    neg=q.loc[q.p249<0]
    return {'p249':stats(core),'p249_plus_p373':stats(coreloan),'p249_plus_clo':stats(coreclo),'p249_plus_p373_plus_clo':stats(all3),'clo':stats(q.clo),'clo_control':stats(q.clo_ctl),'clo_matched_excess_cagr':stats(q.clo)['cagr']-stats(q.clo_ctl)['cagr'],'p249_clo_matched_excess_cagr':stats(coreclo)['cagr']-stats(ctl_cl)['cagr'],'all3_matched_excess_cagr':stats(all3)['cagr']-stats(ctl_all)['cagr'],'clo_impact_vs_p249':{'cagr_delta':stats(coreclo)['cagr']-stats(core)['cagr'],'sharpe_delta':stats(coreclo)['sharpe']-stats(core)['sharpe'],'maxdd_delta':stats(coreclo)['max_drawdown']-stats(core)['max_drawdown']},'clo_impact_vs_p249_p373':{'cagr_delta':stats(all3)['cagr']-stats(coreloan)['cagr'],'sharpe_delta':stats(all3)['sharpe']-stats(coreloan)['sharpe'],'maxdd_delta':stats(all3)['max_drawdown']-stats(coreloan)['max_drawdown']},'return_corr':{'clo_p249':float(q.clo.corr(q.p249)),'clo_p373':float(q.clo.corr(q.loan))},'downside_corr_when_p249_negative':{'clo_p249':float(neg.clo.corr(neg.p249)) if len(neg)>2 else None,'clo_p373':float(neg.clo.corr(neg.loan)) if len(neg)>2 else None},'worst_12m':{'p249':worst(core,12),'p249_p373':worst(coreloan,12),'p249_clo':worst(coreclo,12),'all3':worst(all3,12)}}
blocks={'2021_2022':('2021-01-01','2022-12-31'),'2023_2024':('2023-01-01','2024-12-31'),'2025_plus':('2025-01-01',None)}
full=ev(x); sub={k:ev(x.loc[a:b]) for k,(a,b) in blocks.items()}; coverage_ok=all(v['clo']['months']>=12 for v in sub.values()); pos=sum(v['clo_matched_excess_cagr']>0 for v in sub.values()); i1=full['clo_impact_vs_p249']; i2=full['clo_impact_vs_p249_p373']
add=coverage_ok and full['clo_matched_excess_cagr']>0 and pos>=2 and full['p249_clo_matched_excess_cagr']>0 and full['all3_matched_excess_cagr']>0 and (i1['sharpe_delta']>0 or i1['maxdd_delta']>0) and (i2['sharpe_delta']>0 or i2['maxdd_delta']>0)
if not coverage_ok:decision='NEEDS_CONFIRMATION'
elif full['clo_matched_excess_cagr']<=0:decision='DEMOTED_WITH_CAVEAT'
elif add:decision='ADDITIVE_COMPLEMENT'
elif abs(full['return_corr']['clo_p373'])>0.85 and i2['sharpe_delta']<=0 and i2['maxdd_delta']<=0:decision='REDUNDANT_FIXED_INCOME'
else:decision='NEEDS_CONFIRMATION'
out={'schema':'research.aaa_clo_p249_p373_portfolio_role_r1','workload_id':'AAA_CLO_P249_P373_PORTFOLIO_ROLE_R1','claim':'Fixed JAAA representative of the independently replicated AAA CLO cash-plus family is tested for common-sample after-cost scientific additivity beyond frozen P249 and P373, without fund/control/window/cost/weight/threshold search.','contract':{'aaa_clo':'JAAA','matched_control':'SGOV','clo_endpoint_bps_each':25,'p249':'50/50 SPMO+IJS','p249_control':'50/50 SPY+IJR','p373':'SRLN','p373_control':'causal 24m HYG+SHY regression','core_and_loan_endpoint_bps_each':10,'portfolio_diagnostics':'fixed equal capital only','blocks':blocks,'min_months_per_block':12},'full_sample':full,'chronology':sub,'coverage_ok':coverage_ok,'positive_clo_blocks':pos,'explicit_2022':ev(x.loc['2022-01-01':'2022-12-31']),'decision_rule':'ADDITIVE_COMPLEMENT iff chronology coverage is valid, standalone CLO matched excess is positive full sample and >=2/3 blocks, both fixed portfolio blends retain positive matched excess, and adding CLO improves Sharpe or maxDD versus both P249 and P249+P373. REDUNDANT_FIXED_INCOME requires >0.85 CLO-P373 correlation plus no Sharpe/drawdown benefit versus P249+P373. No rescue.','decision':decision,'scientific_consequence':'Preserve P376/P377 standalone family support if portfolio additivity fails. Coordinator retains portfolio ranking/allocation authority.','boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True);Path('research/artifacts/aaa_clo_p249_p373_portfolio_role_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False));print(json.dumps({'decision':decision,'months':full['clo']['months'],'clo_excess_pp':round(100*full['clo_matched_excess_cagr'],3),'corr_p249':round(full['return_corr']['clo_p249'],3),'corr_p373':round(full['return_corr']['clo_p373'],3),'impact_vs_p249':{k:round(v,4) for k,v in i1.items()},'impact_vs_p249_p373':{k:round(v,4) for k,v in i2.items()}},sort_keys=True))
from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf

T=['XSMO','AVUV','IJR','SPMO','IJS','SPY','SRLN','HYG','SHY']
START='2015-01-01'; END='2026-09-10'; LB=24
SMALL_EP=0.0025; SMALL_REBAL=0.0010; CORE_EP=0.0010; LOAN_EP=0.0010
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
r=c[T].resample('ME').last().dropna().pct_change().dropna()

# Frozen P249 representation and exact control.
p249=.5*(r.SPMO+r.IJS); p249_ctl=.5*(r.SPY+r.IJR)
# Frozen P421 small-cap implementation: 50/50 monthly rebalance with 10bp per dollar one-way turnover; IJR control.
small=[]; turns=[]
for _,row in r.iterrows():
    gross=.5*row.XSMO+.5*row.AVUV
    denom=.5*(1+row.XSMO)+.5*(1+row.AVUV)
    w1=.5*(1+row.XSMO)/denom
    turn=abs(.5-w1)
    small.append(gross-SMALL_REBAL*turn); turns.append(turn)
small=pd.Series(small,index=r.index); small_ctl=r.IJR.copy()
# Frozen P373 causal HYG+SHY control.
bs=[]
for i in range(len(r)):
    if i<LB: bs.append((np.nan,np.nan)); continue
    b=np.linalg.lstsq(r[['HYG','SHY']].iloc[i-LB:i].values,r.SRLN.iloc[i-LB:i].values,rcond=None)[0]
    b=np.clip(b,0,1)
    if b.sum()>1: b=b/b.sum()
    bs.append(tuple(map(float,b)))
b=pd.DataFrame(bs,index=r.index,columns=['hyg','shy']).shift(1)
loan_ctl=b.hyg*r.HYG+b.shy*r.SHY; loan=r.SRLN.copy()
x=pd.DataFrame({'p249':p249,'p249_ctl':p249_ctl,'small':small,'small_ctl':small_ctl,'loan':loan,'loan_ctl':loan_ctl}).dropna().loc['2020-01-01':]

def endpoint(s,cost):
    y=s.copy()
    if len(y): y.iloc[0]-=cost; y.iloc[-1]-=cost
    return y
for col,cost in [('p249',CORE_EP),('p249_ctl',CORE_EP),('small',SMALL_EP),('small_ctl',SMALL_EP),('loan',LOAN_EP),('loan_ctl',LOAN_EP)]: x[col]=endpoint(x[col],cost)

def stats(s):
    q=pd.Series(s,dtype=float).dropna(); w=(1+q).cumprod(); n=len(q); ann=q.mean()*12; vol=q.std(ddof=1)*math.sqrt(12)
    return {'months':int(n),'cagr':float(w.iloc[-1]**(12/n)-1),'sharpe':float(ann/vol) if vol else None,'max_drawdown':float((w/w.cummax()-1).min()),'vol':float(vol)}
def roll_worst(s,n):
    q=pd.Series(s,dtype=float); vals=(1+q).rolling(n).apply(np.prod,raw=True)-1
    return float(vals.min()) if vals.notna().any() else None

def evaluate(q):
    core=q.p249; coreloan=.5*q.p249+.5*q.loan; coresmall=.5*q.p249+.5*q.small; all3=(q.p249+q.loan+q.small)/3
    cctl=q.p249_ctl; clctl=.5*q.p249_ctl+.5*q.loan_ctl; csctl=.5*q.p249_ctl+.5*q.small_ctl; a3ctl=(q.p249_ctl+q.loan_ctl+q.small_ctl)/3
    neg=q.loc[q.p249<0]
    return {
      'p249':stats(core),'p249_plus_p373':stats(coreloan),'p249_plus_smallcap':stats(coresmall),'p249_plus_p373_plus_smallcap':stats(all3),
      'p249_matched_excess_cagr':stats(core)['cagr']-stats(cctl)['cagr'],
      'smallcap_matched_excess_cagr':stats(q.small)['cagr']-stats(q.small_ctl)['cagr'],
      'p373_matched_excess_cagr':stats(q.loan)['cagr']-stats(q.loan_ctl)['cagr'],
      'p249_smallcap_matched_excess_cagr':stats(coresmall)['cagr']-stats(csctl)['cagr'],
      'all3_matched_excess_cagr':stats(all3)['cagr']-stats(a3ctl)['cagr'],
      'smallcap_impact_vs_p249':{'cagr_delta':stats(coresmall)['cagr']-stats(core)['cagr'],'sharpe_delta':stats(coresmall)['sharpe']-stats(core)['sharpe'],'maxdd_delta':stats(coresmall)['max_drawdown']-stats(core)['max_drawdown']},
      'smallcap_impact_vs_p249_p373':{'cagr_delta':stats(all3)['cagr']-stats(coreloan)['cagr'],'sharpe_delta':stats(all3)['sharpe']-stats(coreloan)['sharpe'],'maxdd_delta':stats(all3)['max_drawdown']-stats(coreloan)['max_drawdown']},
      'return_corr':{'smallcap_p249':float(q.small.corr(q.p249)),'smallcap_p373':float(q.small.corr(q.loan)),'p249_p373':float(q.p249.corr(q.loan))},
      'downside_corr_when_p249_negative':{'smallcap_p249':float(neg.small.corr(neg.p249)) if len(neg)>2 else None,'smallcap_p373':float(neg.small.corr(neg.loan)) if len(neg)>2 else None},
      'worst_12m':{'p249':roll_worst(core,12),'p249_smallcap':roll_worst(coresmall,12),'p249_p373':roll_worst(coreloan,12),'all3':roll_worst(all3,12)},
      'worst_24m':{'p249':roll_worst(core,24),'p249_smallcap':roll_worst(coresmall,24),'p249_p373':roll_worst(coreloan,24),'all3':roll_worst(all3,24)}
    }
blocks={'2020_2021':('2020-01-01','2021-12-31'),'2022_2023':('2022-01-01','2023-12-31'),'2024_plus':('2024-01-01',None)}
full=evaluate(x); sub={k:evaluate(x.loc[a:b]) for k,(a,b) in blocks.items()}
positive_small=sum(v['smallcap_matched_excess_cagr']>0 for v in sub.values())
impact1=full['smallcap_impact_vs_p249']; impact2=full['smallcap_impact_vs_p249_p373']
additive=(full['smallcap_matched_excess_cagr']>0 and positive_small>=2 and full['p249_smallcap_matched_excess_cagr']>0 and full['all3_matched_excess_cagr']>0 and (impact1['cagr_delta']>0 or impact1['sharpe_delta']>0 or impact1['maxdd_delta']>0) and (impact2['cagr_delta']>0 or impact2['sharpe_delta']>0 or impact2['maxdd_delta']>0) and impact1['maxdd_delta']>=-0.02 and impact2['maxdd_delta']>=-0.02)
if additive: decision='ADDITIVE_COMPLEMENT'
elif full['smallcap_matched_excess_cagr']>0 and positive_small>=2 and impact1['cagr_delta']>0 and impact2['cagr_delta']>0: decision='RETURN_ENHANCER_WITH_CAVEAT'
elif full['smallcap_matched_excess_cagr']<=0: decision='DEMOTED_WITH_CAVEAT'
elif abs(full['return_corr']['smallcap_p249'])>0.85 and abs(full['return_corr']['smallcap_p373'])>0.85: decision='REDUNDANT'
else: decision='NEEDS_CONFIRMATION'
out={'schema':'research.smallcap_p249_p373_portfolio_role_r1','workload_id':'SMALLCAP_P249_P373_PORTFOLIO_ROLE_R1','claim':'Fixed XSMO+AVUV small-cap implementation is tested for common-sample after-cost scientific portfolio utility versus frozen P249 and P373 without weight, fund, window, control, cost or threshold search.','contract':{'smallcap':'50/50 XSMO+AVUV monthly rebalanced','smallcap_control':'IJR','smallcap_endpoint_bps_each':25,'smallcap_rebalance_bps_per_oneway_turnover':10,'p249':'50/50 SPMO+IJS','p249_control':'50/50 SPY+IJR','p373':'SRLN','p373_control':'causal 24m HYG+SHY regression','core_endpoint_bps_each':10,'loan_endpoint_bps_each':10,'portfolio_diagnostics':'fixed equal capital only','windows':blocks},'mean_monthly_smallcap_oneway_turnover':float(np.mean(turns[-len(x):])),'full_sample':full,'chronology':sub,'decision_rule':'ADDITIVE_COMPLEMENT iff small-cap standalone matched excess is positive full sample and >=2/3 blocks, both fixed portfolio blends retain positive matched excess, small-cap improves at least one of CAGR/Sharpe/maxDD versus P249 and versus P249+P373, and maxDD worsens by <=2pp in each comparison; otherwise fixed caveat classes apply without rescue.','decision':decision,'scientific_consequence':'Preserve P417/P420/P421 standalone support regardless of portfolio-role result. This result informs scientific additivity only; Coordinator retains portfolio ranking/allocation authority.','boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/smallcap_p249_p373_portfolio_role_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'smallcap_excess_pp':round(100*full['smallcap_matched_excess_cagr'],3),'smallcap_corr_p249':round(full['return_corr']['smallcap_p249'],3),'smallcap_corr_p373':round(full['return_corr']['smallcap_p373'],3),'impact_vs_p249':{k:round(v,4) for k,v in impact1.items()},'impact_vs_p249_p373':{k:round(v,4) for k,v in impact2.items()}},sort_keys=True))
from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import p248_smallvalue_survivor_complementarity_r1 as p248

SV_BP=10; WINDOWS={'2020':'2020-01-01','2022':'2022-01-01'}
def metrics(r):
 q=pd.Series(r,dtype=float).dropna(); e=(1+q).cumprod(); n=len(q); ann=float(q.mean()*12); vol=float(q.std(ddof=1)*math.sqrt(12)); return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1),'maxdd':float((e/e.cummax()-1).min()),'sharpe_rf0':float(ann/vol) if vol else None}
def ep(r,bps):
 q=pd.Series(r,dtype=float).dropna().copy(); f=bps/10000
 if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
 return q
svm=p248.close_month[['AVUV','AVDV','IJR','VSS']].pct_change().dropna(); sv=.5*svm.AVUV+.5*svm.AVDV; svctrl=.5*svm.IJR+.5*svm.VSS
p64=p248.p64.copy(); p64.index=p64.index.to_period('M').to_timestamp('M'); p36=p248.p36.copy(); p36.index=p36.index.to_period('M').to_timestamp('M')
x=sv.to_frame('sv').join(svctrl.rename('svm')).join(p64.rename(columns={'candidate':'p64','matched':'p64m'})).join(p36.rename(columns={'candidate':'p36','matched':'p36m'})).dropna(); outw={}
for name,start in WINDOWS.items():
 q=x.loc[x.index>=pd.Timestamp(start)].copy(); full=(q.sv+q.p64+q.p36)/3; fullm=(q.svm+q.p64m+q.p36m)/3; without=(q.p64+q.p36)/2; withoutm=(q.p64m+q.p36m)/2; fulln=ep(full,SV_BP/3); fullmn=ep(fullm,SV_BP/3); sp=p248.close_month.SPY.pct_change().reindex(q.index); qq=p248.close_month.QQQ.pct_change().reindex(q.index); fm=metrics(fulln); wm=metrics(without); folds=[]
 for i,ix in enumerate(np.array_split(np.arange(len(q)),5),1):
  a=ep(full.iloc[ix],SV_BP/3); b=ep(fullm.iloc[ix],SV_BP/3); folds.append({'fold':i,'excess_cagr':metrics(a)['cagr']-metrics(b)['cagr']})
 eq=(1+fulln).cumprod(); dd=eq/eq.cummax()-1; ddm=dd<0; neg=q[['sv','p64','p36']]<0; allneg=neg.all(axis=1); sv_contrib=(q.sv/3).where(ddm).dropna(); total=(full).where(ddm).dropna()
 outw[name]={'months':len(q),'fixed_equal_three':fm,'matched_equal_three':metrics(fullmn),'matched_excess_cagr':fm['cagr']-metrics(fullmn)['cagr'],'vs_spy_cagr':fm['cagr']-metrics(ep(sp,SV_BP/3))['cagr'],'vs_qqq_cagr':fm['cagr']-metrics(ep(qq,SV_BP/3))['cagr'],'positive_matched_folds':sum(z['excess_cagr']>0 for z in folds),'folds':folds,'without_smallvalue_fixed_p64_p36':wm,'smallvalue_removal_impact':{'cagr_delta':fm['cagr']-wm['cagr'],'sharpe_delta':fm['sharpe_rf0']-wm['sharpe_rf0'],'maxdd_delta':fm['maxdd']-wm['maxdd']},'downside_overlap':{'all_three_negative_month_fraction':float(allneg.mean()),'all_three_negative_given_portfolio_drawdown_month_fraction':float(allneg[ddm].mean()) if ddm.any() else None,'smallvalue_mean_return_contribution_on_portfolio_drawdown_months':float(sv_contrib.mean()) if len(sv_contrib) else None,'portfolio_mean_return_on_drawdown_months':float(total.mean()) if len(total) else None}}
a=outw['2020']; b=outw['2022']; ri=a['smallvalue_removal_impact']; support=a['matched_excess_cagr']>0 and b['matched_excess_cagr']>0 and a['positive_matched_folds']>=4 and (ri['cagr_delta']>0 or ri['sharpe_delta']>0) and ri['maxdd_delta']>=-0.05
out={'schema':'research.p249_smallvalue_capital_role_r1','parent':'P239/P248/P249','claim':'The fixed small-value leader earns a distinct capital role in an equal-weight three-primitive-sleeve research portfolio with P64 and P36, measured by matched alpha, opportunity cost, downside overlap, and prospective removal impact.','contract':{'primitive_sleeves':['fixed 50/50 AVUV/AVDV','P64 unchanged','P36 unchanged'],'capital_rule':'equal 1/3 each','removal_comparator':'fixed 50/50 P64/P36','matched_rule':'equal blend of each sleeve matched control','smallvalue_cost_bps':SV_BP,'survivor_costs':'preserved from P248/P64/P36','windows':WINDOWS,'gate':'positive matched excess both windows; >=4/5 positive 2020+ folds; small-value removal improves CAGR or Sharpe; maxdd worsening no more than 5pp','no_weight_window_survivor_or_parameter_search':True},'tests':outw,'decision':'P249_CAPITAL_ROLE_SUPPORTED' if support else 'P249_CAPITAL_ROLE_NOT_SUPPORTED','limitations':['scientific fixed-rule test only; not portfolio allocation authority','common sample constrained by AVUV/AVDV history','Yahoo adjusted prices research-only'],'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'live_trading':False}}
Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p249_smallvalue_capital_role_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
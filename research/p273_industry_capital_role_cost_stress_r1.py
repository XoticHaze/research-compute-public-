from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
import p248_smallvalue_survivor_complementarity_r1 as p248

INDUSTRIES=['XAR','XBI','XHB','XME','XOP','XPH','XRT','XSD','XSW','XTN','KRE']; TOPK=3; IND_COST_BP=50; SV_BP=10; WINDOWS={'2020':'2020-01-01','2022':'2022-01-01'}
def metrics(r):
 q=pd.Series(r,dtype=float).dropna(); e=(1+q).cumprod(); n=len(q); ann=float(q.mean()*12); vol=float(q.std(ddof=1)*math.sqrt(12)); return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1),'maxdd':float((e/e.cummax()-1).min()),'sharpe_rf0':float(ann/vol) if vol else None}
def ep(r,bps):
 q=pd.Series(r,dtype=float).dropna().copy(); f=bps/10000
 if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
 return q
def industry():
 raw=yf.download(INDUSTRIES,start='2010-01-01',end='2026-09-03',auto_adjust=True,progress=False,threads=False); c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw; m=c[INDUSTRIES].dropna().resample('ME').last(); r=m.pct_change(); s=m.shift(1)/m.shift(12)-1; w=pd.DataFrame(0.,index=m.index,columns=INDUSTRIES)
 for dt,row in s.iterrows():
  if row.notna().sum()==len(INDUSTRIES): w.loc[dt,row.nlargest(TOPK).index]=1/TOPK
 turn=.5*w.diff().abs().sum(axis=1); active=w.sum(axis=1).gt(0)
 if active.any(): turn.loc[active.idxmax()]=1.
 cand=(w*r).sum(axis=1)-(IND_COST_BP/10000)*turn; matched=r.mean(axis=1).copy()
 if active.any(): matched.loc[active.idxmax()]-=IND_COST_BP/10000
 return pd.DataFrame({'ind':cand,'indm':matched})
svm=p248.close_month[['AVUV','AVDV','IJR','VSS']].pct_change().dropna(); sv=.5*svm.AVUV+.5*svm.AVDV; svm2=.5*svm.IJR+.5*svm.VSS; p64=p248.p64.copy(); p64.index=p64.index.to_period('M').to_timestamp('M'); p36=p248.p36.copy(); p36.index=p36.index.to_period('M').to_timestamp('M'); ind=industry(); ind.index=ind.index.to_period('M').to_timestamp('M'); x=sv.to_frame('sv').join(svm2.rename('svm')).join(p64.rename(columns={'candidate':'p64','matched':'p64m'})).join(p36.rename(columns={'candidate':'p36','matched':'p36m'})).join(ind).dropna(); out={}
for name,start in WINDOWS.items():
 q=x.loc[x.index>=pd.Timestamp(start)]; full=(q.sv+q.p64+q.p36+q.ind)/4; fullm=(q.svm+q.p64m+q.p36m+q.indm)/4; base=(q.sv+q.p64+q.p36)/3; fn=ep(full,SV_BP/4); fmn=ep(fullm,SV_BP/4); bn=ep(base,SV_BP/3); fm,mm,bm=metrics(fn),metrics(fmn),metrics(bn); folds=[]
 for i,ix in enumerate(np.array_split(np.arange(len(q)),5),1):
  a=ep(full.iloc[ix],SV_BP/4); b=ep(fullm.iloc[ix],SV_BP/4); folds.append({'fold':i,'matched_excess_cagr':metrics(a)['cagr']-metrics(b)['cagr']})
 out[name]={'fixed_equal_four':fm,'matched_equal_four':mm,'matched_excess_cagr':fm['cagr']-mm['cagr'],'positive_matched_folds':sum(z['matched_excess_cagr']>0 for z in folds),'fixed_equal_three_p249':bm,'industry_addition_impact':{'cagr_delta':fm['cagr']-bm['cagr'],'sharpe_delta':fm['sharpe_rf0']-bm['sharpe_rf0'],'maxdd_delta':fm['maxdd']-bm['maxdd']},'folds':folds}
a=out['2020']; b=out['2022']; d=a['industry_addition_impact']; ok=a['matched_excess_cagr']>0 and b['matched_excess_cagr']>0 and a['positive_matched_folds']>=4 and (d['cagr_delta']>0 or d['sharpe_delta']>0) and d['maxdd_delta']>=-0.05
res={'schema':'research.p273_industry_capital_role_cost_stress_r1','parent':'P266/P272/P273','claim':'P272 incremental capital-role evidence survives doubling P266 industry turnover cost from 25 to 50 bps with signals, weights, controls, windows and other sleeve costs frozen.','contract':{'industry_cost_bps_per_one_way_turnover':IND_COST_BP,'baseline_p272_industry_cost_bps':25,'capital_rule':'equal quarter unchanged','windows':WINDOWS,'gate':'same P272 gate under doubled industry turnover cost','no_signal_weight_window_or_parameter_change':True},'tests':out,'decision':'P273_COST_STRESS_SUPPORTED' if ok else 'P273_COST_STRESS_NOT_SUPPORTED','limitations':['scientific cost stress only; not portfolio allocation/ranking authority','Yahoo adjusted prices research-only'],'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p273_industry_capital_role_cost_stress_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(res,sort_keys=True))

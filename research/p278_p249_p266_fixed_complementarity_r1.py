from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import p248_smallvalue_survivor_complementarity_r1 as p248

INDUSTRIES=['XAR','XBI','XHB','XME','XOP','XPH','XRT','XSD','XSW','XTN','KRE']
TOPK=3; IND_COST_BP=50; SV_BP=10; WINDOWS={'2020':'2020-01-01','2022':'2022-01-01'}

def metrics(r):
 q=pd.Series(r,dtype=float).dropna(); e=(1+q).cumprod(); n=len(q); ann=float(q.mean()*12); vol=float(q.std(ddof=1)*math.sqrt(12)); return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1),'maxdd':float((e/e.cummax()-1).min()),'sharpe_rf0':float(ann/vol) if vol else None,'worst_rolling_12m':float(((1+q).rolling(12).apply(np.prod,raw=True)-1).min()) if n>=12 else None}
def ep(r,bps):
 q=pd.Series(r,dtype=float).dropna().copy(); f=bps/10000
 if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
 return q

def industry_sleeve():
 import yfinance as yf
 raw=yf.download(INDUSTRIES,start='2010-01-01',end='2026-09-03',auto_adjust=True,progress=False,threads=False)
 close=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
 m=close[INDUSTRIES].dropna().resample('ME').last(); ret=m.pct_change(); score=m.shift(1)/m.shift(12)-1
 w=pd.DataFrame(0.0,index=m.index,columns=INDUSTRIES)
 for dt,row in score.iterrows():
  if row.notna().sum()==len(INDUSTRIES): w.loc[dt,row.nlargest(TOPK).index]=1/TOPK
 gross=(w*ret).sum(axis=1); turn=.5*w.diff().abs().sum(axis=1); active=w.sum(axis=1).gt(0)
 if active.any(): turn.loc[active.idxmax()]=1.0
 cand=gross-(IND_COST_BP/10000)*turn; matched=ret.mean(axis=1).copy()
 if active.any(): matched.loc[active.idxmax()]-=IND_COST_BP/10000
 return pd.DataFrame({'ind':cand,'indm':matched})

svm=p248.close_month[['AVUV','AVDV','IJR','VSS']].pct_change().dropna(); sv=.5*svm.AVUV+.5*svm.AVDV; svctrl=.5*svm.IJR+.5*svm.VSS
p64=p248.p64.copy(); p64.index=p64.index.to_period('M').to_timestamp('M'); p36=p248.p36.copy(); p36.index=p36.index.to_period('M').to_timestamp('M')
ind=industry_sleeve(); ind.index=ind.index.to_period('M').to_timestamp('M')
x=sv.to_frame('sv').join(svctrl.rename('svm')).join(p64.rename(columns={'candidate':'p64','matched':'p64m'})).join(p36.rename(columns={'candidate':'p36','matched':'p36m'})).join(ind).dropna(); out={}
for name,start in WINDOWS.items():
 q=x.loc[x.index>=pd.Timestamp(start)].copy(); core=(q.sv+q.p64+q.p36)/3; corem=(q.svm+q.p64m+q.p36m)/3; sat=(q.sv+q.p64+q.p36+q.ind)/4; satm=(q.svm+q.p64m+q.p36m+q.indm)/4
 coren=ep(core,SV_BP/3); coremn=ep(corem,SV_BP/3); satn=ep(sat,SV_BP/4); satmn=ep(satm,SV_BP/4); cm=metrics(coren); sm=metrics(satn); cmm=metrics(coremn); smm=metrics(satmn)
 folds=[]
 for i,ix in enumerate(np.array_split(np.arange(len(q)),5),1):
  a=ep(sat.iloc[ix],SV_BP/4); b=ep(core.iloc[ix],SV_BP/3); folds.append({'fold':i,'satellite_minus_core_cagr':metrics(a)['cagr']-metrics(b)['cagr']})
 coredd=(1+coren).cumprod(); coredd=coredd/coredd.cummax()-1; satdd=(1+satn).cumprod(); satdd=satdd/satdd.cummax()-1
 out[name]={'months':len(q),'p249_core':cm,'p249_core_matched':cmm,'p249_core_matched_excess_cagr':cm['cagr']-cmm['cagr'],'p249_plus_p266_fixed_equal_four':sm,'p249_plus_p266_matched':smm,'p249_plus_p266_matched_excess_cagr':sm['cagr']-smm['cagr'],'satellite_increment':{'cagr_delta':sm['cagr']-cm['cagr'],'sharpe_delta':sm['sharpe_rf0']-cm['sharpe_rf0'],'maxdd_delta':sm['maxdd']-cm['maxdd'],'worst_rolling_12m_delta':sm['worst_rolling_12m']-cm['worst_rolling_12m'],'return_corr':float(coren.corr(satn)),'drawdown_corr':float(coredd.corr(satdd)),'positive_calendar_folds':sum(z['satellite_minus_core_cagr']>0 for z in folds),'folds':folds}}
a=out['2020']; b=out['2022']; ai=a['satellite_increment']; bi=b['satellite_increment']
support=(ai['cagr_delta']>0 and bi['cagr_delta']>0 and ai['positive_calendar_folds']>=3 and bi['positive_calendar_folds']>=3 and ai['maxdd_delta']>=0 and bi['maxdd_delta']>=0 and ai['worst_rolling_12m_delta']>=0 and bi['worst_rolling_12m_delta']>=0)
res={'schema':'research.p278_p249_p266_fixed_complementarity_r1','parent':'P249/P266/P268/P272/P273/P274/P277/P278','claim':'Adjudicate whether the frozen P266 regime-dependent satellite adds enough fixed portfolio utility to the leading P249 core to earn scarce capital without optimization.','contract':{'core':'P249 fixed equal-third small-value/P64/P36','satellite':'P266 fixed 12-1 top-3 industry momentum','combined_rule':'equal 1/4 each, no weight search','industry_cost_bps_per_one_way_turnover':IND_COST_BP,'smallvalue_cost_bps':SV_BP,'windows':WINDOWS,'gate':'satellite improves CAGR, max drawdown, worst rolling 12m and >=3/5 calendar folds in both windows; no parameter/weight/window search','no_optimization':True},'tests':out,'decision':'P278_P266_SATELLITE_CAPITAL_ROLE_SUPPORTED' if support else 'P278_P249_CORE_PREFERRED_P266_OPTIONAL_ONLY','limitations':['fixed-rule research comparison only; not allocation authority','common sample constrained by AVUV/AVDV history','Yahoo adjusted prices research-only'],'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p278_p249_p266_fixed_complementarity_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(res,sort_keys=True))

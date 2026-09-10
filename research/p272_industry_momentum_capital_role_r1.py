from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
import p248_smallvalue_survivor_complementarity_r1 as p248

INDUSTRIES=['XAR','XBI','XHB','XME','XOP','XPH','XRT','XSD','XSW','XTN','KRE']
TOPK=3; IND_COST_BP=25; SV_BP=10; WINDOWS={'2020':'2020-01-01','2022':'2022-01-01'}

def metrics(r):
 q=pd.Series(r,dtype=float).dropna(); e=(1+q).cumprod(); n=len(q); ann=float(q.mean()*12); vol=float(q.std(ddof=1)*math.sqrt(12)); return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1),'maxdd':float((e/e.cummax()-1).min()),'sharpe_rf0':float(ann/vol) if vol else None}
def ep(r,bps):
 q=pd.Series(r,dtype=float).dropna().copy(); f=bps/10000
 if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
 return q

def industry_sleeve():
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
 q=x.loc[x.index>=pd.Timestamp(start)].copy(); full=(q.sv+q.p64+q.p36+q.ind)/4; fullm=(q.svm+q.p64m+q.p36m+q.indm)/4; base=(q.sv+q.p64+q.p36)/3
 fulln=ep(full,SV_BP/4); fullmn=ep(fullm,SV_BP/4); basen=ep(base,SV_BP/3); fm=metrics(fulln); mm=metrics(fullmn); bm=metrics(basen); folds=[]
 for i,ix in enumerate(np.array_split(np.arange(len(q)),5),1):
  a=ep(full.iloc[ix],SV_BP/4); b=ep(fullm.iloc[ix],SV_BP/4); folds.append({'fold':i,'matched_excess_cagr':metrics(a)['cagr']-metrics(b)['cagr']})
 sp=p248.close_month.SPY.pct_change().reindex(q.index); qq=p248.close_month.QQQ.pct_change().reindex(q.index)
 out[name]={'fixed_equal_four':fm,'matched_equal_four':mm,'matched_excess_cagr':fm['cagr']-mm['cagr'],'positive_matched_folds':sum(z['matched_excess_cagr']>0 for z in folds),'folds':folds,'fixed_equal_three_p249':bm,'industry_addition_impact':{'cagr_delta':fm['cagr']-bm['cagr'],'sharpe_delta':fm['sharpe_rf0']-bm['sharpe_rf0'],'maxdd_delta':fm['maxdd']-bm['maxdd']},'vs_spy_cagr':fm['cagr']-metrics(ep(sp,SV_BP/4))['cagr'],'vs_qqq_cagr':fm['cagr']-metrics(ep(qq,SV_BP/4))['cagr']}
a=out['2020']; b=out['2022']; ri=a['industry_addition_impact']; support=a['matched_excess_cagr']>0 and b['matched_excess_cagr']>0 and a['positive_matched_folds']>=4 and (ri['cagr_delta']>0 or ri['sharpe_delta']>0) and ri['maxdd_delta']>=-0.05
res={'schema':'research.p272_industry_momentum_capital_role_r1','parent':'P249/P266/P272','claim':'The frozen P266 industry-momentum sleeve earns an incremental scientific capital role when added at a prospectively fixed equal quarter to the already-supported P249 primitive set, without weight optimization or portfolio-ranking authority.','contract':{'primitive_sleeves':['fixed 50/50 AVUV/AVDV','P64 unchanged','P36 unchanged','P266 fixed industry momentum'],'capital_rule':'equal 1/4 each','removal_comparator':'fixed P249 equal-third small-value/P64/P36','matched_rule':'equal blend of each sleeve matched control','industry_signal':'P266 fixed 12-1 top-3 across 11 industries','industry_cost_bps_per_one_way_turnover':IND_COST_BP,'smallvalue_cost_bps':SV_BP,'windows':WINDOWS,'gate':'positive matched excess both windows; >=4/5 positive 2020+ folds; P266 addition improves CAGR or Sharpe; maxdd worsening no more than 5pp','no_weight_window_survivor_or_parameter_search':True},'tests':out,'decision':'P272_INDUSTRY_MOMENTUM_CAPITAL_ROLE_SUPPORTED' if support else 'P272_INDUSTRY_MOMENTUM_CAPITAL_ROLE_NOT_SUPPORTED','limitations':['scientific fixed-rule combination test only; not portfolio allocation/ranking authority','common sample constrained by AVUV/AVDV history','Yahoo adjusted prices research-only'],'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p272_industry_momentum_capital_role_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(res,sort_keys=True))

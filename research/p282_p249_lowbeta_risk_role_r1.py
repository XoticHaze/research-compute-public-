from __future__ import annotations
import json, math, importlib.util
from pathlib import Path
import numpy as np
import pandas as pd
import p281_sector_lowbeta_r1 as p281

P248_PATH=Path(__file__).with_name('p248_smallvalue_survivor_complementarity_r1.py')
if not P248_PATH.is_file(): raise RuntimeError('P282 requires admitted P248 source owner')
spec=importlib.util.spec_from_file_location('p248_owner',P248_PATH); p248=importlib.util.module_from_spec(spec); spec.loader.exec_module(p248)
SV_BP=10; WINDOWS={'2020':'2020-01-01','2022':'2022-01-01'}
def metric(r):
 q=pd.Series(r,dtype=float).dropna(); e=(1+q).cumprod(); n=len(q); vol=float(q.std(ddof=1)*math.sqrt(12)); ann=float(q.mean()*12)
 return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1),'maxdd':float((e/e.cummax()-1).min()),'sharpe_rf0':float(ann/vol) if vol else None,'worst_rolling_12m':float(((1+q).rolling(12).apply(np.prod,raw=True)-1).min()) if n>=12 else None}
def ep(r,bps):
 q=pd.Series(r,dtype=float).dropna().copy(); f=bps/10000
 if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
 return q
svm=p248.close_month[['AVUV','AVDV','IJR','VSS']].pct_change().dropna(); sv=.5*svm.AVUV+.5*svm.AVDV; svctrl=.5*svm.IJR+.5*svm.VSS
p64=p248.p64.copy(); p64.index=p64.index.to_period('M').to_timestamp('M'); p36=p248.p36.copy(); p36.index=p36.index.to_period('M').to_timestamp('M')
lb=p281.r[['model_25','matched']].copy(); lb.index=lb.index.to_period('M').to_timestamp('M'); lb=lb.rename(columns={'model_25':'lb','matched':'lbm'})
x=sv.to_frame('sv').join(svctrl.rename('svm')).join(p64.rename(columns={'candidate':'p64','matched':'p64m'})).join(p36.rename(columns={'candidate':'p36','matched':'p36m'})).join(lb).dropna(); out={}
for name,start in WINDOWS.items():
 q=x.loc[x.index>=pd.Timestamp(start)]; core=(q.sv+q.p64+q.p36)/3; corem=(q.svm+q.p64m+q.p36m)/3; combo=(q.sv+q.p64+q.p36+q.lb)/4; combom=(q.svm+q.p64m+q.p36m+q.lbm)/4
 cn=ep(core,SV_BP/3); cmn=ep(corem,SV_BP/3); fn=ep(combo,SV_BP/4); fmn=ep(combom,SV_BP/4); c=metric(cn); f=metric(fn); fm=metric(fmn)
 folds=[]
 for i,ix in enumerate(np.array_split(np.arange(len(q)),5),1):
  a=ep(combo.iloc[ix],SV_BP/4); b=ep(core.iloc[ix],SV_BP/3); folds.append({'fold':i,'combo_minus_core_cagr':metric(a)['cagr']-metric(b)['cagr']})
 out[name]={'p249_core':c,'combo':f,'combo_matched':fm,'combo_matched_excess_cagr':f['cagr']-fm['cagr'],'lowbeta_increment':{'cagr_delta':f['cagr']-c['cagr'],'sharpe_delta':f['sharpe_rf0']-c['sharpe_rf0'],'maxdd_delta':f['maxdd']-c['maxdd'],'worst_rolling_12m_delta':f['worst_rolling_12m']-c['worst_rolling_12m'],'positive_calendar_folds':sum(z['combo_minus_core_cagr']>0 for z in folds),'folds':folds}}
a=out['2020']['lowbeta_increment']; b=out['2022']['lowbeta_increment']; support=(a['maxdd_delta']>0 and b['maxdd_delta']>0 and a['worst_rolling_12m_delta']>0 and b['worst_rolling_12m_delta']>0 and a['sharpe_delta']>=0 and b['sharpe_delta']>=0 and a['cagr_delta']>=-.02 and b['cagr_delta']>=-.02)
res={'schema':'research.p282_p249_lowbeta_risk_role_r1','parent':'P249/P281/P282','claim':'Adjudicate whether the frozen P281 low-beta sector sleeve adds enough fixed risk efficiency to the supported P249 equal-third core at an equal quarter to justify preserving a scientific risk-role hypothesis, without optimizing weights or rescuing P281 standalone alpha.','contract':{'core':'P249 fixed equal-third small-value/P64/P36','addition':'P281 frozen low-beta sector sleeve at 25 bp turnover cost','combined_rule':'equal 1/4 each, no weight search','windows':WINDOWS,'gate':'risk-role supported only if max drawdown and worst rolling 12m improve in both windows, Sharpe is non-worse in both, and CAGR drag is no worse than 2pp in either window','no_optimization':True},'tests':out,'decision':'P282_LOWBETA_RISK_ROLE_SUPPORTED' if support else 'P282_LOWBETA_RISK_ROLE_NOT_SUPPORTED','limitations':['fixed scientific combination only; not allocation/ranking authority','Yahoo adjusted-price research data','common sample constrained by AVUV/AVDV history'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p282_p249_lowbeta_risk_role_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(res,sort_keys=True))

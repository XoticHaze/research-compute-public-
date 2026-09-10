from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
T=['SPMO','IJS','SPY','IJR','SRLN','HYG','SHY','FNDF','VEA','AVDV','IDMO','VSS','EFA','UUP'];COST=.0025;SWITCH=.001
raw=yf.download(T,start='2015-01-01',end='2026-09-11',auto_adjust=True,progress=False,threads=False);c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw;m=c[T].resample('ME').last();r=m.pct_change(fill_method=None)
p=.5*(r.SPMO+r.IJS);pc=.5*(r.SPY+r.IJR);bs=[]
for i in range(len(r)):
 z=r[['HYG','SHY','SRLN']].iloc[max(0,i-24):i].dropna()
 if len(z)<24:bs.append((np.nan,np.nan));continue
 b=np.clip(np.linalg.lstsq(z[['HYG','SHY']].values,z.SRLN.values,rcond=None)[0],0,1);b=b/b.sum() if b.sum()>1 else b;bs.append(tuple(b))
b=pd.DataFrame(bs,index=r.index,columns=['h','s']).shift(1);lc=b.h*r.HYG+b.s*r.SHY
sig=(m.UUP/m.UUP.shift(12)-1<0).shift(1).astype(float);reg=sig*r.FNDF+(1-sig)*r.VEA;intl=.5*(r.AVDV+r.IDMO);intlc=.5*(r.VSS+r.EFA)
q=pd.DataFrame({'core':.5*p+.5*r.SRLN,'corec':.5*pc+.5*lc,'reg':reg,'intl':intl,'regc':r.VEA,'intlc':intlc,'sig':sig}).dropna().loc['2021-01-01':]
def st(s,switches=None):
 x=s.copy();x.iloc[0]-=COST;x.iloc[-1]-=COST
 if switches:
  for d in switches:
   if d in x.index:x.loc[d]-=SWITCH*.25
 w=(1+x).cumprod();n=len(x);v=x.std(ddof=1)*math.sqrt(12);neg=x[x<0].std(ddof=1)*math.sqrt(12)
 return {'cagr':float(w.iloc[-1]**(12/n)-1),'sharpe':float(x.mean()*12/v),'max_drawdown':float((w/w.cummax()-1).min()),'downside_vol':float(neg) if pd.notna(neg) else None}
def residual_corr(z):
 X=np.column_stack([np.ones(len(z)),z.core.values]);ar=np.linalg.lstsq(X,z.reg.values,rcond=None)[0];ai=np.linalg.lstsq(X,z.intl.values,rcond=None)[0];rr=z.reg.values-X@ar;ri=z.intl.values-X@ai
 return {'return_corr':float(z.reg.corr(z.intl)),'residual_corr_vs_core':float(np.corrcoef(rr,ri)[0,1])}
def ev(z):
 a=.75*z.core+.25*z.reg;i=.75*z.core+.25*z.intl;ac=.75*z.corec+.25*z.regc;ic=.75*z.corec+.25*z.intlc;sw=list(z.index[z.sig.ne(z.sig.shift(1))])[1:]
 A=st(a,sw);I=st(i);AC=st(ac,sw);IC=st(ic);A['matched_excess']=A['cagr']-AC['cagr'];I['matched_excess']=I['cagr']-IC['cagr'];D={k:A[k]-I[k] for k in ['cagr','sharpe','max_drawdown','downside_vol']};wins=sum(D[k]>0 for k in ['cagr','sharpe','max_drawdown'])
 return {'regime':A,'intl':I,'regime_control':AC,'intl_control':IC,'regime_vs_intl':D,'wins':wins,'correlation':residual_corr(z)}
full=ev(q);n=len(q);sizes=[n//3,n//3,n-2*(n//3)];blocks=[];o=0
for j,s in enumerate(sizes,1):z=q.iloc[o:o+s];o+=s;blocks.append({'block':j,'result':ev(z)})
wb=sum(x['result']['wins']>=2 for x in blocks);pe=sum(x['result']['regime']['matched_excess']>0 for x in blocks);support=full['wins']>=2 and full['regime']['matched_excess']>0 and wb>=2 and pe>=2
dec='FNDF_VEA_REGIME_ADDS_UTILITY_VS_AVDV_IDMO' if support else 'FNDF_VEA_REGIME_NOT_INCREMENTALLY_SUPERIOR'
out={'schema':'research.p472_exus_regime_vs_intl_sleeve_r2.v1','workload_id':'P472_FNDF_REGIME_VS_AVDV_IDMO_R1','parent':'FUND_MODEL_SURVIVOR_PORTFOLIO','claim':'Same fixed 25% incremental capital beyond frozen P249+P373 core: compare P470 FNDF/VEA weak-dollar regime implementation against confirmed 50/50 AVDV+IDMO return-enhancement sleeve. Includes required downside volatility plus raw and core-residual correlation. No weight/regime tuning.','contract':{'incremental_budget':.25,'regime_signal':'prior completed 12m UUP return < 0 shifted one month','switch_cost_bps':10,'endpoint_cost_bps':25,'chronology_blocks':3,'support':'regime has positive matched excess, beats AVDV+IDMO in >=2 of CAGR/Sharpe/maxDD full sample and >=2/3 blocks, and positive matched excess in >=2/3 blocks','required_evidence':['CAGR','Sharpe','max drawdown','downside volatility','matched excess','return correlation','core-residual correlation']},'coverage':{'months':n,'start':str(q.index[0].date()),'end':str(q.index[-1].date())},'full':full,'blocks':blocks,'regime_win_blocks':wb,'positive_matched_excess_blocks':pe,'decision':dec,'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True);Path('research/artifacts/p472_exus_regime_vs_intl_sleeve_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False));print(json.dumps({'decision':dec,'full':full,'regime_win_blocks':wb,'positive_matched_excess_blocks':pe},sort_keys=True))
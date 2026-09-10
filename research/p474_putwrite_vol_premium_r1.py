from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
T=['PUTW','SPY','BIL'];COST=.0025;LOOKBACK=24;WINDOWS=['2018-01-01','2020-01-01','2022-01-01']
raw=yf.download(T,start='2015-01-01',end='2026-09-11',auto_adjust=True,progress=False,threads=False);c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
availability={t:int(c[t].dropna().shape[0]) if t in c.columns else 0 for t in T};r=c[T].resample('ME').last().pct_change(fill_method=None).dropna();b=[]
for i in range(len(r)):
 z=r[['PUTW','SPY']].iloc[max(0,i-LOOKBACK):i].dropna()
 if len(z)<LOOKBACK:b.append(np.nan);continue
 x=z.SPY.values;y=z.PUTW.values;beta=float(np.cov(x,y,ddof=1)[0,1]/np.var(x,ddof=1));b.append(float(np.clip(beta,0,1)))
beta=pd.Series(b,index=r.index).shift(1);q=pd.DataFrame({'putw':r.PUTW,'spy':r.SPY,'bil':r.BIL,'beta':beta}).dropna();q['control']=q.beta*q.spy+(1-q.beta)*q.bil
def st(s):
 x=s.copy();x.iloc[0]-=COST;x.iloc[-1]-=COST;w=(1+x).cumprod();n=len(x);v=x.std(ddof=1)*math.sqrt(12);return {'months':n,'cagr':float(w.iloc[-1]**(12/n)-1),'sharpe':float(x.mean()*12/v),'max_drawdown':float((w/w.cummax()-1).min())}
def ev(z):
 a=st(z.putw);b=st(z.control);X=np.column_stack([np.ones(len(z)),z.control.values]);coef=np.linalg.lstsq(X,z.putw.values,rcond=None)[0];return {'candidate':a,'control':b,'after_cost_excess_cagr':a['cagr']-b['cagr'],'annualized_intercept':float(coef[0]*12),'median_beta':float(z.beta.median())}
coverage={s:int(len(q.loc[s:])) for s in WINDOWS};ready=all(coverage[s]>=24 for s in WINDOWS)
if ready:
 fixed={s:ev(q.loc[s:]) for s in WINDOWS};z=q.loc['2018-01-01':];n=len(z);sizes=[n//4,n//4,n//4,n-3*(n//4)];blocks=[];o=0
 for j,sz in enumerate(sizes,1):sl=z.iloc[o:o+sz];o+=sz;blocks.append({'block':j,'start':str(sl.index[0].date()),'end':str(sl.index[-1].date()),**ev(sl)})
 posw=sum(x['after_cost_excess_cagr']>0 and x['annualized_intercept']>0 for x in fixed.values());posb=sum(x['after_cost_excess_cagr']>0 for x in blocks);decision='PUTWRITE_VOL_PREMIUM_SUPPORTED' if posw==3 and posb>=3 else 'PUTWRITE_VOL_PREMIUM_NOT_SUPPORTED'
else:
 fixed={};blocks=[];posb=0;decision='PUTWRITE_VOL_PREMIUM_DATA_NOT_READY'
out={'schema':'research.p474_putwrite_vol_premium_r2.v1','workload_id':'P474_PUTWRITE_VOL_PREMIUM_R1','parent':'MATERIALLY_ORTHOGONAL_ALPHA_DISCOVERY','claim':'Independent option-premium architecture: PUTW versus a chronologically causal beta-matched SPY+BIL replication control. R2 only adds fail-closed source coverage classification after R1 crashed on an empty fixed window; it does not alter the hypothesis or thresholds.','contract':{'beta_lookback_months':LOOKBACK,'beta_shift_months':1,'control':'beta*SPY + (1-beta)*BIL','endpoint_cost_bps':25,'fixed_windows':WINDOWS,'minimum_evaluable_months_per_window':24,'chronology_blocks':4,'support':'positive after-cost excess CAGR and positive annualized intercept in all 3 fixed windows plus >=3/4 positive chronology blocks','parameter_grid':False},'source_availability_rows':availability,'evaluable_months':coverage,'fixed_windows':fixed,'chronology':blocks,'decision':decision,'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True);Path('research/artifacts/p474_putwrite_vol_premium_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False));print(json.dumps({'decision':decision,'availability':availability,'evaluable_months':coverage,'fixed':{k:{'excess_pp':round(100*v['after_cost_excess_cagr'],3),'alpha_pp':round(100*v['annualized_intercept'],3)} for k,v in fixed.items()},'positive_blocks':posb},sort_keys=True))
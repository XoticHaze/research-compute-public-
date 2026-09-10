from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
T=['EFV','EFA','FNDF','VEA','UUP']; ENDPOINT=.0025; SWITCH=.001
raw=yf.download(T,start='2008-01-01',end='2026-09-11',auto_adjust=True,progress=False,threads=False); c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
m=c[T].resample('ME').last(); r=m.pct_change(fill_method=None); weak=(m.UUP/m.UUP.shift(12)-1<0).shift(1).astype(float)
def stats(x,cost_switches=None):
 s=x.dropna().copy(); s.iloc[0]-=ENDPOINT;s.iloc[-1]-=ENDPOINT
 if cost_switches is not None:
  for dt in cost_switches:
   if dt in s.index:s.loc[dt]-=SWITCH
 w=(1+s).cumprod();n=len(s);v=s.std(ddof=1)*math.sqrt(12)
 return {'months':n,'cagr':float(w.iloc[-1]**(12/n)-1),'sharpe':float(s.mean()*12/v),'max_drawdown':float((w/w.cummax()-1).min())}
def one(v,b,start=None,end=None):
 z=pd.DataFrame({'v':r[v],'b':r[b],'sig':weak}).dropna()
 if start:z=z.loc[start:]
 if end:z=z.loc[:end]
 strat=z.sig*z.v+(1-z.sig)*z.b; switches=list(z.index[z.sig.ne(z.sig.shift(1))])[1:]
 a=stats(strat,switches);ctl=stats(z.b);ex=a['cagr']-ctl['cagr']
 X=np.column_stack([np.ones(len(z)),z.b.values]);beta=np.linalg.lstsq(X,strat.values,rcond=None)[0];alpha=float(beta[0]*12)
 return {'start':str(z.index[0].date()),'end':str(z.index[-1].date()),'months':len(z),'weak_dollar_fraction':float(z.sig.mean()),'switches':len(switches),'strategy':a,'control':ctl,'after_cost_excess_cagr':ex,'annualized_intercept_vs_control':alpha}
impl={'EFV_EFA':('EFV','EFA'),'FNDF_VEA':('FNDF','VEA')}; windows=['2014-01-01','2018-01-01','2022-01-01']; outw={}; blocks={}; support={}
for k,(v,b) in impl.items():
 outw[k]={s:one(v,b,s) for s in windows}
 z=pd.DataFrame({'v':r[v],'b':r[b],'sig':weak}).dropna().loc['2014-01-01':]; n=len(z); sizes=[n//4,n//4,n//4,n-3*(n//4)]; off=0; bb=[]
 for i,sz in enumerate(sizes,1):
  sl=z.iloc[off:off+sz];off+=sz;bb.append({'block':i,**one(v,b,str(sl.index[0].date()),str(sl.index[-1].date()))})
 blocks[k]=bb
 poswin=sum(outw[k][s]['after_cost_excess_cagr']>0 and outw[k][s]['annualized_intercept_vs_control']>0 for s in windows);posblk=sum(x['after_cost_excess_cagr']>0 for x in bb)
 support[k]={'positive_fixed_windows':poswin,'positive_blocks':posblk,'supported':poswin==3 and posblk>=3}
decision='DOLLAR_REGIME_EXUS_VALUE_SUPPORTED' if all(x['supported'] for x in support.values()) else ('DOLLAR_REGIME_EXUS_VALUE_PARTIAL' if any(x['supported'] for x in support.values()) else 'DOLLAR_REGIME_EXUS_VALUE_NOT_SUPPORTED')
out={'schema':'research.p470_exus_value_dollar_regime_r1.v1','workload_id':'P470_EXUS_VALUE_DOLLAR_REGIME_R1','parent':'DEVELOPED_EXUS_VALUE_FACTOR_ALPHA','claim':'Independent causal regime model after P451: at each month, use value only when the prior completed 12-month UUP total return is negative (weak-dollar regime), otherwise hold the matched broad developed-ex-US control. Economic hypothesis is that cyclical/value exposures benefit when dollar tightening is absent. Fixed before execution; no regime/date/lookback threshold grid.','contract':{'signal':'prior completed 12-month UUP total return < 0, shifted one month','implementations':{'EFV':'EFA','FNDF':'VEA'},'fixed_windows':windows,'chronology_blocks':4,'endpoint_cost_bps':25,'switch_cost_bps':10,'support':'both implementations positive after-cost excess CAGR and positive annualized intercept vs own control in all 3 fixed windows plus >=3/4 positive chronology blocks','no_parameter_grid':True,'no_date_rescue':True,'no_regime_threshold_rescue':True},'fixed_windows':outw,'chronology':blocks,'support':support,'decision':decision,'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True);Path('research/artifacts/p470_exus_value_dollar_regime_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False));print(json.dumps({'decision':decision,'support':support,'windows':{k:{s:{'excess_pp':round(100*x['after_cost_excess_cagr'],3),'alpha_pp':round(100*x['annualized_intercept_vs_control'],3)} for s,x in v.items()} for k,v in outw.items()}},sort_keys=True))
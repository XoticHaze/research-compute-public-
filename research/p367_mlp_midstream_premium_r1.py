from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
FUND='AMLP'; CONTROLS=['XLE','HYG']; ALL=[FUND]+CONTROLS; START='2011-01-01'; END='2026-09-10'; LOOKBACK=24; COST_BP=10
WINDOWS={'2013_plus':'2013-01-01','2018_plus':'2018-01-01','2020_plus':'2020-01-01','2022_plus':'2022-01-01'}
raw=yf.download(ALL,start=START,end=END,auto_adjust=True,progress=False,threads=False); close=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[ALL].dropna(); r=close.resample('ME').last().pct_change().dropna()
def m(q):
 q=pd.Series(q,dtype=float).dropna(); n=len(q)
 if n<2:return {'months':int(n),'cagr':None,'maxdd':None,'sharpe_rf0':None}
 e=(1+q).cumprod(); v=q.std(ddof=1)*math.sqrt(12); return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1),'maxdd':float((e/e.cummax()-1).min()),'sharpe_rf0':float(q.mean()*12/v) if v else None}
fr=r[FUND]; X=r[CONTROLS]; bs=[]
for i in range(len(r)):
 if i<LOOKBACK:bs.append((np.nan,np.nan));continue
 b=np.linalg.lstsq(X.iloc[i-LOOKBACK:i].values,fr.iloc[i-LOOKBACK:i].values,rcond=None)[0]; b=np.clip(b,0,1)
 if b.sum()>1:b=b/b.sum()
 bs.append(tuple(map(float,b)))
b=pd.DataFrame(bs,index=r.index,columns=['b_xle','b_hyg']).shift(1); bench=b.b_xle*r.XLE+b.b_hyg*r.HYG
x=pd.concat([fr.rename('fund'),bench.rename('bench'),r.XLE,r.HYG,b],axis=1).dropna(); f=COST_BP/10000
if len(x):x.iloc[0,x.columns.get_loc('fund')]-=f;x.iloc[-1,x.columns.get_loc('fund')]-=f
rows={}
for name,start in WINDOWS.items():
 q=x.loc[x.index>=pd.Timestamp(start)]; a,c,xm,hm=m(q.fund),m(q.bench),m(q.XLE),m(q.HYG); folds=[]
 for ix in np.array_split(np.arange(len(q)),5):
  z=q.iloc[ix]
  if len(z)>=2:folds.append(m(z.fund)['cagr']-m(z.bench)['cagr'])
 rows[name]={'fund':a,'matched':c,'XLE':xm,'HYG':hm,'matched_excess_cagr':a['cagr']-c['cagr'],'vs_XLE_cagr':a['cagr']-xm['cagr'],'positive_matched_folds':sum(v>0 for v in folds),'fold_excess_cagr':folds,'mean_xle_beta':float(q.b_xle.mean()),'mean_hyg_beta':float(q.b_hyg.mean())}
passes=sum(v['matched_excess_cagr']>0 and v['positive_matched_folds']>=3 for v in rows.values()); dd=all(v['fund']['maxdd']>=v['matched']['maxdd']-0.05 for v in rows.values()); supported=passes==len(WINDOWS) and dd
res={'schema':'research.p367_mlp_midstream_premium_r1','parent':'MLP_MIDSTREAM_PREMIUM','claim':'Independent midstream/MLP fund architecture: fixed AMLP versus causal lagged 24-month XLE+HYG matched control, 10bp endpoint cost, fixed chronology windows; no fund/control/window/cost/beta tuning.','contract':{'fund':FUND,'control':'lagged 24m OLS XLE+HYG clipped [0,1], normalize if sum>1','windows':WINDOWS,'endpoint_cost_bps':COST_BP,'gate':'positive matched excess and >=3/5 positive folds in every window; maxdd no worse by >5pp'},'results':rows,'window_pass_count':passes,'drawdown_guard_pass':dd,'decision':'P367_MLP_MIDSTREAM_PREMIUM_SUPPORTED' if supported else 'P367_MLP_MIDSTREAM_PREMIUM_NOT_SUPPORTED','scientific_consequence':'Pass requires independent midstream representation. Failure rejects this fixed formulation without product/control/date/cost rescue and rotates.','limitations':['AMLP tax structure differs from direct MLP ownership','Yahoo adjusted-price representation','control omits pipeline contract structure and tax effects'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True);Path('research/artifacts/p367_mlp_midstream_premium_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False));print(json.dumps(res,sort_keys=True))

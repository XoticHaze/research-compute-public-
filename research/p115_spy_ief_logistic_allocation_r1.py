from __future__ import annotations
import json,math,hashlib
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
U=['SPY','IEF','HYG','GLD']; COSTS=(10,25,50)
def cg(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1)
def mt(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); v=float(r.std(ddof=1)*math.sqrt(12)); a=float(r.mean()*12); return {'cagr':cg(r),'sharpe_rf0':a/v if v else None,'maxdd':float((e/e.cummax()-1).min())}
def ev(q):
 out={'months':len(q),'controls':{'balanced_50_50':mt(q['balanced']),'spy':mt(q['spy'])},'costs':{}}; ids=np.array_split(np.arange(len(q)),5)
 for bp in COSTS:
  n=q['gross']-q['turn']*bp/10000; m=mt(n); fs=[]
  for j,ix in enumerate(ids,1):
   a=q.iloc[ix]; x=a['gross']-a['turn']*bp/10000; fs.append({'fold':j,'balanced':cg(x)-cg(a['balanced']),'spy':cg(x)-cg(a['spy'])})
  out['costs'][str(bp)]={'candidate':m,'excess_balanced':m['cagr']-out['controls']['balanced_50_50']['cagr'],'excess_spy':m['cagr']-out['controls']['spy']['cagr'],'positive_balanced_folds':sum(x['balanced']>0 for x in fs),'positive_spy_folds':sum(x['spy']>0 for x in fs),'folds':fs}
 return out
def main():
 raw=yf.download(U,start='2004-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna().astype(float); m=raw.resample('ME').last(); r=m.pct_change(); f=pd.DataFrame(index=m.index)
 for s in U:
  f[f'{s}_r3']=m[s].pct_change(3).shift(1); f[f'{s}_r12']=m[s].pct_change(12).shift(1)
 f['spy_vol3']=r['SPY'].rolling(3).std(ddof=1).shift(1)*math.sqrt(12); f['hyg_ief_r3']=(m['HYG']/m['IEF']).pct_change(3).shift(1); f['y']=((r['SPY']-r['IEF'])>0).astype(int); f['spy_ret']=r['SPY']; f['ief_ret']=r['IEF']; f=f.dropna(); cols=[c for c in f.columns if c.endswith('_r3') or c.endswith('_r12')]+['spy_vol3']; preds=[]
 for year in range(2010,int(f.index.year.max())+1):
  tr=f[f.index<pd.Timestamp(f'{year}-01-01')]; te=f[(f.index>=pd.Timestamp(f'{year}-01-01'))&(f.index<pd.Timestamp(f'{year+1}-01-01'))]
  if len(tr)<60 or te.empty: continue
  model=make_pipeline(StandardScaler(),LogisticRegression(C=1.0,max_iter=1000,solver='lbfgs')); model.fit(tr[cols],tr['y']); z=te[['spy_ret','ief_ret']].copy(); z['prob']=model.predict_proba(te[cols])[:,1]; preds.append(z)
 o=pd.concat(preds); choose=(o['prob']>0.5).astype(float); prev=choose.shift(1).fillna(.5); q=pd.DataFrame({'gross':choose*o['spy_ret']+(1-choose)*o['ief_ret'],'turn':(choose-prev).abs(),'balanced':.5*o['spy_ret']+.5*o['ief_ret'],'spy':o['spy_ret'],'choose_spy':choose}).dropna(); tests={k:ev(q.loc[v:]) for k,v in {'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}.items()}; a=tests['2015']['costs']['25']; b=tests['2020']['costs']['25']; ok=a['excess_balanced']>0 and b['excess_balanced']>0 and a['positive_balanced_folds']>=3 and b['positive_balanced_folds']>=3 and b['excess_spy']>0
 out={'schema':'research.p115_spy_ief_logistic_allocation_r1','parent':'P115','hypothesis':'A fixed causal expanding-window classifier using lagged multi-asset state can choose SPY versus IEF monthly and create durable after-cost excess beyond static 50/50 and SPY.','contract':{'assets':U,'model':'StandardScaler + LogisticRegression C=1 lbfgs','features':'lagged 3m/12m returns for SPY IEF HYG GLD plus lagged SPY 3m realized vol and HYG/IEF 3m relative return','target':'next observed monthly SPY return greater than IEF','retrain':'calendar-year expanding window; first OOS 2010','allocation':'100% SPY if P(SPY>IEF)>0.5 else 100% IEF','cost_bps_turnover':list(COSTS),'matched_control':'50/50 SPY/IEF','opportunity_control':'SPY','windows':['2010','2015','2020'],'folds':5,'no_hyperparameter_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_month':str(m.index[-1].date()),'panel_sha256':hashlib.sha256(m.reset_index().to_csv(index=False).encode()).hexdigest()},'tests':tests,'decision':'P115_CROSSASSET_LOGISTIC_SUPPORTED_FOR_FURTHER_FALSIFICATION' if ok else 'P115_CROSSASSET_LOGISTIC_NOT_SUPPORTED'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p115_spy_ief_logistic_allocation_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True,allow_nan=False))
if __name__=='__main__': main()

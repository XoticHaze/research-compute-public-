from __future__ import annotations
import json,math,hashlib
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
COSTS=(1,5,10)
def cg(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(252/len(r))-1)
def mt(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); v=float(r.std(ddof=1)*math.sqrt(252)); a=float(r.mean()*252); return {'cagr':cg(r),'sharpe_rf0':a/v if v else None,'maxdd':float((e/e.cummax()-1).min())}
def ev(q):
 ex=float(q['exp'].mean()); matched=q['spy']*ex; out={'days':len(q),'avg_exposure':ex,'controls':{'exposure_matched_spy':mt(matched),'full_spy':mt(q['spy'])},'costs':{}}; ids=np.array_split(np.arange(len(q)),5)
 for bp in COSTS:
  n=q['gross']-q['turn']*bp/10000; m=mt(n); fs=[]
  for j,ix in enumerate(ids,1):
   a=q.iloc[ix]; x=a['gross']-a['turn']*bp/10000; z=a['spy']*ex; fs.append({'fold':j,'matched':cg(x)-cg(z),'spy':cg(x)-cg(a['spy'])})
  out['costs'][str(bp)]={'candidate':m,'excess_matched':m['cagr']-out['controls']['exposure_matched_spy']['cagr'],'excess_spy':m['cagr']-out['controls']['full_spy']['cagr'],'positive_matched_folds':sum(x['matched']>0 for x in fs),'positive_spy_folds':sum(x['spy']>0 for x in fs),'folds':fs}
 return out
def main():
 p=yf.download('SPY',start='1993-01-01',auto_adjust=True,progress=False,threads=False)['Close']; p=p.iloc[:,0] if isinstance(p,pd.DataFrame) else p; p=p.dropna().astype(float); r=p.pct_change(fill_method=None); f=pd.DataFrame(index=p.index); f['r1']=r.shift(1); f['r5']=p.pct_change(5).shift(1); f['r20']=p.pct_change(20).shift(1); f['vol20']=r.rolling(20).std(ddof=1).shift(1)*math.sqrt(252); f['ma200dist']=(p/p.rolling(200).mean()-1).shift(1); f['y']=(r>0).astype(int); f['ret']=r; f=f.dropna(); preds=[]
 for year in range(2010,int(f.index.year.max())+1):
  tr=f[(f.index<'%d-01-01'%year)]; te=f[(f.index>='%d-01-01'%year)&(f.index<'%d-01-01'%(year+1))]
  if len(tr)<1000 or te.empty: continue
  cols=['r1','r5','r20','vol20','ma200dist']; model=make_pipeline(StandardScaler(),LogisticRegression(C=1.0,max_iter=1000,solver='lbfgs')); model.fit(tr[cols],tr['y']); pr=model.predict_proba(te[cols])[:,1]; x=te[['ret']].copy(); x['prob']=pr; preds.append(x)
 o=pd.concat(preds); exp=(o['prob']>0.5).astype(float); prev=exp.shift(1).fillna(0); q=pd.DataFrame({'gross':exp*o['ret'],'turn':(exp-prev).abs(),'spy':o['ret'],'exp':exp,'prob':o['prob']}).dropna(); tests={k:ev(q.loc[v:]) for k,v in {'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}.items()}; a=tests['2015']['costs']['5']; b=tests['2020']['costs']['5']; ok=a['excess_matched']>0 and b['excess_matched']>0 and a['positive_matched_folds']>=3 and b['positive_matched_folds']>=3
 out={'schema':'research.p114_spy_logistic_walkforward_r1','parent':'P114','hypothesis':'A fixed causal expanding-window logistic model using lagged return, volatility, and trend features creates durable after-cost SPY timing excess beyond identical average capital usage.','contract':{'asset':'SPY','model':'StandardScaler + LogisticRegression C=1 lbfgs','features':['lag1 return','lag5 return','lag20 return','lagged 20d realized vol','lagged distance to 200d SMA'],'target':'same-day close-to-close return positive, predicted only from t-1-known features','retrain':'calendar-year expanding window; first OOS year 2010','decision_rule':'long SPY if P(up)>0.5 else cash','cost_bps_per_position_change':list(COSTS),'matched_control':'continuous SPY scaled to candidate average exposure','opportunity_control':'full SPY','windows':['2010','2015','2020'],'folds':5,'no_hyperparameter_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_date':str(p.index[-1].date()),'series_sha256':hashlib.sha256(p.reset_index().to_csv(index=False).encode()).hexdigest()},'tests':tests,'decision':'P114_SPY_LOGISTIC_WALKFORWARD_SUPPORTED_FOR_FURTHER_FALSIFICATION' if ok else 'P114_SPY_LOGISTIC_WALKFORWARD_NOT_SUPPORTED'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p114_spy_logistic_walkforward_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True,allow_nan=False))
if __name__=='__main__': main()

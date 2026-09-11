from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

TICKERS=['SPY','QQQ','HYG','IEF','GLD','DBC']
START='2007-01-01'; COST_BPS=10.0; MIN_TRAIN=60
FOLDS=[('2012-01-01','2016-12-31'),('2017-01-01','2020-12-31'),('2021-01-01','2026-12-31')]

def cagr(r):
 if len(r)<2:return None
 years=(r.index[-1]-r.index[0]).days/365.25; total=(1+r).prod()
 return float(total**(1/years)-1) if years>0 and total>0 else None

def mdd(r):
 e=(1+r).cumprod(); return float((e/e.cummax()-1).min())

def stats(r): return {'cagr':cagr(r),'max_drawdown':mdd(r),'months':int(len(r)),'vol':float(r.std()*math.sqrt(12))}

def evaluate(df,a,b):
 z=df.loc[a:b]; s=z['strategy']; c=z['control']
 return {'strategy':stats(s),'control':stats(c),'qqq':stats(z['QQQ_ret']),'spy':stats(z['SPY_ret']),'matched_excess_cagr':cagr(s)-cagr(c),'switches':int(z['switch'].sum()),'qqq_weight_mean':float(z['qqq_w'].mean()),'hit_rate':float((z['selected_correct']>0).mean())}

def main():
 px=yf.download(TICKERS,start=START,auto_adjust=True,progress=False,group_by='column')['Close'].dropna()
 m=px.resample('ME').last(); ret=m.pct_change();
 feats=pd.DataFrame(index=m.index)
 for t in TICKERS:
  feats[f'{t}_r1']=ret[t].shift(1)
  feats[f'{t}_r3']=m[t].pct_change(3).shift(1)
  feats[f'{t}_r6']=m[t].pct_change(6).shift(1)
  feats[f'{t}_vol3']=ret[t].rolling(3).std().shift(1)
 target=(ret['QQQ']>ret['SPY']).astype(int)
 rows=[]; prior=None
 valid=feats.dropna().index
 for i,dt in enumerate(valid):
  hist=valid[valid<dt]
  if len(hist)<MIN_TRAIN: continue
  train=pd.DataFrame(feats.loc[hist]).dropna(); y=target.reindex(train.index)
  keep=y.notna(); train=train.loc[keep]; y=y.loc[keep]
  if y.nunique()<2: continue
  sc=StandardScaler(); X=sc.fit_transform(train.values); model=LogisticRegression(C=1.0,solver='lbfgs',max_iter=1000,random_state=0); model.fit(X,y.values)
  p=float(model.predict_proba(sc.transform(feats.loc[[dt]].values))[0,1]); w=1.0 if p>=0.5 else 0.0
  rr=ret.loc[dt]; sw=0.0 if prior is None else abs(w-prior); strat=w*rr['QQQ']+(1-w)*rr['SPY']-sw*(COST_BPS/10000.0); ctrl=0.5*rr['QQQ']+0.5*rr['SPY']; correct=1.0 if (w==1 and rr['QQQ']>rr['SPY']) or (w==0 and rr['SPY']>=rr['QQQ']) else 0.0
  rows.append((dt,strat,ctrl,rr['QQQ'],rr['SPY'],w,sw,correct,p)); prior=w
 d=pd.DataFrame(rows,columns=['date','strategy','control','QQQ_ret','SPY_ret','qqq_w','switch','selected_correct','prob_qqq']).set_index('date')
 overall=evaluate(d,d.index.min().strftime('%Y-%m-%d'),'2026-12-31'); folds=[evaluate(d,a,b) for a,b in FOLDS]; pos=sum(1 for f in folds if f['matched_excess_cagr']>0)
 decision='P543_SUPPORTED' if overall['matched_excess_cagr']>0 and pos>=2 else 'P543_NOT_SUPPORTED'
 out={'schema':'research.p543_cross_asset_walkforward_selector_r1','parent':'P543','claim':'A fixed expanding walk-forward logistic model using only lagged cross-asset return/volatility state can select QQQ versus SPY with durable after-cost excess over a static 50/50 QQQ/SPY control.','frozen_contract':{'universe':TICKERS,'features':'lagged 1m/3m/6m returns and lagged 3m volatility for all six assets','model':'StandardScaler + LogisticRegression(C=1.0, lbfgs, random_state=0)','training':'expanding, minimum 60 completed months, refit monthly','threshold':0.5,'cost_bps_per_switch':COST_BPS,'control':'static 50/50 QQQ/SPY','folds':FOLDS,'no_hyperparameter_search':True},'overall':overall,'folds':folds,'positive_fold_count':pos,'decision':decision,'oos_months':int(len(d)),'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
 Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p543_cross_asset_walkforward_selector_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()

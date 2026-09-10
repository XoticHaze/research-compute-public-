from __future__ import annotations

import json, math
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
import yfinance as yf

BASE="https://publicreporting.cftc.gov/resource/gpe5-46if.json"
CODES={"ES":"13874A","NQ":"209742"}
START="2010-01-01"
COST=0.001
RIDGE=1.0
MIN_TRAIN=104
WINDOWS={"all":"2012-01-01","recent":"2020-01-01"}


def fetch(code):
 q=urlencode({"$where":f"cftc_contract_market_code='{code}' AND report_date_as_yyyy_mm_dd >= '{START}T00:00:00.000'","$order":"report_date_as_yyyy_mm_dd ASC","$limit":"5000"})
 req=Request(BASE+'?'+q,headers={"User-Agent":"XoticHaze-Research/1.0"})
 with urlopen(req,timeout=45) as r: rows=json.loads(r.read().decode())
 out=[]
 for z in rows:
  oi=float(z['open_interest_all']); d=pd.Timestamp(z['report_date_as_yyyy_mm_dd']).tz_localize(None)
  out.append((d,(float(z['asset_mgr_positions_long'])-float(z['asset_mgr_positions_short']))/oi,(float(z['lev_money_positions_long'])-float(z['lev_money_positions_short']))/oi))
 return pd.DataFrame(out,columns=['report_date','am','lm']).drop_duplicates('report_date').set_index('report_date')


def metrics(r):
 q=pd.Series(r,dtype=float).dropna(); n=len(q)
 if not n:return {'weeks':0,'cagr':0.0,'maxdd':0.0,'sharpe_rf0':None,'turnover':None}
 e=(1+q).cumprod(); vol=float(q.std(ddof=1)*math.sqrt(52)) if n>1 else None; ann=float(q.mean()*52) if n>1 else None
 return {'weeks':n,'cagr':float(e.iloc[-1]**(52/n)-1),'maxdd':float((e/e.cummax()-1).min()),'sharpe_rf0':float(ann/vol) if vol else None}


def ridge_pred(X,y,x):
 X=np.asarray(X,float); y=np.asarray(y,float); x=np.asarray(x,float); mu=X.mean(0); sd=X.std(0); sd[sd<1e-12]=1
 Z=(X-mu)/sd; zx=(x-mu)/sd; A=np.column_stack([np.ones(len(Z)),Z]); p=np.eye(A.shape[1]); p[0,0]=0
 b=np.linalg.solve(A.T@A+RIDGE*p,A.T@y); return float(np.r_[1,zx]@b)


def causal_permutation(pos):
 a=np.asarray(pos,float); out=np.full_like(a,np.nan)
 for i in range(1,len(a)):
  j=(i*37+11)%i; out[i]=a[j]
 return out


def arm_metrics(df, pred_col):
 q=df.dropna(subset=[pred_col,'qqq_fwd','spy_fwd']).copy(); choose=(q[pred_col]>0).astype(int); gross=np.where(choose.to_numpy()==1,q.qqq_fwd,q.spy_fwd); turn=choose.ne(choose.shift()).astype(float); turn.iloc[0]=1.0; net=pd.Series(gross,index=q.index)-COST*turn
 bench=.5*q.qqq_fwd+.5*q.spy_fwd
 m=metrics(net); bm=metrics(bench); sp=metrics(q.spy_fwd); qq=metrics(q.qqq_fwd)
 m.update({'matched_excess_cagr':m['cagr']-bm['cagr'],'vs_spy_cagr':m['cagr']-sp['cagr'],'vs_qqq_cagr':m['cagr']-qq['cagr'],'switch_fraction':float(turn.mean()),'benchmark_cagr':bm['cagr']})
 return m,net


def fold_delta(a,b):
 n=len(a); out=[]
 for k,ix in enumerate(np.array_split(np.arange(n),5),1):
  aa=metrics(a.iloc[ix]); bb=metrics(b.iloc[ix]); out.append({'fold':k,'cagr_delta':aa['cagr']-bb['cagr']})
 return out

es=fetch(CODES['ES']).rename(columns={'am':'es_am','lm':'es_lm'}); nq=fetch(CODES['NQ']).rename(columns={'am':'nq_am','lm':'nq_lm'}); cot=es.join(nq,how='inner').sort_index()
cot['release_date']=cot.index+pd.Timedelta(days=3); cot['am_diff']=cot.nq_am-cot.es_am; cot['lm_diff']=cot.nq_lm-cot.es_lm; cot['am_chg13']=cot.am_diff-cot.am_diff.shift(13); cot['lm_chg13']=cot.lm_diff-cot.lm_diff.shift(13)
raw=yf.download(['QQQ','SPY'],start=START,end=(pd.Timestamp.utcnow()+pd.Timedelta(days=1)).date().isoformat(),auto_adjust=True,progress=False,threads=False); close=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw; close=close[['QQQ','SPY']].dropna()
rows=[]
for dt,z in cot.iterrows():
 ix=close.index.searchsorted(z.release_date)
 if ix>=len(close):continue
 pxdt=close.index[ix]; rows.append((dt,pxdt,z.am_diff,z.lm_diff,z.am_chg13,z.lm_chg13,float(close.loc[pxdt,'QQQ']),float(close.loc[pxdt,'SPY'])))
d=pd.DataFrame(rows,columns=['report_date','signal_date','am_diff','lm_diff','am_chg13','lm_chg13','qqq','spy']).drop_duplicates('signal_date').set_index('signal_date').sort_index(); rel=d.qqq/d.spy; d['rel4']=rel.pct_change(4); d['rel13']=rel.pct_change(13); d['qqq_fwd']=d.qqq.shift(-1)/d.qqq-1; d['spy_fwd']=d.spy.shift(-1)/d.spy-1; d['target']=d.qqq_fwd-d.spy_fwd
poscols=['am_diff','lm_diff','am_chg13','lm_chg13']; pricecols=['rel4','rel13']; perm=causal_permutation(d[poscols].to_numpy()); preds={'price':[],'positioning':[],'combined':[],'permuted':[]}
for i in range(len(d)):
 train=d.iloc[:i].dropna(subset=pricecols+poscols+['target'])
 if len(train)<MIN_TRAIN or d.iloc[i][pricecols+poscols].isna().any():
  for k in preds:preds[k].append(np.nan)
  continue
 y=train.target.to_numpy(); xrow=d.iloc[i]
 preds['price'].append(ridge_pred(train[pricecols],y,xrow[pricecols]))
 preds['positioning'].append(ridge_pred(train[poscols],y,xrow[poscols]))
 preds['combined'].append(ridge_pred(train[pricecols+poscols],y,xrow[pricecols+poscols]))
 train_ix=d.index.get_indexer(train.index); pp=perm[train_ix]; good=np.isfinite(pp).all(1); Xp=np.column_stack([train[pricecols].to_numpy()[good],pp[good]]); yp=y[good]; xp=np.r_[xrow[pricecols].to_numpy(float),perm[i]]
 preds['permuted'].append(ridge_pred(Xp,yp,xp) if len(yp)>=MIN_TRAIN and np.isfinite(xp).all() else np.nan)
for k,v in preds.items():d[k+'_pred']=v
results={}
for wn,start in WINDOWS.items():
 q=d.loc[d.index>=pd.Timestamp(start)].dropna(subset=['combined_pred','price_pred','positioning_pred','permuted_pred','qqq_fwd','spy_fwd']).copy(); arms={}; nets={}
 for k in preds:arms[k],nets[k]=arm_metrics(q,k+'_pred')
 fcp=fold_delta(nets['combined'],nets['price']); fperm=fold_delta(nets['combined'],nets['permuted'])
 results[wn]={'start':start,'end':q.index.max().date().isoformat() if len(q) else None,'observations':len(q),'arms':arms,'combined_minus_price_folds':fcp,'combined_minus_permuted_folds':fperm,'positive_combined_minus_price_folds':sum(x['cagr_delta']>0 for x in fcp),'positive_combined_minus_permuted_folds':sum(x['cagr_delta']>0 for x in fperm)}
a=results['all']; r=results['recent']; gate=(a['arms']['combined']['matched_excess_cagr']>0 and r['arms']['combined']['matched_excess_cagr']>0 and a['arms']['combined']['cagr']>a['arms']['price']['cagr'] and r['arms']['combined']['cagr']>r['arms']['price']['cagr'] and a['positive_combined_minus_price_folds']>=3 and r['positive_combined_minus_price_folds']>=3 and a['arms']['combined']['cagr']>a['arms']['permuted']['cagr'] and r['arms']['combined']['cagr']>r['arms']['permuted']['cagr'] and a['positive_combined_minus_permuted_folds']>=3)
out={'schema':'research.p282_cftc_relative_alpha_r1','parent':'P281/P282','claim':'Test whether causally lagged NQ-versus-ES TFF positioning adds incremental information to a fixed QQQ-versus-SPY relative-selection model beyond price state alone.','contract':{'target':'next COT-to-COT QQQ minus SPY return','price_features':['4-week QQQ/SPY relative return','13-week QQQ/SPY relative return'],'positioning_features':['NQ-ES asset-manager net/OI','NQ-ES leveraged-money net/OI','13-week change of each'],'models':'expanding fixed ridge lambda=1; minimum 104 training weeks','arms':['PRICE_STATE_CONTROL','POSITIONING_ONLY','PRICE_PLUS_POSITIONING','CAUSAL_PERMUTED_POSITIONING_NEGATIVE_CONTROL'],'decision_rule':'choose QQQ when predicted relative return >0 else SPY','switch_cost_bps':10,'publication_lag':'Tuesday COT observation available no earlier than Friday; signal price is first market close on/after Friday release','windows':WINDOWS,'gate':'combined positive matched excess in both windows, beats price control in both with >=3/5 positive chronology folds, and beats permuted control in both without parameter search','no_feature_window_lambda_threshold_or_cost_search':True},'source':{'dataset':'gpe5-46if','ES_code':CODES['ES'],'NQ_code':CODES['NQ'],'source_admission_run':34451989568,'source_admission_artifact':10141899576},'tests':results,'decision':'P282_CFTC_POSITIONING_INCREMENTAL_EVIDENCE' if gate else 'P282_CFTC_POSITIONING_NOT_INCREMENTAL','limitations':['Yahoo adjusted ETF prices are research-only','COT release-date rule uses the standard Friday publication schedule','This is a relative QQQ/SPY consumer and does not establish ticker-level alpha'],'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('artifacts').mkdir(exist_ok=True);Path('artifacts/p282_cftc_relative_alpha_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False));print(json.dumps(out,sort_keys=True))

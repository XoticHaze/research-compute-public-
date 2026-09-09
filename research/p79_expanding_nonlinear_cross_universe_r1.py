from __future__ import annotations
import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
from sklearn.ensemble import RandomForestRegressor

ASSETS=('SPY','QQQ','TLT','GLD','DBC','SOXX','XBI','XHB','KRE','ITA','IGV','IYT','XRT','XOP','IHI'); FEATURES=('mom6','trend200','low_vol6','drawdown6'); TOP=3; MIN_TRAIN=60; COSTS=(25,50); SEED=790079

def metric(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); y=len(r)/12; c=float(e.iloc[-1]**(1/y)-1); a=float(r.mean()*12); v=float(r.std(ddof=0)*math.sqrt(12)); d=e/e.cummax()-1; m=float(d.min()); return {'cagr':c,'annualized_vol':v,'sharpe_rf0':a/v if v else float('nan'),'max_drawdown_monthly':m}
def folds(c,b):
 z=[]
 for idx in np.array_split(np.arange(len(c)),5): z.append(metric(c.iloc[idx])['cagr']-metric(b.iloc[idx])['cagr'])
 return int(sum(x>0 for x in z)),z
def main():
 data=yf.download(list(ASSETS),start='2005-01-01',auto_adjust=True,progress=False,threads=False); close=data['Close'] if isinstance(data.columns,pd.MultiIndex) else data[['Close']]; close=close.loc[:,list(ASSETS)].astype(float); end=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp('M'); close_m=close.resample('ME').last(); close_m=close_m.loc[close_m.index<end]; dr=close.pct_change(fill_method=None); vol=(dr.rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last().reindex(close_m.index); trend=(close/close.rolling(200,min_periods=160).mean()-1).resample('ME').last().reindex(close_m.index); dd=(close/close.rolling(126,min_periods=100).max()-1).resample('ME').last().reindex(close_m.index); mom=close_m.pct_change(6); fmap={}; tmap={}
 for i,dt in enumerate(close_m.index[:-1]):
  nxt=close_m.index[i+1]; raw=pd.DataFrame({'mom6':mom.loc[dt],'trend200':trend.loc[dt],'low_vol6':-vol.loc[dt],'drawdown6':dd.loc[dt]}); target=close_m.loc[nxt]/close_m.loc[dt]-1
  if raw.isna().any().any() or target.isna().any(): continue
  fmap[dt]=raw.rank(axis=0,pct=True,method='average'); tmap[dt]=target.astype(float)
 months=sorted(fmap); prev={s:0.0 for s in ASSETS}; rec=[]
 for j in range(MIN_TRAIN,len(months)):
  dt=months[j]; xs=[]; ys=[]
  for tm in months[:j]: xs.append(fmap[tm].loc[:,list(FEATURES)].to_numpy()); y=tmap[tm].to_numpy(); ys.append(y-y.mean())
  model=RandomForestRegressor(n_estimators=160,max_depth=3,min_samples_leaf=20,max_features=None,random_state=SEED,n_jobs=-1); model.fit(np.vstack(xs),np.concatenate(ys)); pred=model.predict(fmap[dt].loc[:,list(FEATURES)].to_numpy()); picks=[ASSETS[i] for i in np.argsort(-pred)[:TOP]]; fixed=fmap[dt].loc[:,list(FEATURES)].mean(axis=1).sort_values(ascending=False,kind='stable').head(TOP).index.tolist(); w={s:(1/TOP if s in picks else 0.0) for s in ASSETS}; wf={s:(1/TOP if s in fixed else 0.0) for s in ASSETS}; turn=.5*sum(abs(w[s]-prev[s]) for s in ASSETS); r=tmap[dt]; rec.append({'return_month':str(close_m.index[close_m.index.get_loc(dt)+1].date()),'gross':sum(w[s]*r[s] for s in ASSETS),'fixed':sum(wf[s]*r[s] for s in ASSETS),'ew':float(r.mean()),'qqq':float(r['QQQ']),'spy':float(r['SPY']),'turnover':turn}); prev=w
 fr=pd.DataFrame(rec); sha=hashlib.sha256(close_m.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest(); out={'schema':'research.p79_expanding_nonlinear_cross_universe_r1','parent':'P70','hypothesis':'A conservative nonlinear expanding model can extract cross-sectional interactions from the same P70 feature-target stack even though the frozen linear ridge failed.','scientific_contract':{'assets':list(ASSETS),'features':list(FEATURES),'target':'next-month cross-sectional demeaned return','model':'RandomForestRegressor','frozen_model':{'n_estimators':160,'max_depth':3,'min_samples_leaf':20,'max_features':None,'random_state':SEED},'minimum_training_months':MIN_TRAIN,'top_k':TOP,'costs_bps':list(COSTS),'comparators':['same-universe fixed equal-factor top3','same-universe equal weight','QQQ','SPY'],'incomplete_months_excluded':True,'no_hyperparameter_search':True},'source':{'provider':'Yahoo Finance via yfinance','complete_month_panel_sha256':sha},'oos_window':{'start':fr.iloc[0].return_month,'end':fr.iloc[-1].return_month,'months':int(len(fr))},'mean_annual_turnover':float(fr.turnover.mean()*12),'costs':{}}
 for bp in COSTS:
  c=fr.gross-fr.turnover*bp/10000; cm,fm,em,qm,sm=map(metric,(c,fr.fixed,fr.ew,fr.qqq,fr.spy)); pf,_=folds(c,fr.fixed); pe,_=folds(c,fr.ew); out['costs'][str(bp)]={'candidate':cm,'fixed_composite':fm,'equal_weight':em,'qqq':qm,'spy':sm,'excess_cagr_vs_fixed':cm['cagr']-fm['cagr'],'excess_cagr_vs_equal_weight':cm['cagr']-em['cagr'],'excess_cagr_vs_qqq':cm['cagr']-qm['cagr'],'excess_cagr_vs_spy':cm['cagr']-sm['cagr'],'positive_folds_vs_fixed':pf,'positive_folds_vs_equal_weight':pe}
 p,s=out['costs']['25'],out['costs']['50']; out['decision']='SUPPORTED_NONLINEAR_CROSS_UNIVERSE_CANDIDATE' if p['excess_cagr_vs_fixed']>0 and p['excess_cagr_vs_equal_weight']>.01 and p['positive_folds_vs_equal_weight']>=3 and s['excess_cagr_vs_equal_weight']>0 else 'NOT_SUPPORTED_NONLINEAR_CROSS_UNIVERSE_ROTATE'; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p79_expanding_nonlinear_cross_universe_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'oos':out['oos_window'],'turnover':out['mean_annual_turnover'],'25':{k:p[k] for k in ('excess_cagr_vs_fixed','excess_cagr_vs_equal_weight','excess_cagr_vs_qqq','excess_cagr_vs_spy','positive_folds_vs_fixed','positive_folds_vs_equal_weight')},'50':{k:s[k] for k in ('excess_cagr_vs_fixed','excess_cagr_vs_equal_weight','excess_cagr_vs_qqq','excess_cagr_vs_spy')}},sort_keys=True))
if __name__=='__main__': main()

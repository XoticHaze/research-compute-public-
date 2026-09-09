from __future__ import annotations
import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
SYMS=("SMH","XBI","ITB","KRE","ITA","IGV","IWM","XRT"); REQ=(*SYMS,"SPY","QQQ"); START="2006-01-01"
def metrics(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); y=len(r)/12; c=float(e.iloc[-1]**(1/y)-1); a=float(r.mean()*12); v=float(r.std(ddof=0)*math.sqrt(12)); d=e/e.cummax()-1; m=float(d.min()); return {'cagr':c,'annualized_mean':a,'annualized_vol':v,'sharpe_rf0':a/v if v else float('nan'),'max_drawdown_monthly':m,'calmar':c/abs(m) if m<0 else float('nan')}
def folds(c,b):
 out=[]
 for n,idx in enumerate(np.array_split(np.arange(len(c)),5),1):
  x,y=metrics(c.iloc[idx]),metrics(b.iloc[idx]); out.append({'fold':n,'excess_cagr':x['cagr']-y['cagr']})
 return sum(z['excess_cagr']>0 for z in out),out
def main():
 d=yf.download(list(REQ),start=START,auto_adjust=True,progress=False,threads=False); close=d['Close'] if isinstance(d.columns,pd.MultiIndex) else d[['Close']]; close=close.loc[:,list(REQ)].dropna(how='all').astype(float); monthly=close.resample('ME').last(); last=pd.Timestamp(close.index.max()); last=last.tz_localize(None) if last.tzinfo is not None else last; monthly=monthly.loc[monthly.index<=last.normalize()]; dr=close.pct_change(); rows=[]; prev={s:0. for s in SYMS}
 for month in monthly.index:
  loc=monthly.index.get_loc(month)
  if not isinstance(loc,(int,np.integer)) or loc+1>=len(monthly): continue
  daily=dr.loc[:month].tail(252)
  if len(daily)<200 or daily[list(REQ)].isna().any().any(): continue
  mkt=daily['SPY']; mv=float(mkt.var(ddof=0))
  if mv<=0: continue
  score={}
  for s in SYMS:
   beta=float(((daily[s]-daily[s].mean())*(mkt-mkt.mean())).mean()/mv); r6=float(monthly.at[month,s]/monthly.iloc[max(0,loc-6)][s]-1) if loc>=6 else float('nan'); m6=float(monthly.at[month,'SPY']/monthly.iloc[loc-6]['SPY']-1) if loc>=6 else float('nan'); score[s]=r6-beta*m6
  if any(pd.isna(v) for v in score.values()): continue
  chosen=sorted(SYMS,key=lambda s:(score[s],s),reverse=True)[:3]; nxt=monthly.index[loc+1]; realized=monthly.loc[nxt,list(REQ)]/monthly.loc[month,list(REQ)]-1
  if realized.isna().any(): continue
  w={s:(1/3 if s in chosen else 0.) for s in SYMS}; to=.5*sum(abs(w[s]-prev[s]) for s in SYMS); rows.append({'date':nxt,'gross':sum(w[s]*float(realized[s]) for s in SYMS),'turnover':to,'ew':float(realized.loc[list(SYMS)].mean()),'spy':float(realized.SPY),'qqq':float(realized.QQQ)}); prev=w
 f=pd.DataFrame(rows).set_index('date'); costs={}
 for bps in (25,50):
  c=f.gross-f.turnover*bps/10000; cm,bm=metrics(c),metrics(f.ew); p,fs=folds(c,f.ew); costs[str(bps)]={'candidate':cm,'matched_equal_weight':bm,'spy':metrics(f.spy),'qqq':metrics(f.qqq),'excess_cagr_vs_equal_weight':cm['cagr']-bm['cagr'],'excess_cagr_vs_spy':cm['cagr']-metrics(f.spy)['cagr'],'excess_cagr_vs_qqq':cm['cagr']-metrics(f.qqq)['cagr'],'positive_folds_vs_equal_weight':p,'folds':fs}
 p25,p50=costs['25'],costs['50']; ok=p25['excess_cagr_vs_equal_weight']>.01 and p25['positive_folds_vs_equal_weight']>=3 and p25['candidate']['sharpe_rf0']>=p25['matched_equal_weight']['sharpe_rf0'] and p50['excess_cagr_vs_equal_weight']>0
 out={'schema':'research.p84_industry_residual_momentum_r1','scientific_contract':{'mechanism':'daily trailing-252d beta to SPY; rank eight industries by six-month return minus beta times SPY six-month return; top3 monthly','comparators':['same-universe equal weight','SPY','QQQ'],'costs_bps':[25,50],'no_parameter_tuning':True,'complete_months_only':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_panel_sha256':hashlib.sha256(close.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()},'window':{'start':str(f.index.min().date()),'end':str(f.index.max().date()),'months':len(f)},'mean_annual_turnover':float(f.turnover.mean()*12),'costs':costs,'decision':'SUPPORTED_RESIDUAL_MOMENTUM_REQUIRES_VALIDATION' if ok else 'NOT_SUPPORTED_RESIDUAL_MOMENTUM_ROTATE'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p84_industry_residual_momentum_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'window':out['window'],'25':{'excess_vs_ew':p25['excess_cagr_vs_equal_weight'],'excess_vs_spy':p25['excess_cagr_vs_spy'],'excess_vs_qqq':p25['excess_cagr_vs_qqq'],'folds':p25['positive_folds_vs_equal_weight']},'50':{'excess_vs_ew':p50['excess_cagr_vs_equal_weight']},'turnover':out['mean_annual_turnover']},sort_keys=True))
if __name__=='__main__': main()

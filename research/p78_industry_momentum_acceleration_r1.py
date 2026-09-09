from __future__ import annotations
import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf

ASSETS=('SOXX','XBI','XHB','KRE','ITA','IGV','IYT','XRT','XOP','IHI'); CONTROLS=('QQQ','SPY'); COSTS=(25,50); TOP=3

def metric(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); y=len(r)/12; c=float(e.iloc[-1]**(1/y)-1); a=float(r.mean()*12); v=float(r.std(ddof=0)*math.sqrt(12)); d=e/e.cummax()-1; m=float(d.min()); return {'cagr':c,'annualized_vol':v,'sharpe_rf0':a/v if v else float('nan'),'max_drawdown_monthly':m,'calmar':c/abs(m) if m<0 else float('nan')}
def folds(c,b):
 z=[]
 for n,idx in enumerate(np.array_split(np.arange(len(c)),5),1):
  cm,bm=metric(c.iloc[idx]),metric(b.iloc[idx]); z.append({'fold':n,'excess_cagr':cm['cagr']-bm['cagr']})
 return int(sum(x['excess_cagr']>0 for x in z)),z
def main():
 syms=list(ASSETS+CONTROLS); data=yf.download(syms,start='2005-01-01',auto_adjust=True,progress=False,threads=False); close=data['Close'] if isinstance(data.columns,pd.MultiIndex) else data[['Close']]; close=close.loc[:,syms].astype(float); end=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp('M'); m=close.resample('ME').last(); m=m.loc[m.index<end]; sha=hashlib.sha256(m.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest(); r3=m[list(ASSETS)].pct_change(3); prior3=m[list(ASSETS)].shift(3)/m[list(ASSETS)].shift(6)-1; accel=r3-prior3; rec=[]; prev={s:0.0 for s in ASSETS}
 for i,dt in enumerate(m.index[:-1]):
  nxt=m.index[i+1]
  if accel.loc[dt].isna().any() or m.loc[[dt,nxt],syms].isna().any().any(): continue
  picks=accel.loc[dt].sort_values(ascending=False,kind='stable').head(TOP).index.tolist(); w={s:(1/TOP if s in picks else 0.0) for s in ASSETS}; turn=.5*sum(abs(w[s]-prev[s]) for s in ASSETS); rets=m.loc[nxt,list(ASSETS)]/m.loc[dt,list(ASSETS)]-1; gross=float(sum(w[s]*rets[s] for s in ASSETS)); ew=float(rets.mean()); q=float(m.at[nxt,'QQQ']/m.at[dt,'QQQ']-1); spy=float(m.at[nxt,'SPY']/m.at[dt,'SPY']-1); rec.append({'return_month':str(nxt.date()),'gross':gross,'ew':ew,'qqq':q,'spy':spy,'turnover':turn,'picks':picks}); prev=w
 fr=pd.DataFrame(rec); out={'schema':'research.p78_industry_momentum_acceleration_r1','hypothesis':'Cross-sectional acceleration, defined as recent 3-month return minus the immediately preceding 3-month return, identifies industries entering stronger opportunity states and creates after-cost excess versus the same-universe equal-weight control.','scientific_contract':{'assets':list(ASSETS),'score':'3m return minus preceding 3m return','top_k':TOP,'rebalance':'monthly after complete month-end signal','costs_bps':list(COSTS),'matched_control':'same-universe equal weight exact months','opportunity_controls':['QQQ','SPY'],'incomplete_months_excluded':True,'no_lookback_topk_threshold_or_weight_tuning':True},'source':{'provider':'Yahoo Finance via yfinance','complete_month_panel_sha256':sha},'window':{'start':fr.iloc[0].return_month,'end':fr.iloc[-1].return_month,'months':int(len(fr))},'mean_annual_turnover':float(fr.turnover.mean()*12),'costs':{}}
 for bp in COSTS:
  c=fr.gross-fr.turnover*bp/10000; cm,em,qm,sm=metric(c),metric(fr.ew),metric(fr.qqq),metric(fr.spy); pos,fs=folds(c,fr.ew); out['costs'][str(bp)]={'candidate':cm,'equal_weight':em,'qqq':qm,'spy':sm,'excess_cagr_vs_equal_weight':cm['cagr']-em['cagr'],'excess_cagr_vs_qqq':cm['cagr']-qm['cagr'],'excess_cagr_vs_spy':cm['cagr']-sm['cagr'],'positive_folds_vs_equal_weight':pos,'folds_vs_equal_weight':fs}
 p,s=out['costs']['25'],out['costs']['50']; out['decision']='SUPPORTED_INDUSTRY_ACCELERATION_CANDIDATE' if p['excess_cagr_vs_equal_weight']>.01 and p['positive_folds_vs_equal_weight']>=3 and s['excess_cagr_vs_equal_weight']>0 else 'NOT_SUPPORTED_INDUSTRY_ACCELERATION_ROTATE'; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p78_industry_momentum_acceleration_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'window':out['window'],'turnover':out['mean_annual_turnover'],'25':{k:p[k] for k in ('excess_cagr_vs_equal_weight','excess_cagr_vs_qqq','excess_cagr_vs_spy','positive_folds_vs_equal_weight')},'50':{k:s[k] for k in ('excess_cagr_vs_equal_weight','excess_cagr_vs_qqq','excess_cagr_vs_spy')}},sort_keys=True))
if __name__=='__main__': main()

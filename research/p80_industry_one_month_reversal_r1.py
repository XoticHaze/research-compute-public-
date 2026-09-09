from __future__ import annotations
import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
ASSETS=('SOXX','XBI','XHB','KRE','ITA','IGV','IYT','XRT','XOP','IHI'); COSTS=(25,50); TOP=3
def metric(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); y=len(r)/12; c=float(e.iloc[-1]**(1/y)-1); a=float(r.mean()*12); v=float(r.std(ddof=0)*math.sqrt(12)); d=e/e.cummax()-1; m=float(d.min()); return {'cagr':c,'annualized_vol':v,'sharpe_rf0':a/v if v else float('nan'),'max_drawdown_monthly':m}
def folds(c,b):
 z=[]
 for idx in np.array_split(np.arange(len(c)),5): z.append(metric(c.iloc[idx])['cagr']-metric(b.iloc[idx])['cagr'])
 return int(sum(x>0 for x in z)),z
def main():
 syms=list(ASSETS)+['QQQ','SPY']; data=yf.download(syms,start='2005-01-01',auto_adjust=True,progress=False,threads=False); close=data['Close'] if isinstance(data.columns,pd.MultiIndex) else data[['Close']]; close=close.loc[:,syms].astype(float); end=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp('M'); m=close.resample('ME').last(); m=m.loc[m.index<end]; r1=m[list(ASSETS)].pct_change(1); sha=hashlib.sha256(m.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest(); rec=[]; prev={s:0.0 for s in ASSETS}
 for i,dt in enumerate(m.index[:-1]):
  nxt=m.index[i+1]
  if r1.loc[dt].isna().any() or m.loc[[dt,nxt],syms].isna().any().any(): continue
  picks=r1.loc[dt].sort_values(ascending=True,kind='stable').head(TOP).index.tolist(); w={s:(1/TOP if s in picks else 0.0) for s in ASSETS}; turn=.5*sum(abs(w[s]-prev[s]) for s in ASSETS); rets=m.loc[nxt,list(ASSETS)]/m.loc[dt,list(ASSETS)]-1; rec.append({'return_month':str(nxt.date()),'gross':sum(w[s]*rets[s] for s in ASSETS),'ew':float(rets.mean()),'qqq':float(m.at[nxt,'QQQ']/m.at[dt,'QQQ']-1),'spy':float(m.at[nxt,'SPY']/m.at[dt,'SPY']-1),'turnover':turn}); prev=w
 fr=pd.DataFrame(rec); out={'schema':'research.p80_industry_one_month_reversal_r1','hypothesis':'Short-horizon cross-sectional reversal across industry ETFs creates after-cost excess by selecting the three prior-month laggards.','scientific_contract':{'assets':list(ASSETS),'signal':'prior complete month return ascending','top_k':TOP,'costs_bps':list(COSTS),'matched_control':'same-universe equal weight','opportunity_controls':['QQQ','SPY'],'incomplete_months_excluded':True,'no_lookback_topk_or_weight_tuning':True},'source':{'provider':'Yahoo Finance via yfinance','complete_month_panel_sha256':sha},'window':{'start':fr.iloc[0].return_month,'end':fr.iloc[-1].return_month,'months':int(len(fr))},'mean_annual_turnover':float(fr.turnover.mean()*12),'costs':{}}
 for bp in COSTS:
  c=fr.gross-fr.turnover*bp/10000; cm,em,qm,sm=metric(c),metric(fr.ew),metric(fr.qqq),metric(fr.spy); pos,_=folds(c,fr.ew); out['costs'][str(bp)]={'candidate':cm,'equal_weight':em,'qqq':qm,'spy':sm,'excess_cagr_vs_equal_weight':cm['cagr']-em['cagr'],'excess_cagr_vs_qqq':cm['cagr']-qm['cagr'],'excess_cagr_vs_spy':cm['cagr']-sm['cagr'],'positive_folds_vs_equal_weight':pos}
 p,s=out['costs']['25'],out['costs']['50']; out['decision']='SUPPORTED_INDUSTRY_REVERSAL_CANDIDATE' if p['excess_cagr_vs_equal_weight']>.01 and p['positive_folds_vs_equal_weight']>=3 and s['excess_cagr_vs_equal_weight']>0 else 'NOT_SUPPORTED_INDUSTRY_REVERSAL_ROTATE'; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p80_industry_one_month_reversal_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'window':out['window'],'turnover':out['mean_annual_turnover'],'25':{k:p[k] for k in ('excess_cagr_vs_equal_weight','excess_cagr_vs_qqq','excess_cagr_vs_spy','positive_folds_vs_equal_weight')},'50':{k:s[k] for k in ('excess_cagr_vs_equal_weight','excess_cagr_vs_qqq','excess_cagr_vs_spy')}},sort_keys=True))
if __name__=='__main__': main()

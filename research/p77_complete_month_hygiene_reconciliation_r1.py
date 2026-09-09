from __future__ import annotations
import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf

COSTS=(25,50)

def metric(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); y=len(r)/12; c=float(e.iloc[-1]**(1/y)-1); a=float(r.mean()*12); v=float(r.std(ddof=0)*math.sqrt(12)); d=e/e.cummax()-1; m=float(d.min()); return {'cagr':c,'annualized_vol':v,'sharpe_rf0':a/v if v else float('nan'),'max_drawdown_monthly':m}
def folds(c,b):
 z=[]
 for idx in np.array_split(np.arange(len(c)),5): z.append(metric(c.iloc[idx])['cagr']-metric(b.iloc[idx])['cagr'])
 return int(sum(x>0 for x in z))
def eval_timer(fr):
 avg=float(fr.exp.mean()); matched=avg*fr.qqq+(1-avg)*fr.shy; out={}
 for bp in COSTS:
  c=fr.gross-fr.turnover*bp/10000; out[str(bp)]={'excess_cagr_vs_matched':metric(c)['cagr']-metric(matched)['cagr'],'excess_cagr_vs_qqq':metric(c)['cagr']-metric(fr.qqq)['cagr'],'excess_cagr_vs_spy':metric(c)['cagr']-metric(fr.spy)['cagr'],'positive_folds_vs_matched':folds(c,matched)}
 return {'months':int(len(fr)),'end':str(fr.iloc[-1].return_month),'mean_qqq_exposure':avg,'mean_annual_turnover':float(fr.turnover.mean()*12),'costs':out}
def main():
 syms=['SOXX','XBI','XHB','KRE','ITA','IGV','IYT','XRT','XOP','IHI','HYG','LQD','SMH','QQQ','SHY','SPY']; data=yf.download(syms,start='2000-01-01',auto_adjust=True,progress=False,threads=False); close=data['Close'] if isinstance(data.columns,pd.MultiIndex) else data[['Close']]; close=close.loc[:,syms].astype(float); current_end=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp('M'); m=close.resample('ME').last(); m=m.loc[m.index<current_end]; sha=hashlib.sha256(m.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()
 # P72 breadth
 breadth_syms=['SOXX','XBI','XHB','KRE','ITA','IGV','IYT','XRT','XOP','IHI']; sma=close[breadth_syms].rolling(200,min_periods=160).mean(); breadth=((close[breadth_syms]>sma).sum(axis=1)/len(breadth_syms)).resample('ME').last(); breadth=breadth.reindex(m.index)
 # P73 credit and P75 semiconductor leadership
 credit=m['HYG'].pct_change(3)-m['LQD'].pct_change(3); semi=m['SMH'].pct_change(6)-m['QQQ'].pct_change(6)
 def frame(signal,rule):
  rec=[]; prev=0.0
  for i,dt in enumerate(m.index[:-1]):
   nxt=m.index[i+1]
   if pd.isna(signal.get(dt)) or m.loc[[dt,nxt],['QQQ','SHY','SPY']].isna().any().any(): continue
   exp=1.0 if rule(float(signal.loc[dt])) else 0.0; q=float(m.at[nxt,'QQQ']/m.at[dt,'QQQ']-1); shy=float(m.at[nxt,'SHY']/m.at[dt,'SHY']-1); spy=float(m.at[nxt,'SPY']/m.at[dt,'SPY']-1); rec.append({'return_month':str(nxt.date()),'gross':exp*q+(1-exp)*shy,'qqq':q,'shy':shy,'spy':spy,'exp':exp,'turnover':abs(exp-prev)}); prev=exp
  return pd.DataFrame(rec)
 results={'P72':eval_timer(frame(breadth,lambda x:x>=.5)),'P73':eval_timer(frame(credit,lambda x:x>0)),'P75':eval_timer(frame(semi,lambda x:x>0))}
 prior={'P72':{'25':-0.0044442091771570436,'50':-0.008186294060749555},'P73':{'25':-0.010157890645838608,'50':-0.018183666341921256},'P75':{'25':-0.016601495451741277,'50':-0.022485461540648233}}
 stable={k:all(results[k]['costs'][bp]['excess_cagr_vs_matched']<0 for bp in ('25','50')) for k in results}
 out={'schema':'research.p77_complete_month_hygiene_reconciliation_r1','hypothesis':'Excluding the partial September observation does not reverse the rejection of P72, P73, or P75.','scientific_contract':{'recomputed_parents':['P72','P73','P75'],'complete_months_only':True,'economics_unchanged':True,'costs_bps':list(COSTS)},'source':{'provider':'Yahoo Finance via yfinance','complete_month_panel_sha256':sha},'results':results,'prior_partial_month_matched_excess':prior,'rejection_stable':stable,'decision':'REJECTIONS_CONFIRMED_COMPLETE_MONTHS' if all(stable.values()) else 'PARTIAL_MONTH_MATTERS_REOPEN_AFFECTED_PARENT'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p77_complete_month_hygiene_reconciliation_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'rejection_stable':stable,'results':{k:{'months':v['months'],'end':v['end'],'25':v['costs']['25'],'50':v['costs']['50']} for k,v in results.items()}},sort_keys=True))
if __name__=='__main__': main()

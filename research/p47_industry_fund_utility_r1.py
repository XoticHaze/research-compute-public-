from __future__ import annotations
import json,math,hashlib
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
U=('SMH','XBI','ITB','KRE','ITA','IGV','IWM','XRT'); COSTS=(25,50,100,200)

def metrics(r):
 r=pd.Series(r,dtype=float).dropna(); eq=(1+r).cumprod(); n=len(r); cg=float(eq.iloc[-1]**(12/n)-1); vol=float(r.std(ddof=0)*math.sqrt(12)); sh=float(r.mean()*12/vol) if vol else None; mdd=float((eq/eq.cummax()-1).min()); return {'cagr':cg,'vol':vol,'sharpe_rf0':sh,'maxdd':mdd,'calmar':float(cg/abs(mdd)) if mdd<0 else None}
def build():
 d=yf.download(list(U)+['SPY','QQQ'],start='2005-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna(how='all').astype(float); last=pd.Timestamp(d.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cut=last.to_period('M').start_time-pd.Timedelta(days=1); d=d.loc[d.index<=cut]; m=d.resample('ME').last(); vol=(d.pct_change(fill_method=None).rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last(); trend=(d/d.rolling(200,min_periods=160).mean()-1).resample('ME').last(); dd=(d/d.rolling(126,min_periods=100).max()-1).resample('ME').last(); mom=m.pct_change(6); prev={s:0. for s in U}; rows=[]
 for i,dt in enumerate(m.index[:-1]):
  b=pd.DataFrame({'mom6':mom.loc[dt,list(U)],'trend200':trend.loc[dt,list(U)],'low_vol6':-vol.loc[dt,list(U)],'drawdown6':dd.loc[dt,list(U)]},index=list(U))
  if b.isna().any().any(): continue
  score=b.rank(axis=0,pct=True,method='average').mean(axis=1); block=pd.DataFrame({'symbol':list(U),'score':[float(score[s]) for s in U]}).sort_values(['score','symbol'],ascending=[False,True]); chosen=block.head(3).symbol.tolist(); nxt=m.index[i+1]; rr=m.loc[nxt,list(U)+['SPY','QQQ']]/m.loc[dt,list(U)+['SPY','QQQ']]-1
  if rr.isna().any(): continue
  w={s:(1/3 if s in chosen else 0.) for s in U}; turn=.5*sum(abs(w[s]-prev[s]) for s in U); gross=sum(w[s]*float(rr[s]) for s in U); rows.append({'date':nxt,'gross':gross,'turnover':turn,'equal_weight':float(rr[list(U)].mean()),'spy':float(rr.SPY),'qqq':float(rr.QQQ)}); prev=w
 return pd.DataFrame(rows).set_index('date'),d,cut

def main():
 q,d,cut=build(); windows={'2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}; tests={}
 for w,s in windows.items():
  z=q.loc[pd.Timestamp(s):]; tests[w]={}
  for c in COSTS:
   net=z.gross-z.turnover*c/10000; tests[w][str(c)]={'candidate':metrics(net),'equal_weight':metrics(z.equal_weight),'spy':metrics(z.spy),'qqq':metrics(z.qqq),'excess_equal_weight':metrics(net)['cagr']-metrics(z.equal_weight)['cagr'],'excess_spy':metrics(net)['cagr']-metrics(z.spy)['cagr'],'excess_qqq':metrics(net)['cagr']-metrics(z.qqq)['cagr'],'annualized_one_way_turnover':float(z.turnover.mean()*12)}
 a=tests['2015']['50']; decision='P47_FUND_UTILITY_SUPPORTED' if a['excess_equal_weight']>0 and a['candidate']['sharpe_rf0']>=a['spy']['sharpe_rf0'] and a['candidate']['maxdd']>a['spy']['maxdd'] else 'P47_FUND_UTILITY_NOT_SUPPORTED'
 out={'schema':'research.p47_industry_fund_utility_r1','parent':'P47','hypothesis':'The frozen canonical industry top-3 composite provides after-cost matched alpha with enough risk utility to justify its broad-market opportunity cost.','contract':{'selector':'canonical fixed_multifactor_cross_sectional_r1 industry top-3 monthly','canonical_reference':'7bfd6ce8d78b13ae76e7ecfe70fd3dcbb0bfe987/research/fixed_multifactor_cross_sectional_r1.py','tie_break':'score descending, symbol ascending','cost_bps_per_one_way_turnover':list(COSTS),'controls':['same-industry-universe equal-weight','SPY','QQQ'],'windows':list(windows),'no_signal_factor_weight_cost_or_window_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cut.date()),'panel_sha256':hashlib.sha256(d.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()},'tests':tests,'decision':decision}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p47_industry_fund_utility_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()

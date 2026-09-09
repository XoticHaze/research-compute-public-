from __future__ import annotations
import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
U=('SPY','QQQ','TLT','GLD','DBC'); BP=50

def cagr(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1)

def main():
 d=yf.download(list(U),start='2005-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna(how='all').astype(float)
 last=pd.Timestamp(d.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cutoff=last.to_period('M').start_time-pd.Timedelta(days=1); d=d.loc[d.index<=cutoff]
 m=d.resample('ME').last(); dr=d.pct_change(fill_method=None); vol=(dr.rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last(); trend=(d/d.rolling(200,min_periods=160).mean()-1).resample('ME').last(); dd=(d/d.rolling(126,min_periods=100).max()-1).resample('ME').last(); mom=m.pct_change(6)
 rows=[]; prev={s:0. for s in U}
 for i,dt in enumerate(m.index[:-1]):
  b=pd.DataFrame({'mom6':mom.loc[dt,list(U)],'trend200':trend.loc[dt,list(U)],'low_vol6':-vol.loc[dt,list(U)],'drawdown6':dd.loc[dt,list(U)]},index=list(U))
  if b.isna().any().any(): continue
  score=b.rank(axis=0,pct=True,method='average').mean(axis=1); chosen=score.sort_values(ascending=False,kind='mergesort').index[:2]; w={s:(.5 if s in chosen else 0.) for s in U}; nxt=m.index[i+1]; rr=m.loc[nxt,list(U)]/m.loc[dt,list(U)]-1
  if rr.isna().any(): continue
  turn=.5*sum(abs(w[s]-prev[s]) for s in U); gross=sum(w[s]*float(rr[s]) for s in U); net=gross-turn*BP/10000
  rows.append({'feature_month':str(dt.date()),'return_month':str(nxt.date()),'p46_net_50bps':net,'p46_gross':gross,'turnover':turn,'equal_weight':float(rr.mean()),'qqq':float(rr['QQQ']),'spy':float(rr['SPY']),'chosen_1':chosen[0],'chosen_2':chosen[1]}); prev=w
 q=pd.DataFrame(rows); Path('artifacts').mkdir(exist_ok=True); q.to_csv('artifacts/p46_monthly_sleeve_returns_50bps.csv',index=False)
 out={'schema':'research.p46_monthly_sleeve_materialization_r1','parent':'P46','contract':{'universe':list(U),'score':'equal-weight percentile ranks of 6m momentum, price/SMA200 trend, inverse 6m realized vol, 6m distance-from-high','top_k':2,'rebalance':'monthly','cost_bps_turnover':BP,'no_parameter_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cutoff.date()),'panel_sha256':hashlib.sha256(d.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()},'rows':len(q),'start':q.iloc[0].return_month,'end':q.iloc[-1].return_month,'summary':{'p46_net_cagr':cagr(q.p46_net_50bps),'equal_weight_cagr':cagr(q.equal_weight),'excess_equal_weight_cagr':cagr(q.p46_net_50bps)-cagr(q.equal_weight),'qqq_cagr':cagr(q.qqq),'excess_qqq_cagr':cagr(q.p46_net_50bps)-cagr(q.qqq)},'csv_sha256':hashlib.sha256(Path('artifacts/p46_monthly_sleeve_returns_50bps.csv').read_bytes()).hexdigest(),'decision':'P46_MONTHLY_SLEEVE_VECTOR_MATERIALIZED'}
 Path('artifacts/p46_monthly_sleeve_materialization_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()

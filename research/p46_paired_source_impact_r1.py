from __future__ import annotations
import json,math,time,hashlib
from pathlib import Path
import pandas as pd,numpy as np,yfinance as yf
U=('SPY','QQQ','TLT','GLD','DBC')
def load():
 d=yf.download(list(U),start='2005-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna(how='all').astype(float); last=pd.Timestamp(d.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cut=last.to_period('M').start_time-pd.Timedelta(days=1); return d.loc[d.index<=cut,list(U)]
def replay(d):
 m=d.resample('ME').last(); vol=(d.pct_change(fill_method=None).rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last(); trend=(d/d.rolling(200,min_periods=160).mean()-1).resample('ME').last(); dd=(d/d.rolling(126,min_periods=100).max()-1).resample('ME').last(); mom=m.pct_change(6); prev={s:0. for s in U}; rows=[]
 for i,dt in enumerate(m.index[:-1]):
  b=pd.DataFrame({'mom6':mom.loc[dt,list(U)],'trend200':trend.loc[dt,list(U)],'low_vol6':-vol.loc[dt,list(U)],'drawdown6':dd.loc[dt,list(U)]},index=list(U))
  if b.isna().any().any(): continue
  score=b.rank(axis=0,pct=True,method='average').mean(axis=1); block=pd.DataFrame({'symbol':list(U),'score':[float(score[s]) for s in U]}).sort_values(['score','symbol'],ascending=[False,True]); chosen=tuple(block.head(2).symbol); nxt=m.index[i+1]; rr=m.loc[nxt,list(U)]/m.loc[dt,list(U)]-1
  if rr.isna().any(): continue
  w={s:(.5 if s in chosen else 0.) for s in U}; turn=.5*sum(abs(w[s]-prev[s]) for s in U); gross=sum(w[s]*float(rr[s]) for s in U); rows.append({'date':nxt,'chosen':'|'.join(chosen),'gross':gross,'turnover':turn,'ew':float(rr.mean()),'spy':float(rr.SPY),'qqq':float(rr.QQQ)}); prev=w
 return pd.DataFrame(rows).set_index('date')
def cagr(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1)
def main():
 a=load(); time.sleep(2); b=load(); ra,rb=replay(a),replay(b); idx=ra.index.intersection(rb.index); x,y=ra.loc[idx],rb.loc[idx]; selection_diff=int((x.chosen!=y.chosen).sum()); turnover_max=float((x.turnover-y.turnover).abs().max()); gross_max=float((x.gross-y.gross).abs().max()); econ={}
 for start in ('2015-01-01','2020-01-01'):
  xa=x.loc[pd.Timestamp(start):]; ya=y.loc[pd.Timestamp(start):]; na=xa.gross-xa.turnover*.005; nb=ya.gross-ya.turnover*.005; econ[start[:4]]={'cagr_a':cagr(na),'cagr_b':cagr(nb),'abs_cagr_diff':abs(cagr(na)-cagr(nb)),'ew_excess_a':cagr(na)-cagr(xa.ew),'ew_excess_b':cagr(nb)-cagr(ya.ew)}
 out={'schema':'research.p46_paired_source_impact_r1','parent':'P46','contract':{'selector':'exact canonical P46 score-desc/symbol-asc','paired_identical_requests':True,'cost_bps':50,'no_parameter_search':True},'comparison':{'common_months':len(idx),'selection_diff_months':selection_diff,'max_turnover_diff':turnover_max,'max_gross_return_diff':gross_max},'economics':econ,'classification':'P46_OUTPUT_INVARIANT_TO_OBSERVED_YAHOO_DRIFT' if selection_diff==0 and max(v['abs_cagr_diff'] for v in econ.values())<1e-6 else 'P46_OUTPUT_SENSITIVE_TO_YAHOO_DRIFT'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_paired_source_impact_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()

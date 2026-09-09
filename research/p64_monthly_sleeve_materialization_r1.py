from __future__ import annotations
import hashlib,json
from pathlib import Path
import pandas as pd,yfinance as yf
CROSS=('SPY','QQQ','TLT','GLD','DBC'); IND=('SOXX','XBI','XHB','KRE','ITA','IGV','IYT','XRT','XOP','IHI'); BP=50; DELAY=5

def cagr(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1)

def load(syms):
 return yf.download(list(dict.fromkeys((*syms,'SPY','QQQ'))),start='2005-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna(how='all').astype(float)

def sleeve(close,syms,topk):
 last=pd.Timestamp(close.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cutoff=last.to_period('M').start_time-pd.Timedelta(days=1); m=close.resample('ME').last(); m=m[m.index<=cutoff]; mom=m[list(syms)].pct_change(6); trend=(close[list(syms)]/close[list(syms)].rolling(200,min_periods=160).mean()-1).resample('ME').last().reindex(m.index); idx=close.index; prev={s:0. for s in syms}; rows=[]
 for i,dt in enumerate(m.index[:-1]):
  if i<6: continue
  b=pd.DataFrame({'mom6':mom.loc[dt,list(syms)],'trend200':trend.loc[dt,list(syms)]},index=list(syms))
  if b.isna().any().any(): continue
  score=b.rank(axis=0,pct=True,method='average').mean(axis=1); nxt=m.index[i+1]; a=idx.get_indexer([dt],method='pad')[0]+DELAY; z=idx.get_indexer([nxt],method='pad')[0]+DELAY
  if a<0 or z<0 or a>=len(idx) or z>=len(idx): continue
  r=close.iloc[z][list(syms)]/close.iloc[a][list(syms)]-1
  if r.isna().any(): continue
  chosen=list(score.sort_values(ascending=False,kind='mergesort').head(topk).index); w={s:(1/topk if s in chosen else 0.) for s in syms}; turn=.5*sum(abs(w[s]-prev[s]) for s in syms); gross=sum(w[s]*float(r[s]) for s in syms); qqq=float(close['QQQ'].iloc[z]/close['QQQ'].iloc[a]-1); rows.append({'date':pd.Timestamp(idx[z]),'gross':gross,'net':gross-turn*BP/10000,'matched':float(r.mean()),'qqq':qqq,'turnover':turn,'chosen':'|'.join(chosen)}); prev=w
 return pd.DataFrame(rows).set_index('date'),cutoff

def main():
 cc=load(CROSS); ic=load(IND); cf,ccut=sleeve(cc,CROSS,2); inf,icut=sleeve(ic,IND,3); ix=cf.index.intersection(inf.index); q=pd.DataFrame(index=ix); q['p57_cross_net_50bps']=cf.loc[ix,'net']; q['p52_industry_net_50bps']=inf.loc[ix,'net']; q['p64_net_50bps']=.5*q.p57_cross_net_50bps+.5*q.p52_industry_net_50bps; q['matched_blend']=.5*cf.loc[ix,'matched']+.5*inf.loc[ix,'matched']; q['qqq']=cf.loc[ix,'qqq']; q=q.dropna(); q.index.name='return_date'; Path('artifacts').mkdir(exist_ok=True); q.to_csv('artifacts/p64_monthly_sleeve_returns_5day_50bps.csv')
 out={'schema':'research.p64_monthly_sleeve_materialization_r1','parent':'P64','contract':{'cross_sleeve':'P57 momentum+trend top-2','industry_sleeve':'P52 momentum+trend top-3','weights':[0.5,0.5],'execution_delay_trading_days':DELAY,'component_cost_bps':BP,'no_parameter_or_weight_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','cross_last_complete_month_end':str(ccut.date()),'industry_last_complete_month_end':str(icut.date()),'cross_panel_sha256':hashlib.sha256(cc.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest(),'industry_panel_sha256':hashlib.sha256(ic.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()},'rows':len(q),'start':str(q.index.min().date()),'end':str(q.index.max().date()),'summary':{'p64_net_cagr':cagr(q.p64_net_50bps),'matched_blend_cagr':cagr(q.matched_blend),'excess_matched_cagr':cagr(q.p64_net_50bps)-cagr(q.matched_blend),'qqq_cagr':cagr(q.qqq),'excess_qqq_cagr':cagr(q.p64_net_50bps)-cagr(q.qqq)},'csv_sha256':hashlib.sha256(Path('artifacts/p64_monthly_sleeve_returns_5day_50bps.csv').read_bytes()).hexdigest(),'decision':'P64_INVESTABLE_MONTHLY_SLEEVE_VECTOR_MATERIALIZED'}; Path('artifacts/p64_monthly_sleeve_materialization_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()

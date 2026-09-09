from __future__ import annotations
import json,math,hashlib
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
CROSS=('SPY','QQQ','TLT','GLD','DBC'); IND=('SOXX','XBI','XHB','KRE','ITA','IGV','IYT','XRT','XOP','IHI'); BP=50; DELAY=5

def cagr(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1)
def metrics(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); vol=float(r.std(ddof=1)*math.sqrt(12)); ann=float(r.mean()*12); dd=float((e/e.cummax()-1).min()); return {'cagr':cagr(r),'sharpe_rf0':ann/vol if vol else None,'maxdd':dd}
def load(syms):
 return yf.download(list(dict.fromkeys((*syms,'SPY','QQQ'))),start='2005-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna(how='all').astype(float)
def sleeve(close,syms,topk,four):
 last=pd.Timestamp(close.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cutoff=last.to_period('M').start_time-pd.Timedelta(days=1); m=close.resample('ME').last(); m=m[m.index<=cutoff]; mom=m[list(syms)].pct_change(6); trend=(close[list(syms)]/close[list(syms)].rolling(200,min_periods=160).mean()-1).resample('ME').last().reindex(m.index); dr=close[list(syms)].pct_change(fill_method=None); vol=(dr.rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last().reindex(m.index); dd=(close[list(syms)]/close[list(syms)].rolling(126,min_periods=100).max()-1).resample('ME').last().reindex(m.index); idx=close.index; prev={s:0. for s in syms}; rows=[]
 for i,dt in enumerate(m.index[:-1]):
  if i<6: continue
  cols={'mom6':mom.loc[dt,list(syms)],'trend200':trend.loc[dt,list(syms)]}
  if four: cols.update({'low_vol6':-vol.loc[dt,list(syms)],'drawdown6':dd.loc[dt,list(syms)]})
  b=pd.DataFrame(cols,index=list(syms))
  if b.isna().any().any(): continue
  score=b.rank(axis=0,pct=True,method='average').mean(axis=1); nxt=m.index[i+1]; a=idx.get_indexer([dt],method='pad')[0]+DELAY; z=idx.get_indexer([nxt],method='pad')[0]+DELAY
  if a<0 or z<0 or a>=len(idx) or z>=len(idx): continue
  r=close.iloc[z][list(syms)]/close.iloc[a][list(syms)]-1
  if r.isna().any(): continue
  chosen=list(score.sort_values(ascending=False,kind='mergesort').head(topk).index); w={s:(1/topk if s in chosen else 0.) for s in syms}; turn=.5*sum(abs(w[s]-prev[s]) for s in syms); gross=sum(w[s]*float(r[s]) for s in syms); rows.append({'date':pd.Timestamp(idx[z]),'net':gross-turn*BP/10000,'matched':float(r.mean()),'qqq':float(close['QQQ'].iloc[z]/close['QQQ'].iloc[a]-1)}); prev=w
 return pd.DataFrame(rows).set_index('date'),cutoff
def evaluate(q):
 out={'months':len(q),'candidate':metrics(q.combo),'p46':metrics(q.p46),'p64':metrics(q.p64),'matched':metrics(q.matched),'qqq':metrics(q.qqq)}; out['excess_vs_matched']=out['candidate']['cagr']-out['matched']['cagr']; out['excess_vs_qqq']=out['candidate']['cagr']-out['qqq']['cagr']; out['delta_vs_p46']=out['candidate']['cagr']-out['p46']['cagr']; out['delta_sharpe_vs_p46']=out['candidate']['sharpe_rf0']-out['p46']['sharpe_rf0']; out['delta_maxdd_vs_p46']=out['candidate']['maxdd']-out['p46']['maxdd']; ids=np.array_split(np.arange(len(q)),5); fs=[]
 for j,ix in enumerate(ids,1):
  a=q.iloc[ix]; fs.append({'fold':j,'matched_excess':cagr(a.combo)-cagr(a.matched),'qqq_excess':cagr(a.combo)-cagr(a.qqq),'p46_delta':cagr(a.combo)-cagr(a.p46)})
 out['positive_matched_folds']=sum(x['matched_excess']>0 for x in fs); out['positive_qqq_folds']=sum(x['qqq_excess']>0 for x in fs); out['positive_p46_delta_folds']=sum(x['p46_delta']>0 for x in fs); out['folds']=fs; return out
def main():
 cc=load(CROSS); ic=load(IND); p46,cut=sleeve(cc,CROSS,2,True); p57,_=sleeve(cc,CROSS,2,False); p52,_=sleeve(ic,IND,3,False); ix=p46.index.intersection(p57.index).intersection(p52.index); q=pd.DataFrame(index=ix); q['p46']=p46.loc[ix,'net']; q['p64']=.5*p57.loc[ix,'net']+.5*p52.loc[ix,'net']; q['combo']=.5*q.p46+.5*q.p64; q['matched']=.5*p46.loc[ix,'matched']+.25*p57.loc[ix,'matched']+.25*p52.loc[ix,'matched']; q['qqq']=p46.loc[ix,'qqq']; q=q.dropna(); tests={k:evaluate(q.loc[pd.Timestamp(v):]) for k,v in {'2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}.items()}; t=tests['2020']; decision='P46_P64_FIXED_UTILITY_SUPPORTED_FOR_FURTHER_FALSIFICATION' if t['excess_vs_matched']>0 and t['positive_matched_folds']>=3 and t['delta_sharpe_vs_p46']>0 and tests['2022']['excess_vs_qqq']>0 else 'P46_P64_FIXED_UTILITY_NOT_SUPPORTED'
 out={'schema':'research.p46_p64_fixed_utility_r1','parent':'P46+P64','hypothesis':'A fixed 50/50 blend of investable five-day P46 and P64 sleeves adds durable after-cost utility beyond their matched exposures and standalone P46 without weight search.','contract':{'p46':'four-factor crossasset top-2','p64':'50/50 P57 crossasset momentum+trend top-2 plus P52 industry momentum+trend top-3','portfolio_weights':[0.5,0.5],'execution_delay_trading_days':DELAY,'component_cost_bps':BP,'matched_control':'50% P46 crossasset EW + 25% P57 crossasset EW + 25% P52 industry EW on identical delayed intervals','opportunity_control':'QQQ identical delayed intervals','windows':['2015','2020','2022'],'folds':5,'no_weight_parameter_or_delay_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cut.date()),'cross_panel_sha256':hashlib.sha256(cc.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest(),'industry_panel_sha256':hashlib.sha256(ic.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()},'tests':tests,'decision':decision}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_p64_fixed_utility_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()

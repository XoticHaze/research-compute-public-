from __future__ import annotations
import hashlib, json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

CUT='2026-08-31'; END='2026-09-01'; START='2005-01-01'
P52=('SMH','XBI','ITB','KRE','ITA','IGV','IWM','XRT')
P52_ALT=('SOXX','XBI','XHB','KRE','ITA','IGV','IYT','XRT','XOP','IHI')
P57=('SPY','QQQ','TLT','GLD','DBC')
P57_ALT=('SPY','QQQ','IEF','IAU','PDBC')
ALL=tuple(dict.fromkeys((*P52,*P52_ALT,*P57,*P57_ALT)))

def metrics(r):
 r=pd.Series(r,dtype=float).dropna(); eq=(1+r).cumprod(); years=len(r)/12; cagr=float(eq.iloc[-1]**(1/years)-1); ann=float(r.mean()*12); vol=float(r.std(ddof=0)*math.sqrt(12)); dd=eq/eq.cummax()-1
 return {'cagr':cagr,'annualized_mean':ann,'annualized_vol':vol,'sharpe_rf0':ann/vol if vol else None,'max_drawdown_monthly':float(dd.min()),'calmar':cagr/abs(float(dd.min())) if float(dd.min())<0 else None,'final_equity':float(eq.iloc[-1])}
def folds(c,b):
 out=[]
 for n,idx in enumerate(np.array_split(np.arange(len(c)),5),1):
  cm,bm=metrics(c.iloc[idx]),metrics(b.iloc[idx]); out.append({'fold':n,'candidate_cagr':cm['cagr'],'baseline_cagr':bm['cagr'],'excess_cagr':cm['cagr']-bm['cagr']})
 return sum(x['excess_cagr']>0 for x in out),out
def load():
 d=yf.download(list(ALL),start=START,end=END,auto_adjust=True,progress=False,threads=False)
 c=d['Close'] if isinstance(d.columns,pd.MultiIndex) else d[['Close']]
 if not isinstance(c,pd.DataFrame): c=c.to_frame()
 missing=[s for s in ALL if s not in c.columns]
 if missing: raise RuntimeError(f'missing:{missing}')
 c=c.loc[c.index<=pd.Timestamp(CUT),list(ALL)].astype(float).dropna(how='all')
 if c.index.max()>pd.Timestamp(CUT): raise RuntimeError('cutoff_violation')
 h=hashlib.sha256(c.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()
 return c,h
def fmap(c):
 m=c.resample('ME').last(); dr=c.pct_change()
 return m,{'mom6':m.pct_change(6),'trend200':(c/c.rolling(200,min_periods=160).mean()-1).resample('ME').last(),'low_vol6':-(dr.rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last(),'drawdown6':(c/c.rolling(126,min_periods=100).max()-1).resample('ME').last()}
def run(c,syms,factors,topk,lag=0):
 m,fm=fmap(c); prev={s:0.0 for s in syms}; rec=[]
 for dt in m.index:
  b=pd.DataFrame({f:fm[f].loc[dt,list(syms)] for f in factors},index=list(syms))
  if b.isna().any().any(): continue
  sc=b.rank(axis=0,pct=True,method='average').mean(axis=1); loc=m.index.get_loc(dt)
  if not isinstance(loc,(int,np.integer)) or loc+1+lag>=len(m): continue
  start=m.index[loc+lag]; nxt=m.index[loc+1+lag]; r=m.loc[nxt,list(syms)]/m.loc[start,list(syms)]-1
  if r.isna().any(): continue
  chosen=sc.sort_values(ascending=False).head(topk).index.tolist(); w={s:(1/topk if s in chosen else 0.0) for s in syms}; to=.5*sum(abs(w[s]-prev[s]) for s in syms)
  rec.append({'date':nxt,'feature_date':dt,'gross':sum(w[s]*float(r[s]) for s in syms),'ew':float(r.mean()),'turnover':to}); prev=w
 return pd.DataFrame(rec).set_index('date')
def score(fr,bp):
 c=fr.gross-fr.turnover*bp/10000; b=fr.ew; cm,bm=metrics(c),metrics(b); p,fd=folds(c,b)
 return {'months':len(fr),'start':str(fr.index.min().date()),'end':str(fr.index.max().date()),'candidate':cm,'matched_ew':bm,'excess_cagr':cm['cagr']-bm['cagr'],'positive_folds':p,'folds':fd}
def pack(fr): return {'25':score(fr,25),'50':score(fr,50)}
def temporal(fr):
 x={'full':pack(fr)}
 for y in ('2015','2020'): x[y+'_forward']=pack(fr.loc[pd.Timestamp(y+'-01-01'):])
 return x
def concentration(c,fr):
 spy=c['SPY']; state=(spy>spy.rolling(200,min_periods=160).mean()).resample('ME').last(); out={}
 for bp in (25,50):
  cand=fr.gross-fr.turnover*bp/10000; ex=cand-fr.ew; fs=pd.Series([state.get(pd.Timestamp(x),pd.NA) for x in fr.feature_date],index=fr.index,dtype='boolean'); rows={}
  for label,mask in (('risk_on',fs==True),('risk_off',fs==False)):
   keep=mask.fillna(False); cm,bm=metrics(cand[keep]),metrics(fr.ew[keep]); rows[label]={'months':int(keep.sum()),'annualized_mean_excess':float((cand[keep]-fr.ew[keep]).mean()*12),'excess_cagr':cm['cagr']-bm['cagr'],'candidate':cm,'matched_ew':bm}
  strong=ex.nlargest(5).index; keep=~fr.index.isin(strong); cm,bm=metrics(cand[keep]),metrics(fr.ew[keep]); rows['remove_five_strongest_relative_months']={'months':int(keep.sum()),'removed':[str(pd.Timestamp(x).date()) for x in strong],'excess_cagr':cm['cagr']-bm['cagr'],'candidate':cm,'matched_ew':bm}; out[str(bp)]=rows
 return out
def leaveouts(c,syms,factors,topk):
 out={}
 for omitted in syms:
  fr=run(c,tuple(s for s in syms if s!=omitted),factors,topk); out['leave_out_'+omitted]=pack(fr)
 return out
def p58_combo(c):
 a=run(c,P57,('mom6','trend200','low_vol6','drawdown6'),2); b=run(c,P52,('mom6','trend200'),3); ix=a.index.intersection(b.index); a=a.loc[ix]; b=b.loc[ix]; out={}
 m=c.resample('ME').last()
 for scope,start in (('full',None),('2015_forward','2015-01-01'),('2020_forward','2020-01-01')):
  aa=a if start is None else a.loc[pd.Timestamp(start):]; bb=b.loc[aa.index]
  rows={}
  for bp in (25,50):
   ac=aa.gross-aa.turnover*bp/10000; bc=bb.gross-bb.turnover*bp/10000; combo=.5*ac+.5*bc; matched=.5*aa.ew+.5*bb.ew; cm,bm=metrics(combo),metrics(matched); p,fd=folds(combo,matched)
   rows[str(bp)]={'combo':cm,'matched_static_blend':bm,'cross_sleeve':metrics(ac),'industry_sleeve':metrics(bc),'excess_cagr_vs_matched':cm['cagr']-bm['cagr'],'excess_cagr_vs_cross':cm['cagr']-metrics(ac)['cagr'],'excess_cagr_vs_industry':cm['cagr']-metrics(bc)['cagr'],'positive_folds':p,'folds':fd,'sleeve_return_correlation':float(ac.corr(bc))}
  out[scope]=rows
 return out
def capital(c,fr):
 m=c.resample('ME').last(); spy=[]; qqq=[]
 for _,r in fr.iterrows():
  dt=pd.Timestamp(r.name); loc=m.index.get_loc(dt); prv=m.index[loc-1]; spy.append(float(m.at[dt,'SPY']/m.at[prv,'SPY']-1)); qqq.append(float(m.at[dt,'QQQ']/m.at[prv,'QQQ']-1))
 spy=pd.Series(spy,index=fr.index); qqq=pd.Series(qqq,index=fr.index); out={}
 for bp in (25,50):
  cand=fr.gross-fr.turnover*bp/10000; cm,em,sm,qm=metrics(cand),metrics(fr.ew),metrics(spy),metrics(qqq); out[str(bp)]={'candidate':cm,'matched_ew':em,'spy':sm,'qqq':qm,'excess_cagr_vs_matched':cm['cagr']-em['cagr'],'excess_cagr_vs_spy':cm['cagr']-sm['cagr'],'excess_cagr_vs_qqq':cm['cagr']-qm['cagr']}
 bm=metrics(fr.ew)['cagr']; ex=[metrics(fr.gross-fr.turnover*bp/10000)['cagr']-bm for bp in range(201)]; non=[i for i,x in enumerate(ex) if x<=0]; out['cost_breakeven']={'first_nonpositive_bps':non[0] if non else None,'excess_25':ex[25],'excess_50':ex[50],'excess_100':ex[100]}; return out
def main():
 c,h=load(); f52=run(c,P52,('mom6','trend200'),3); f52lag=run(c,P52,('mom6','trend200'),3,1); f52a=run(c,P52_ALT,('mom6','trend200'),3); f52alag=run(c,P52_ALT,('mom6','trend200'),3,1); f57=run(c,P57,('mom6','trend200'),2); f57lag=run(c,P57,('mom6','trend200'),2,1); f60=run(c,P57_ALT,('mom6','trend200'),2); f60lag=run(c,P57_ALT,('mom6','trend200'),2,1)
 p57_lo=leaveouts(c,P57,('mom6','trend200'),2); ex=(f57.gross-f57.turnover*.0025-f57.ew).to_numpy(); rng=np.random.default_rng(61); vals=np.array([rng.choice(ex,size=len(ex),replace=True).mean()*12 for _ in range(3000)]); q=np.quantile(vals,[.025,.975])
 out={'schema':'research.market_research_complete_month_r11d','scientific_cutoff':CUT,'source':{'provider':'Yahoo Finance via yfinance','download_end_exclusive':END,'normalized_complete_month_panel_sha256':h,'last_daily_observation':str(c.index.max().date())},'integrity':{'incomplete_september_2026_excluded':True,'single_panel_shared_across_all_discriminators':True,'supersedes_unpinned_r11_results':True},'p52':{'base':{**temporal(f52),'one_month_execution_lag':pack(f52lag)},'independent_representation':{**temporal(f52a),'one_month_execution_lag':pack(f52alag)},'leave_one_out':leaveouts(c,P52,('mom6','trend200'),3),'concentration':concentration(c,f52)},'p57':{'base':{**temporal(f57),'one_month_execution_lag':pack(f57lag)},'independent_representation':{**temporal(f60),'one_month_execution_lag':pack(f60lag)},'leave_one_out':p57_lo,'paired_bootstrap_25':{'annualized_mean_excess':float(ex.mean()*12),'bootstrap_95pct':[float(q[0]),float(q[1])],'p_excess_le_zero':float((vals<=0).mean()),'n':3000},'concentration':concentration(c,f57),'capital_risk':capital(c,f57)},'p58_combination':p58_combo(c)}
 Path('artifacts').mkdir(exist_ok=True); Path('artifacts/market_research_complete_month_r11d.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
 print(json.dumps({'cutoff':CUT,'hash':h,'p52_full25':out['p52']['base']['full']['25']['excess_cagr'],'p52_alt25':out['p52']['independent_representation']['full']['25']['excess_cagr'],'p52_top5_removed25':out['p52']['concentration']['25']['remove_five_strongest_relative_months']['excess_cagr'],'p57_full25':out['p57']['base']['full']['25']['excess_cagr'],'p57_alt25':out['p57']['independent_representation']['full']['25']['excess_cagr'],'p57_top5_removed25':out['p57']['concentration']['25']['remove_five_strongest_relative_months']['excess_cagr'],'p57_bootstrap_p':out['p57']['paired_bootstrap_25']['p_excess_le_zero'],'p58_full25':out['p58_combination']['full']['25']['excess_cagr_vs_matched']},sort_keys=True))
if __name__=='__main__': main()

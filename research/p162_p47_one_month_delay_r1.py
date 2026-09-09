import json,math,hashlib
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
U=('SMH','XBI','ITB','KRE','ITA','IGV','IWM','XRT'); COST=(25,50,100); W={'2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}
def met(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); c=float(e.iloc[-1]**(12/len(r))-1); v=float(r.std(ddof=0)*math.sqrt(12)); return {'cagr':c,'sharpe':float(r.mean()*12/v) if v else None,'maxdd':float((e/e.cummax()-1).min())}
def build():
 d=yf.download(list(U)+['SPY','QQQ'],start='2005-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna(how='all').astype(float); last=pd.Timestamp(d.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cut=last.to_period('M').start_time-pd.Timedelta(days=1); d=d.loc[d.index<=cut]; m=d.resample('ME').last(); vol=(d.pct_change(fill_method=None).rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last(); tr=(d/d.rolling(200,min_periods=160).mean()-1).resample('ME').last(); dd=(d/d.rolling(126,min_periods=100).max()-1).resample('ME').last(); mom=m.pct_change(6); choices={}
 for x in m.index:
  z=pd.DataFrame({'m':mom.loc[x,list(U)],'t':tr.loc[x,list(U)],'v':-vol.loc[x,list(U)],'d':dd.loc[x,list(U)]},index=list(U))
  if z.isna().any().any(): continue
  q=z.rank(axis=0,pct=True,method='average').mean(axis=1); choices[x]=sorted(U,key=lambda s:(-q[s],s))[:3]
 prev={s:0 for s in U}; rows=[]
 for sig,c in choices.items():
  i=m.index.get_loc(sig)
  if i+2>=len(m): continue
  start=m.index[i+1]; end=m.index[i+2]; rr=m.loc[end,list(U)+['SPY','QQQ']]/m.loc[start,list(U)+['SPY','QQQ']]-1
  if rr.isna().any(): continue
  w={s:(1/3 if s in c else 0) for s in U}; turn=.5*sum(abs(w[s]-prev[s]) for s in U); rows.append({'date':end,'gross':sum(w[s]*rr[s] for s in U),'turn':turn,'ew':rr[list(U)].mean(),'spy':rr.SPY,'qqq':rr.QQQ}); prev=w
 return pd.DataFrame(rows).set_index('date'),d,cut
def ev(z,c):
 n=z.gross-z.turn*c/10000; x={'candidate':met(n),'matched':met(z.ew),'spy':met(z.spy),'qqq':met(z.qqq),'excess_matched':met(n)['cagr']-met(z.ew)['cagr'],'excess_spy':met(n)['cagr']-met(z.spy)['cagr'],'excess_qqq':met(n)['cagr']-met(z.qqq)['cagr']}; fs=[]
 for i,ix in enumerate(np.array_split(np.arange(len(z)),5),1):
  a=z.iloc[ix]; nn=a.gross-a.turn*c/10000; fs.append({'fold':i,'matched_excess':met(nn)['cagr']-met(a.ew)['cagr']})
 x['positive_matched_folds']=sum(f['matched_excess']>0 for f in fs); x['folds']=fs; return x
def main():
 q,d,cut=build(); t={w:{str(c):ev(q.loc[pd.Timestamp(s):],c) for c in COST} for w,s in W.items()}; a=t['2015']['50']; b=t['2020']['50']; ok=a['excess_matched']>0 and a['excess_spy']>0 and a['positive_matched_folds']>=3 and b['excess_matched']>0; dec='P47_ONE_MONTH_DELAY_IMPLEMENTATION_ROBUST' if ok else 'P47_ONE_MONTH_DELAY_IMPLEMENTATION_FRAGILE'; o={'schema':'research.p162_p47_one_month_delay_r1','parent':'P47','adjudicator':'P162','hypothesis':'Frozen P47 industry selector retains after-cost matched and SPY utility when implementation is delayed one additional completed month.','contract':{'selector':'unchanged canonical P47 top-3 four-factor ranking','delay':'signal at completed month t applied over return month t+2','cost_bps':list(COST),'controls':['same-industry equal-weight','SPY','QQQ'],'windows':list(W),'no_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cut.date()),'panel_sha256':hashlib.sha256(d.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()},'tests':t,'decision':dec}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p162_p47_one_month_delay_r1.json').write_text(json.dumps(o,indent=2,sort_keys=True)); print(json.dumps(o,sort_keys=True))
if __name__=='__main__': main()

import json,math,hashlib
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
A=('SPY','QQQ','TLT','GLD','DBC'); B=('SMH','XBI','ITB','KRE','ITA','IGV','IWM','XRT'); U=tuple(dict.fromkeys(A+B)); COST=(25,50,100)
def met(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); v=float(r.std(ddof=0)*math.sqrt(12)); c=float(e.iloc[-1]**(12/len(r))-1); d=float((e/e.cummax()-1).min()); return {'cagr':c,'sharpe':float(r.mean()*12/v) if v else None,'maxdd':d}
def ranks(d,m,s):
 vol=(d.pct_change(fill_method=None).rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last(); tr=(d/d.rolling(200,min_periods=160).mean()-1).resample('ME').last(); dd=(d/d.rolling(126,min_periods=100).max()-1).resample('ME').last(); mom=m.pct_change(6); out={}
 for x in m.index:
  z=pd.DataFrame({'m':mom.loc[x,list(s)],'t':tr.loc[x,list(s)],'v':-vol.loc[x,list(s)],'d':dd.loc[x,list(s)]},index=list(s))
  if z.isna().any().any(): continue
  q=z.rank(axis=0,pct=True,method='average').mean(axis=1); out[x]=sorted(s,key=lambda k:(-q[k],k))
 return out
def build():
 d=yf.download(list(U),start='2005-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna(how='all').astype(float); last=pd.Timestamp(d.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cut=last.to_period('M').start_time-pd.Timedelta(days=1); d=d.loc[d.index<=cut]; m=d.resample('ME').last(); ra,rb=ranks(d,m,A),ranks(d,m,B); pa={x:0 for x in A}; pb={x:0 for x in B}; rows=[]
 for x in sorted(set(ra)&set(rb)):
  i=m.index.get_loc(x)
  if i+1>=len(m): continue
  n=m.index[i+1]; rr=m.loc[n,list(U)]/m.loc[x,list(U)]-1
  if rr.isna().any(): continue
  ca,cb=ra[x][:2],rb[x][:3]; wa={z:(.5 if z in ca else 0) for z in A}; wb={z:(1/3 if z in cb else 0) for z in B}; ta=.5*sum(abs(wa[z]-pa[z]) for z in A); tb=.5*sum(abs(wb[z]-pb[z]) for z in B)
  rows.append({'date':n,'a':sum(wa[z]*rr[z] for z in A),'b':sum(wb[z]*rr[z] for z in B),'ta':ta,'tb':tb,'ma':rr[list(A)].mean(),'mb':rr[list(B)].mean(),'spy':rr.SPY,'qqq':rr.QQQ}); pa,pb=wa,wb
 return pd.DataFrame(rows).set_index('date'),d,cut
def ev(z,c):
 a=z.a-z.ta*c/10000; b=z.b-z.tb*c/10000; q=.5*a+.5*b; m=.5*z.ma+.5*z.mb; x={'combo':met(q),'matched':met(m),'spy':met(z.spy),'qqq':met(z.qqq),'excess_matched':met(q)['cagr']-met(m)['cagr'],'excess_spy':met(q)['cagr']-met(z.spy)['cagr'],'excess_qqq':met(q)['cagr']-met(z.qqq)['cagr'],'component_corr':float(a.corr(b))}; fs=[]
 for i,ix in enumerate(np.array_split(np.arange(len(z)),5),1):
  y=z.iloc[ix]; aa=y.a-y.ta*c/10000; bb=y.b-y.tb*c/10000; cc=.5*aa+.5*bb; mm=.5*y.ma+.5*y.mb; fs.append({'fold':i,'matched_excess':met(cc)['cagr']-met(mm)['cagr']})
 x['positive_matched_folds']=sum(f['matched_excess']>0 for f in fs); x['folds']=fs; return x
def main():
 q,d,cut=build(); W={'2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}; t={w:{str(c):ev(q.loc[pd.Timestamp(s):],c) for c in COST} for w,s in W.items()}; a=t['2015']['50']; b=t['2020']['50']; ok=a['excess_matched']>0 and a['positive_matched_folds']>=3 and b['excess_matched']>0 and b['positive_matched_folds']>=3 and a['component_corr']<.8; dec='P160_FIXED_P46_P47_COMBINATION_SUPPORTED_FOR_INDEPENDENT_VALIDATION' if ok else 'P160_FIXED_P46_P47_COMBINATION_NOT_SUPPORTED'; o={'schema':'research.p160_fixed_p46_p47_combo_r1','parent':'P160','hypothesis':'A fixed 50/50 combination of frozen P46 cross-asset top-2 and P47 industry top-3 composites creates persistent after-cost matched excess without combination-weight optimization.','contract':{'combination':'fixed 50/50','cost_bps':list(COST),'matched':'50/50 same-universe equal-weight controls','opportunity':['SPY','QQQ'],'windows':list(W),'no_search':True,'portfolio_authority':False},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cut.date()),'panel_sha256':hashlib.sha256(d.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()},'tests':t,'decision':dec}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p160_fixed_p46_p47_combo_r1.json').write_text(json.dumps(o,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(o,sort_keys=True))
if __name__=='__main__': main()

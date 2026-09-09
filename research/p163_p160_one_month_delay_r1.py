import json,hashlib
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
from p160_fixed_p46_p47_combo_r1 import A,B,U,COST,ranks,met
W={'2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}

def build():
 d=yf.download(list(U),start='2005-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna(how='all').astype(float); last=pd.Timestamp(d.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cut=last.to_period('M').start_time-pd.Timedelta(days=1); d=d.loc[d.index<=cut]; m=d.resample('ME').last(); ra=ranks(d,m,A); rb=ranks(d,m,B); pa={x:0 for x in A}; pb={x:0 for x in B}; rows=[]
 for sig in sorted(set(ra)&set(rb)):
  i=m.index.get_loc(sig)
  if i+2>=len(m): continue
  st,en=m.index[i+1],m.index[i+2]; rr=m.loc[en,list(U)]/m.loc[st,list(U)]-1
  if rr.isna().any(): continue
  ca=ra[sig][:2]; cb=rb[sig][:3]; wa={x:(.5 if x in ca else 0) for x in A}; wb={x:(1/3 if x in cb else 0) for x in B}; ta=.5*sum(abs(wa[x]-pa[x]) for x in A); tb=.5*sum(abs(wb[x]-pb[x]) for x in B); rows.append({'date':en,'a':sum(wa[x]*rr[x] for x in A),'b':sum(wb[x]*rr[x] for x in B),'ta':ta,'tb':tb,'ma':rr[list(A)].mean(),'mb':rr[list(B)].mean(),'spy':rr.SPY,'qqq':rr.QQQ}); pa,pb=wa,wb
 return pd.DataFrame(rows).set_index('date'),d,cut

def ev(z,c):
 a=z.a-z.ta*c/10000; b=z.b-z.tb*c/10000; q=.5*a+.5*b; m=.5*z.ma+.5*z.mb; x={'combo':met(q),'matched':met(m),'spy':met(z.spy),'qqq':met(z.qqq),'excess_matched':met(q)['cagr']-met(m)['cagr'],'excess_spy':met(q)['cagr']-met(z.spy)['cagr'],'excess_qqq':met(q)['cagr']-met(z.qqq)['cagr'],'component_corr':float(a.corr(b))}; fs=[]
 for i,ix in enumerate(np.array_split(np.arange(len(z)),5),1):
  y=z.iloc[ix]; aa=y.a-y.ta*c/10000; bb=y.b-y.tb*c/10000; cc=.5*aa+.5*bb; mm=.5*y.ma+.5*y.mb; fs.append({'fold':i,'matched_excess':met(cc)['cagr']-met(mm)['cagr']})
 x['positive_matched_folds']=sum(f['matched_excess']>0 for f in fs); x['folds']=fs; return x

def main():
 q,d,cut=build(); t={w:{str(c):ev(q.loc[pd.Timestamp(s):],c) for c in COST} for w,s in W.items()}; a=t['2015']['50']; b=t['2020']['50']; ok=a['excess_matched']>0 and a['positive_matched_folds']>=3 and b['excess_matched']>0 and b['positive_matched_folds']>=3; dec='P160_ONE_MONTH_DELAY_IMPLEMENTATION_ROBUST' if ok else 'P160_ONE_MONTH_DELAY_IMPLEMENTATION_FRAGILE'; o={'schema':'research.p163_p160_one_month_delay_r1','parent':'P160','adjudicator':'P163','hypothesis':'The fixed P160 50/50 P46+P47 combination retains after-cost matched alpha when both frozen component selectors are implemented one additional completed month late.','contract':{'combination':'fixed 50/50','selectors':'unchanged frozen P46 top-2 and P47 top-3','delay':'signal t applied over t+2 return month','cost_bps':list(COST),'matched':'50/50 same-universe equal-weight controls','opportunity':['SPY','QQQ'],'windows':list(W),'no_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cut.date()),'panel_sha256':hashlib.sha256(d.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()},'tests':t,'decision':dec}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p163_p160_one_month_delay_r1.json').write_text(json.dumps(o,indent=2,sort_keys=True)); print(json.dumps(o,sort_keys=True))
if __name__=='__main__': main()

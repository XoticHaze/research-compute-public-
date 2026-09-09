import io,json,math,hashlib,urllib.request
from pathlib import Path
import numpy as np,pandas as pd
U=('SPY','QQQ','TLT','GLD','DBC'); COST=(25,50,100); W={'2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}
def met(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); c=float(e.iloc[-1]**(12/len(r))-1); v=float(r.std(ddof=0)*math.sqrt(12)); return {'cagr':c,'sharpe':float(r.mean()*12/v) if v else None,'maxdd':float((e/e.cummax()-1).min())}
def load():
 out={}
 for s in U:
  url=f'https://stooq.com/q/d/l/?s={s.lower()}.us&i=d&d1=20050101&d2=20260909'
  req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 research-validation/1.0','Accept':'text/csv,*/*'})
  raw=urllib.request.urlopen(req,timeout=30).read(); z=pd.read_csv(io.BytesIO(raw),parse_dates=['Date']).set_index('Date').sort_index()
  if 'Close' not in z or len(z)<500: raise RuntimeError(f'Stooq invalid panel for {s}: rows={len(z)} columns={list(z.columns)}')
  out[s]=z['Close'].astype(float)
 d=pd.DataFrame(out).dropna(); last=pd.Timestamp(d.index.max()); cut=last.to_period('M').start_time-pd.Timedelta(days=1); return d.loc[d.index<=cut],cut
def build():
 d,cut=load(); m=d.resample('ME').last(); dr=d.pct_change(fill_method=None); vol=(dr.rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last(); tr=(d/d.rolling(200,min_periods=160).mean()-1).resample('ME').last(); dd=(d/d.rolling(126,min_periods=100).max()-1).resample('ME').last(); mom=m.pct_change(6); prev={s:0 for s in U}; rows=[]
 for i,x in enumerate(m.index[:-1]):
  z=pd.DataFrame({'m':mom.loc[x,list(U)],'t':tr.loc[x,list(U)],'v':-vol.loc[x,list(U)],'d':dd.loc[x,list(U)]},index=list(U))
  if z.isna().any().any(): continue
  q=z.rank(axis=0,pct=True,method='average').mean(axis=1); pick=sorted(U,key=lambda s:(-q[s],s))[:2]; w={s:(.5 if s in pick else 0) for s in U}; n=m.index[i+1]; rr=m.loc[n,list(U)]/m.loc[x,list(U)]-1
  if rr.isna().any(): continue
  turn=.5*sum(abs(w[s]-prev[s]) for s in U); rows.append({'date':n,'gross':sum(w[s]*rr[s] for s in U),'turn':turn,'matched':rr[list(U)].mean(),'spy':rr.SPY,'qqq':rr.QQQ}); prev=w
 return pd.DataFrame(rows).set_index('date'),d,cut
def ev(z,c):
 n=z.gross-z.turn*c/10000; x={'candidate':met(n),'matched':met(z.matched),'spy':met(z.spy),'qqq':met(z.qqq),'excess_matched':met(n)['cagr']-met(z.matched)['cagr'],'excess_spy':met(n)['cagr']-met(z.spy)['cagr'],'excess_qqq':met(n)['cagr']-met(z.qqq)['cagr']}; fs=[]
 for i,ix in enumerate(np.array_split(np.arange(len(z)),5),1):
  a=z.iloc[ix]; nn=a.gross-a.turn*c/10000; fs.append({'fold':i,'matched_excess':met(nn)['cagr']-met(a.matched)['cagr']})
 x['positive_matched_folds']=sum(f['matched_excess']>0 for f in fs); x['folds']=fs; return x
def main():
 q,d,cut=build(); t={w:{str(c):ev(q.loc[pd.Timestamp(s):],c) for c in COST} for w,s in W.items()}; a=t['2015']['50']; b=t['2020']['50']; ok=a['excess_matched']>0 and a['positive_matched_folds']>=3 and b['excess_matched']>0 and b['positive_matched_folds']>=3; dec='P46_STOOQ_REPLICATION_SUPPORTED' if ok else 'P46_STOOQ_REPLICATION_NOT_SUPPORTED'; o={'schema':'research.p166_p46_stooq_replication_r1','parent':'P46','adjudicator':'P166','hypothesis':'The frozen P46 selector retains after-cost matched excess on an independent Stooq daily-price representation.','contract':{'selector':'frozen P46 four-factor top-2','source':'Stooq daily close','cost_bps':list(COST),'controls':['same-universe equal-weight','SPY','QQQ'],'windows':list(W),'no_search':True},'source':{'provider':'Stooq','last_complete_month_end':str(cut.date()),'panel_sha256':hashlib.sha256(d.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()},'tests':t,'decision':dec}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p166_p46_stooq_replication_r1.json').write_text(json.dumps(o,indent=2,sort_keys=True)); print(json.dumps(o,sort_keys=True))
if __name__=='__main__': main()

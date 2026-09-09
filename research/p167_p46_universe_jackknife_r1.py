import json,math,hashlib
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
U=('SPY','QQQ','TLT','GLD','DBC'); COST=50; WINDOWS={'2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}
def met(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); c=float(e.iloc[-1]**(12/len(r))-1); v=float(r.std(ddof=0)*math.sqrt(12)); return {'cagr':c,'sharpe':float(r.mean()*12/v) if v else None,'maxdd':float((e/e.cummax()-1).min())}
def run(close,symbols):
 m=close[list(symbols)].resample('ME').last(); dr=close[list(symbols)].pct_change(fill_method=None); vol=(dr.rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last(); tr=(close[list(symbols)]/close[list(symbols)].rolling(200,min_periods=160).mean()-1).resample('ME').last(); dd=(close[list(symbols)]/close[list(symbols)].rolling(126,min_periods=100).max()-1).resample('ME').last(); mom=m.pct_change(6); prev={s:0 for s in symbols}; rows=[]
 for i,x in enumerate(m.index[:-1]):
  z=pd.DataFrame({'m':mom.loc[x,list(symbols)],'t':tr.loc[x,list(symbols)],'v':-vol.loc[x,list(symbols)],'d':dd.loc[x,list(symbols)]},index=list(symbols))
  if z.isna().any().any(): continue
  score=z.rank(axis=0,pct=True,method='average').mean(axis=1); pick=sorted(symbols,key=lambda s:(-score[s],s))[:2]; w={s:(.5 if s in pick else 0) for s in symbols}; n=m.index[i+1]; rr=m.loc[n]/m.loc[x]-1
  if rr.isna().any(): continue
  turn=.5*sum(abs(w[s]-prev[s]) for s in symbols); rows.append({'date':n,'gross':sum(w[s]*rr[s] for s in symbols),'turn':turn,'matched':float(rr.mean())}); prev=w
 return pd.DataFrame(rows).set_index('date')
def ev(q,start):
 z=q.loc[pd.Timestamp(start):]; net=z.gross-z.turn*COST/10000; folds=[]
 for i,ix in enumerate(np.array_split(np.arange(len(z)),5),1):
  a=z.iloc[ix]; n=a.gross-a.turn*COST/10000; folds.append({'fold':i,'matched_excess':met(n)['cagr']-met(a.matched)['cagr']})
 return {'candidate':met(net),'matched':met(z.matched),'excess_matched':met(net)['cagr']-met(z.matched)['cagr'],'positive_matched_folds':sum(f['matched_excess']>0 for f in folds),'folds':folds,'months':len(z)}
def main():
 d=yf.download(list(U),start='2005-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna(how='all').astype(float); last=pd.Timestamp(d.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cut=last.to_period('M').start_time-pd.Timedelta(days=1); d=d.loc[d.index<=cut].dropna(); tests={}
 for omitted in ('NONE',)+U:
  syms=U if omitted=='NONE' else tuple(s for s in U if s!=omitted); q=run(d,syms); tests[omitted]={w:ev(q,s) for w,s in WINDOWS.items()}
 j=[tests[o]['2015'] for o in U]; survive=sum(x['excess_matched']>0 and x['positive_matched_folds']>=3 for x in j); dec='P46_UNIVERSE_JACKKNIFE_ROBUST' if survive>=4 else 'P46_UNIVERSE_JACKKNIFE_CONCENTRATED'; out={'schema':'research.p167_p46_universe_jackknife_r1','parent':'P46','adjudicator':'P167','hypothesis':'Frozen P46 matched alpha is not dependent on availability of any single member of SPY/QQQ/TLT/GLD/DBC.','contract':{'selector':'unchanged four-factor top-2','jackknife':'omit exactly one asset, no replacement','cost_bps':COST,'matched':'equal-weight same reduced universe','windows':list(WINDOWS),'folds':5,'predeclared_gate':'at least 4 of 5 leave-one-out variants positive matched excess with >=3/5 positive folds from 2015','no_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cut.date()),'panel_sha256':hashlib.sha256(d.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()},'tests':tests,'jackknife_survivors_2015':survive,'decision':dec}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p167_p46_universe_jackknife_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()

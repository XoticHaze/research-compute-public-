import json,math,hashlib
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
U=('XLK','XLF','XLE','XLV','XLI','XLY','XLP','XLU','XLB'); COSTS=(25,50,100); WINDOWS={'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}
def met(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); c=float(e.iloc[-1]**(12/len(r))-1); v=float(r.std(ddof=0)*math.sqrt(12)); return {'cagr':c,'sharpe':float(r.mean()*12/v) if v else None,'maxdd':float((e/e.cummax()-1).min())}
def run(close):
 m=close[list(U)+['SPY']].resample('ME').last(); sig=m[list(U)].shift(1)/m[list(U)].shift(12)-1; prev={s:0 for s in U}; rows=[]
 for i,x in enumerate(m.index[:-1]):
  s=sig.loc[x]
  if s.isna().any(): continue
  pick=sorted(U,key=lambda k:(-s[k],k))[:3]; w={k:(1/3 if k in pick else 0) for k in U}; n=m.index[i+1]; rr=m.loc[n,list(U)]/m.loc[x,list(U)]-1
  if rr.isna().any() or pd.isna(m.loc[n,'SPY']) or pd.isna(m.loc[x,'SPY']): continue
  turn=.5*sum(abs(w[k]-prev[k]) for k in U); rows.append({'date':n,'gross':sum(w[k]*rr[k] for k in U),'turn':turn,'matched':float(rr.mean()),'spy':float(m.loc[n,'SPY']/m.loc[x,'SPY']-1)}); prev=w
 return pd.DataFrame(rows).set_index('date')
def ev(q,start,cost):
 z=q.loc[pd.Timestamp(start):]; net=z.gross-z.turn*cost/10000; c=met(net); mm=met(z.matched); sp=met(z.spy); folds=[]
 for i,ix in enumerate(np.array_split(np.arange(len(z)),5),1):
  a=z.iloc[ix]; n=a.gross-a.turn*cost/10000; folds.append({'fold':i,'matched_excess':met(n)['cagr']-met(a.matched)['cagr'],'spy_excess':met(n)['cagr']-met(a.spy)['cagr']})
 return {'months':len(z),'candidate':c,'matched':mm,'spy':sp,'excess_matched':c['cagr']-mm['cagr'],'excess_spy':c['cagr']-sp['cagr'],'positive_matched_folds':sum(f['matched_excess']>0 for f in folds),'positive_spy_folds':sum(f['spy_excess']>0 for f in folds),'folds':folds}
def main():
 syms=list(U)+['SPY']; d=yf.download(syms,start='2004-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna(how='all').astype(float); last=pd.Timestamp(d.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cut=last.to_period('M').start_time-pd.Timedelta(days=1); d=d.loc[d.index<=cut].dropna(); q=run(d); tests={str(c):{w:ev(q,s,c) for w,s in WINDOWS.items()} for c in COSTS}; p=tests['50']['2015']; decision='P171_SECTOR_12M1M_MOMENTUM_SURVIVOR' if p['excess_matched']>0 and p['excess_spy']>0 and p['positive_matched_folds']>=3 else 'P171_SECTOR_12M1M_MOMENTUM_REJECT'; out={'schema':'research.p171_sector_12m1m_momentum_r1','parent':'P171','hypothesis':'Medium-horizon cross-sectional sector momentum excluding the most recent month creates durable after-cost excess beyond passive sector exposure and SPY.','contract':{'universe':U,'signal':'12-to-1 month momentum using completed month-ends','portfolio':'equal-weight top 3 sectors for next month','cost_bps':COSTS,'primary_cost_bps':50,'matched':'equal-weight same sector universe','opportunity_control':'SPY','windows':WINDOWS,'folds':5,'predeclared_gate':'2015+ at 50 bps must have positive matched and SPY excess with >=3/5 positive matched folds','no_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cut.date()),'panel_sha256':hashlib.sha256(d.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()},'tests':tests,'decision':decision}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p171_sector_12m1m_momentum_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()

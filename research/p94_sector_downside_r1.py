import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
S=['XLB','XLE','XLF','XLI','XLK','XLP','XLU','XLV','XLY']; A=S+['SPY']; C=(25,50,100)
def cg(x):
 x=pd.Series(x,dtype=float).dropna(); return float((1+x).prod()**(12/len(x))-1)
def mt(x):
 x=pd.Series(x,dtype=float).dropna(); e=(1+x).cumprod(); v=float(x.std(ddof=1)*math.sqrt(12)); a=float(x.mean()*12); return {'cagr':cg(x),'sharpe':a/v,'maxdd':float((e/e.cummax()-1).min())}
def main():
 c=yf.download(A,start='1999-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna().astype(float); last=pd.Timestamp(c.index.max()); last=last.tz_localize(None) if last.tzinfo else last; m=c.resample('ME').last(); m=m[m.index<=last.to_period('M').start_time-pd.Timedelta(days=1)]; mr=m.pct_change(); z=[]
 for i in range(12,len(m)-1):
  d=m.index[i]; n=m.index[i+1]
  for s in S:
   rn=float(m.loc[n,s]/m.loc[d,s]-1); q={'date':d,'sector':s,'y':int(rn<0),'next':rn,'spy':float(m.loc[n,'SPY']/m.loc[d,'SPY']-1)}
   for h in (1,3,6,12): q[f'r{h}']=float(m.loc[d,s]/m.iloc[i-h][s]-1); q[f'x{h}']=q[f'r{h}']-float(m.loc[d,'SPY']/m.iloc[i-h]['SPY']-1)
   q['v6']=float(mr[s].iloc[i-5:i+1].std()); q['sv6']=float(mr.SPY.iloc[i-5:i+1].std()); z.append(q)
 p=pd.DataFrame(z); F=[f'{k}{h}' for h in (1,3,6,12) for k in ('r','x')]+['v6','sv6']; ds=sorted(p.date.unique()); rows=[]; prev=np.ones(len(S))/len(S)
 for i in range(60,len(ds)):
  d=ds[i]; tr=p[p.date<d]; q=p[p.date==d].copy(); model=make_pipeline(StandardScaler(),LogisticRegression(C=1,max_iter=1000,class_weight='balanced',random_state=31)); model.fit(tr[F],tr.y); q['prob']=model.predict_proba(q[F])[:,1]; chosen=set(q.nsmallest(3,'prob').sector); w=np.array([1/3 if s in chosen else 0 for s in S]); r=q.set_index('sector').loc[S,'next'].to_numpy(); turn=.5*abs(w-prev).sum(); rows.append({'date':d,'gross':float(w@r),'turn':float(turn),'matched':float(r.mean()),'spy':float(q.spy.iloc[0])}); prev=w
 f=pd.DataFrame(rows).set_index('date'); out={'schema':'research.p94_sector_downside_r1','parent':'P94','contract':{'target':'next month negative return','model':'fixed expanding logistic','features':F,'allocation':'three lowest predicted downside probabilities','matched':'static equal-weight sectors','costs_bps':list(C),'no_search':True},'tests':{}}
 for name,start in [('all',None),('2015','2015-01-01'),('2020','2020-01-01')]:
  q=f if start is None else f.loc[start:]; d={'months':len(q),'matched':mt(q.matched),'spy':mt(q.spy),'costs':{}}; folds=np.array_split(np.arange(len(q)),5)
  for bp in C:
   net=q.gross-q.turn*bp/10000; cm=mt(net); d['costs'][str(bp)]={'candidate':cm,'excess_matched':cm['cagr']-d['matched']['cagr'],'excess_spy':cm['cagr']-d['spy']['cagr'],'sharpe_delta':cm['sharpe']-d['matched']['sharpe'],'dd_delta':cm['maxdd']-d['matched']['maxdd'],'positive_folds':sum(cg((q.iloc[ix].gross-q.iloc[ix].turn*bp/10000))-cg(q.iloc[ix].matched)>0 for ix in folds)}
  out['tests'][name]=d
 q=out['tests']['2020']['costs']['50']; out['decision']='SUPPORTED' if q['excess_matched']>0 and q['positive_folds']>=3 and q['sharpe_delta']>0 else 'NOT_SUPPORTED'; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p94_sector_downside_r1.json').write_text(json.dumps(out,indent=2)); print(json.dumps(out))
if __name__=='__main__': main()

import json,math,hashlib
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
U=('XLK','XLF','XLE','XLV','XLI','XLY','XLP','XLU','XLB'); CASH='BIL'; COSTS=(25,50,100); WINDOWS={'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}
def met(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); c=float(e.iloc[-1]**(12/len(r))-1); v=float(r.std(ddof=0)*math.sqrt(12)); return {'cagr':c,'sharpe':float(r.mean()*12/v) if v else None,'maxdd':float((e/e.cummax()-1).min())}
def run(close):
 m=close[list(U)+[CASH,'SPY']].resample('ME').last(); sma=close[list(U)].rolling(200,min_periods=200).mean().resample('ME').last(); prev={s:0 for s in list(U)+[CASH]}; rows=[]
 for i,x in enumerate(m.index[:-1]):
  if x not in sma.index or sma.loc[x].isna().any(): continue
  on=[s for s in U if m.loc[x,s]>sma.loc[x,s]]; w={s:(1/len(U) if s in on else 0) for s in U}; w[CASH]=1-sum(w.values()); n=m.index[i+1]; rr=m.loc[n,list(U)+[CASH]]/m.loc[x,list(U)+[CASH]]-1
  if rr.isna().any() or pd.isna(m.loc[n,'SPY']) or pd.isna(m.loc[x,'SPY']): continue
  turn=.5*sum(abs(w[s]-prev[s]) for s in prev); rows.append({'date':n,'gross':sum(w[s]*rr[s] for s in prev),'turn':turn,'matched':float((m.loc[n,list(U)]/m.loc[x,list(U)]-1).mean()),'spy':float(m.loc[n,'SPY']/m.loc[x,'SPY']-1),'breadth':len(on)/len(U)}); prev=w
 return pd.DataFrame(rows).set_index('date')
def ev(q,start,cost):
 z=q.loc[pd.Timestamp(start):]; net=z.gross-z.turn*cost/10000; c=met(net); mm=met(z.matched); sp=met(z.spy); folds=[]
 for i,ix in enumerate(np.array_split(np.arange(len(z)),5),1):
  a=z.iloc[ix]; n=a.gross-a.turn*cost/10000; folds.append({'fold':i,'matched_excess':met(n)['cagr']-met(a.matched)['cagr'],'spy_excess':met(n)['cagr']-met(a.spy)['cagr']})
 return {'months':len(z),'candidate':c,'matched':mm,'spy':sp,'excess_matched':c['cagr']-mm['cagr'],'excess_spy':c['cagr']-sp['cagr'],'positive_matched_folds':sum(f['matched_excess']>0 for f in folds),'positive_spy_folds':sum(f['spy_excess']>0 for f in folds),'mean_risk_on_fraction':float(z.breadth.mean()),'folds':folds}
def main():
 syms=list(U)+[CASH,'SPY']; d=yf.download(syms,start='2007-06-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna(how='all').astype(float); last=pd.Timestamp(d.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cut=last.to_period('M').start_time-pd.Timedelta(days=1); d=d.loc[d.index<=cut].dropna(); q=run(d); tests={str(c):{w:ev(q,s,c) for w,s in WINDOWS.items()} for c in COSTS}; p=tests['50']['2015']; decision='P172_SECTOR_TREND_BREADTH_SURVIVOR' if p['excess_matched']>0 and p['excess_spy']>0 and p['positive_matched_folds']>=3 else 'P172_SECTOR_TREND_BREADTH_REJECT'; out={'schema':'research.p172_sector_trend_breadth_r1','parent':'P172','hypothesis':'Independent absolute-trend breadth across sectors can avoid enough sector drawdowns to produce durable after-cost excess while idle capital earns a T-bill proxy.','contract':{'universe':U,'cash_proxy':CASH,'signal':'each sector above its own trailing 200-session SMA at completed month-end','portfolio':'1/9 weight per trend-positive sector; residual weight BIL; monthly rebalance','cost_bps':COSTS,'primary_cost_bps':50,'matched':'equal-weight same nine-sector universe','opportunity_control':'SPY','windows':WINDOWS,'folds':5,'predeclared_gate':'2015+ at 50 bps must have positive matched and SPY CAGR excess with >=3/5 positive matched folds','no_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cut.date()),'panel_sha256':hashlib.sha256(d.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()},'tests':tests,'decision':decision}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p172_sector_trend_breadth_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()

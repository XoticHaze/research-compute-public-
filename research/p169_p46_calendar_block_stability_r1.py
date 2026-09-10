import json,math,hashlib
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
U=('SPY','QQQ','TLT','GLD','DBC'); COST=50
BLOCKS={'2015_2018':('2015-01-01','2018-12-31'),'2019_2022':('2019-01-01','2022-12-31'),'2023_present':('2023-01-01',None)}
def met(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); c=float(e.iloc[-1]**(12/len(r))-1); v=float(r.std(ddof=0)*math.sqrt(12)); return {'cagr':c,'sharpe':float(r.mean()*12/v) if v else None,'maxdd':float((e/e.cummax()-1).min())}
def run(close):
 m=close[list(U)].resample('ME').last(); dr=close[list(U)].pct_change(fill_method=None); vol=(dr.rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last(); tr=(close[list(U)]/close[list(U)].rolling(200,min_periods=160).mean()-1).resample('ME').last(); dd=(close[list(U)]/close[list(U)].rolling(126,min_periods=100).max()-1).resample('ME').last(); mom=m.pct_change(6); prev={s:0 for s in U}; rows=[]
 for i,x in enumerate(m.index[:-1]):
  z=pd.DataFrame({'m':mom.loc[x,list(U)],'t':tr.loc[x,list(U)],'v':-vol.loc[x,list(U)],'d':dd.loc[x,list(U)]},index=list(U))
  if z.isna().any().any(): continue
  score=z.rank(axis=0,pct=True,method='average').mean(axis=1); pick=sorted(U,key=lambda s:(-score[s],s))[:2]; w={s:(.5 if s in pick else 0) for s in U}; n=m.index[i+1]; rr=m.loc[n]/m.loc[x]-1
  if rr.isna().any(): continue
  turn=.5*sum(abs(w[s]-prev[s]) for s in U); rows.append({'date':n,'gross':sum(w[s]*rr[s] for s in U),'turn':turn,'matched':float(rr.mean()),'spy':float(rr['SPY']),'qqq':float(rr['QQQ'])}); prev=w
 return pd.DataFrame(rows).set_index('date')
def ev(q,start,end):
 z=q.loc[pd.Timestamp(start):] if end is None else q.loc[pd.Timestamp(start):pd.Timestamp(end)]; net=z.gross-z.turn*COST/10000
 c=met(net); mm=met(z.matched); sp=met(z.spy); qq=met(z.qqq)
 return {'months':len(z),'candidate':c,'matched':mm,'spy':sp,'qqq':qq,'excess_matched':c['cagr']-mm['cagr'],'excess_spy':c['cagr']-sp['cagr'],'excess_qqq':c['cagr']-qq['cagr']}
def main():
 d=yf.download(list(U),start='2005-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna(how='all').astype(float); last=pd.Timestamp(d.index.max()); last=last.tz_localize(None) if last.tzinfo else last; cut=last.to_period('M').start_time-pd.Timedelta(days=1); d=d.loc[d.index<=cut].dropna(); q=run(d); tests={k:ev(q,*v) for k,v in BLOCKS.items()}; positive=sum(v['excess_matched']>0 for v in tests.values()); decision='P46_CALENDAR_BLOCK_STABLE' if positive==3 else 'P46_CALENDAR_BLOCK_INSTABILITY'; out={'schema':'research.p169_p46_calendar_block_stability_r1','parent':'P46','adjudicator':'P169','hypothesis':'Frozen P46 after-cost matched alpha persists across non-overlapping calendar regimes rather than being concentrated in one evaluation era.','contract':{'selector':'unchanged P46 four-factor top-2','cost_bps':COST,'blocks':BLOCKS,'matched':'same-universe equal-weight','opportunity_controls':['SPY','QQQ'],'predeclared_gate':'positive matched excess in all three non-overlapping blocks','no_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_complete_month_end':str(cut.date()),'panel_sha256':hashlib.sha256(d.reset_index().to_csv(index=False,float_format='%.10g').encode()).hexdigest()},'tests':tests,'positive_matched_blocks':positive,'decision':decision}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p169_p46_calendar_block_stability_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()

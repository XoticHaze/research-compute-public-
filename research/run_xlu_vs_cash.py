from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import numpy as np
import pandas as pd

START='2014-01-01'; END='2026-09-03'; SYMBOLS=('AMAT','APH','XLU'); LOOKBACK=20; HORIZON=10; DELAY=1; TAIL=.30; FOLDS=6; MIN_TRAIN=756; PURGE=12; COST_BPS=25.; VOL_LOOKBACK=252

def epoch(x): return int(datetime.fromisoformat(x).replace(tzinfo=timezone.utc).timestamp())
def load(s):
 q=urlencode({'period1':epoch(START),'period2':epoch(END),'interval':'1d','events':'history','includeAdjustedClose':'true'})
 req=Request(f'https://query1.finance.yahoo.com/v8/finance/chart/{s}?{q}',headers={'User-Agent':'Mozilla/5.0 research-compute/1.0'})
 with urlopen(req,timeout=30) as r: p=json.loads(r.read().decode())
 z=(p.get('chart',{}).get('result') or [None])[0]; ts=z.get('timestamp') or []; ind=z.get('indicators',{}); a=(ind.get('adjclose') or [{}])[0].get('adjclose'); c=a or (ind.get('quote') or [{}])[0].get('close')
 f=pd.DataFrame({'timestamp':pd.to_datetime(ts,unit='s',utc=True),'price':pd.to_numeric(pd.Series(c),errors='coerce')}).dropna().sort_values('timestamp').drop_duplicates('timestamp',keep='last').reset_index(drop=True); f['signal']=f.price.pct_change(LOOKBACK); return f.dropna().reset_index(drop=True)
def folds(n):
 e=np.linspace(MIN_TRAIN,n-(HORIZON+DELAY),FOLDS+1,dtype=int); return [(int(e[i]),int(e[i+1])) for i in range(FOLDS)]
def trades(s,f):
 out=[]
 for k,(st,sp) in enumerate(folds(len(f)),1):
  th=float(f.iloc[:st-PURGE].signal.quantile(1-TAIL)); nxt=st+DELAY
  for i in range(st,sp):
   en=i+DELAY; ex=en+HORIZON
   if en<nxt or ex>=sp or float(f.at[i,'signal'])<th: continue
   out.append({'symbol':s,'fold':k,'entry_timestamp':f.at[en,'timestamp'],'exit_timestamp':f.at[ex,'timestamp']}); nxt=ex
 return out
def leg(f,t):
 px=f.set_index('timestamp').price; d=px.pct_change().fillna(0); pnl=pd.Series(0.,index=d.index)
 for x in t:
  m=(pnl.index>x['entry_timestamp'])&(pnl.index<=x['exit_timestamp']); pnl.loc[m]+=d.loc[m]
  if x['exit_timestamp'] in pnl.index: pnl.loc[x['exit_timestamp']]-=COST_BPS/10000
 return pnl
def weights(raw,syms,cut):
 v={s:float(raw[s].loc[raw[s].index<cut].tail(VOL_LOOKBACK).std(ddof=1)) for s in syms}; inv={s:1/x for s,x in v.items()}; z=sum(inv.values()); return {s:inv[s]/z for s in syms}
def metrics(r):
 r=r.fillna(0); eq=(1+r).cumprod(); yrs=len(r)/252; ar=float(eq.iloc[-1]**(1/yrs)-1) if yrs>0 and eq.iloc[-1]>0 else None; av=float(r.std(ddof=1)*np.sqrt(252)); dd=float((eq/eq.cummax()-1).min()); return {'days':len(r),'total_return':float(eq.iloc[-1]-1),'annualized_return':ar,'annualized_volatility':av,'return_over_volatility':ar/av if ar is not None and av>0 else None,'max_drawdown':dd,'sum_return_bps':float(r.sum()*10000)}
def main():
 fs={s:load(s) for s in SYMBOLS}; ts={s:trades(s,fs[s]) for s in SYMBOLS}; ls={s:leg(fs[s],ts[s]) for s in SYMBOLS}; raw={s:fs[s].set_index('timestamp').price.pct_change().dropna() for s in SYMBOLS}; cal=ls['AMAT'].index.union(ls['APH'].index).union(ls['XLU'].index).sort_values(); ls={s:ls[s].reindex(cal,fill_value=0.) for s in SYMBOLS}; cash=pd.Series(0.,index=cal); div=pd.Series(0.,index=cal); rows=[]
 for k in range(1,FOLDS+1):
  ent=[x for s in SYMBOLS for x in ts[s] if x['fold']==k]; lo=min(x['entry_timestamp'] for x in ent); hi=max(x['exit_timestamp'] for x in ent); m=(cal>=lo)&(cal<=hi); w=weights(raw,SYMBOLS,lo); cash.loc[m]=w['AMAT']*ls['AMAT'].loc[m]+w['APH']*ls['APH'].loc[m]; div.loc[m]=cash.loc[m]+w['XLU']*ls['XLU'].loc[m]; c=float(cash.loc[m].sum()); d=float(div.loc[m].sum()); rows.append({'fold':k,'weights':w,'cash_control_sum_return_bps':c*10000,'diversified_sum_return_bps':d*10000,'xlu_incremental_bps':(d-c)*10000,'xlu_increment_positive':d>c})
 cm=metrics(cash); dm=metrics(div); pos=sum(x['xlu_increment_positive'] for x in rows); cw=min(x['cash_control_sum_return_bps'] for x in rows); dw=min(x['diversified_sum_return_bps'] for x in rows); passed=dm['total_return']>cm['total_return'] and pos>=4 and dm['max_drawdown']>=cm['max_drawdown'] and (dm['return_over_volatility']>cm['return_over_volatility'] or dw>cw); out={'schema':'foundry.research.amat_aph_xlu_vs_cash_derisk.v1','source_contract':'research-foundry PR #93 frozen executable, public compute transport only','cash_control':cm,'diversified_with_xlu':dm,'folds':rows,'gate':{'positive_xlu_increment_folds':pos,'cash_control_worst_fold_bps':cw,'diversified_worst_fold_bps':dw,'passed':bool(passed),'decision':'retain_xlu_as_true_diversifier_beyond_derisking' if passed else 'do_not_claim_xlu_value_beyond_derisking'}}; Path('result.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n'); print(json.dumps(out,indent=2,sort_keys=True))
if __name__=='__main__': main()

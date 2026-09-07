from __future__ import annotations
import io,json,math,hashlib
from datetime import datetime,timezone
from urllib.parse import urlencode
from urllib.request import Request,urlopen
import numpy as np
import pandas as pd
START='1999-01-01'; END='2026-09-08'; SYMBOLS=['SMH','QQQ','SPY']; LAG_DAYS=7; DELTA_OBS=63; COSTS=[10.0,25.0,50.0]; PRIMARY=25.0; OUT='p17-term-spread-semiconductor-switch-receipt.json'; FRED='https://fred.stlouisfed.org/graph/fredgraph.csv?id=T10Y2Y&cosd=1999-01-01&coed=2026-09-08'
def epoch(s): return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp())
def fetch(url,timeout=60):
 r=Request(url,headers={'User-Agent':'Mozilla/5.0 research-compute/1.0'}); raw=urlopen(r,timeout=timeout).read();
 if not raw: raise RuntimeError('empty '+url)
 return raw
def price(sym):
 q=urlencode({'period1':epoch(START),'period2':epoch(END),'interval':'1d','events':'history','includeAdjustedClose':'true'})
 p=json.loads(fetch(f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?{q}',30))['chart']['result'][0]
 idx=pd.to_datetime(p['timestamp'],unit='s',utc=True); ind=p['indicators']; vals=(ind.get('adjclose') or [{}])[0].get('adjclose') or (ind.get('quote') or [{}])[0].get('close')
 s=pd.Series(pd.to_numeric(pd.Series(vals),errors='coerce').to_numpy(),index=idx,name=sym).dropna(); return s[~s.index.duplicated(keep='last')].sort_index()
def term_spread():
 raw=fetch(FRED); f=pd.read_csv(io.BytesIO(raw),na_values=['.']); dc='DATE' if 'DATE' in f else f.columns[0]; vc='T10Y2Y'; idx=pd.to_datetime(f[dc],utc=True,errors='coerce'); val=pd.to_numeric(f[vc],errors='coerce'); s=pd.Series(val.to_numpy(),index=idx,name=vc).dropna().sort_index(); return s[~s.index.duplicated(keep='last')],hashlib.sha256(raw).hexdigest()
def month_ends(frame): return [i for i in range(len(frame)-1) if frame.index[i].month!=frame.index[i+1].month]
def summary(rows):
 eq=1.0; peak=1.0; dd=0.0; yrs={}; rets=[]
 for d,r in rows:
  eq*=1+r; peak=max(peak,eq); dd=min(dd,eq/peak-1); yrs[str(d.year)]=yrs.get(str(d.year),1.0)*(1+r); rets.append(r)
 span=max((rows[-1][0]-rows[0][0]).days/365.25,1/12); cagr=eq**(1/span)-1; vol=float(np.std(rets,ddof=1)*math.sqrt(12)) if len(rets)>1 else 0
 return {'periods':len(rows),'cagr':cagr,'total_return':eq-1,'max_drawdown':dd,'annualized_volatility':vol,'year_returns':{y:v-1 for y,v in sorted(yrs.items())}}
def main():
 ps={s:price(s) for s in SYMBOLS}; common=pd.DatetimeIndex(sorted(set.intersection(*[set(x.index) for x in ps.values()]))); frame=pd.DataFrame({s:x.reindex(common) for s,x in ps.items()}).dropna(); ts,fred_sha=term_spread(); me=month_ends(frame); decisions=[]
 for n,i in enumerate(me[:-1]):
  j=me[n+1]; d=frame.index[i]; avail=ts.loc[ts.index<=d-pd.Timedelta(days=LAG_DAYS)]
  if len(avail)<=DELTA_OBS: continue
  cur=float(avail.iloc[-1]); delta=cur-float(avail.iloc[-1-DELTA_OBS]); selected='SMH' if cur>0 and delta>0 else 'QQQ'; decisions.append((i,j,d,avail.index[-1],cur,delta,selected))
 if len(decisions)<180: raise RuntimeError(f'insufficient decisions {len(decisions)}')
 policy={c:[] for c in COSTS}; base={s:[] for s in SYMBOLS}; base['equal_SMH_QQQ']=[]; prev=None; turns=[]
 for i,j,d,cut,cur,delta,sel in decisions:
  turn=0.0 if prev==sel else 1.0; turns.append(turn); gross=float(frame[sel].iloc[j]/frame[sel].iloc[i]-1)
  for c in COSTS: policy[c].append((frame.index[j],gross-turn*c/10000))
  prev=sel
  for s in SYMBOLS: base[s].append((frame.index[j],float(frame[s].iloc[j]/frame[s].iloc[i]-1)))
  base['equal_SMH_QQQ'].append((frame.index[j],0.5*float(frame.SMH.iloc[j]/frame.SMH.iloc[i]-1)+0.5*float(frame.QQQ.iloc[j]/frame.QQQ.iloc[i]-1)))
 sums={'term_spread_switch':{str(int(c)):summary(policy[c]) for c in COSTS},**{k:summary(v) for k,v in base.items()}}; p=sums['term_spread_switch'][str(int(PRIMARY))]; smh=sums['SMH']; qqq=sums['QQQ']; equal=sums['equal_SMH_QQQ']; years=sorted(set(p['year_returns'])&set(smh['year_returns'])&set(qqq['year_returns'])); first=str(frame.index[decisions[0][0]].year); last=str(frame.index[decisions[-1][1]].year); full=[y for y in years if y not in {first,last}]; wins_q=sum(p['year_returns'][y]>qqq['year_returns'][y] for y in full); wins_s=sum(p['year_returns'][y]>smh['year_returns'][y] for y in full); cost_rob=all(sums['term_spread_switch'][str(int(c))]['cagr']>qqq['cagr'] for c in COSTS); supported=p['cagr']>equal['cagr'] and p['cagr']>qqq['cagr'] and wins_q>=math.ceil(0.6*len(full)) and wins_s>=math.ceil(0.5*len(full)) and cost_rob
 receipt={'schema':'public_compute.p17_term_spread_semiconductor_switch.v1','decision':'P17_TERM_SPREAD_SWITCH_SUPPORTED' if supported else 'P17_TERM_SPREAD_SWITCH_NOT_SUPPORTED','frozen_rule':{'series':'T10Y2Y','publication_lag_days':LAG_DAYS,'delta_observations':DELTA_OBS,'select_smh_when':'spread > 0 and 63-observation delta > 0','otherwise':'QQQ'},'provenance':{'fred_url':FRED,'fred_sha256':fred_sha,'fred_first':ts.index.min().isoformat(),'fred_last':ts.index.max().isoformat(),'fred_rows':len(ts)},'window':{'first_decision':decisions[0][2].isoformat(),'last_decision':decisions[-1][2].isoformat(),'decisions':len(decisions),'full_years':len(full)},'metrics':sums,'primary_cost_bps':PRIMARY,'excess_cagr_pp':{'vs_equal':100*(p['cagr']-equal['cagr']),'vs_SMH':100*(p['cagr']-smh['cagr']),'vs_QQQ':100*(p['cagr']-qqq['cagr'])},'annual_consistency':{'wins_vs_QQQ':wins_q,'wins_vs_SMH':wins_s,'full_years':len(full)},'turnover':{'mean_one_way':float(np.mean(turns)),'switches':int(sum(x>0 for x in turns))},'cost_robust_vs_QQQ':cost_rob,'safety':{'allocation_authority_changed':False,'runtime_changed':False,'live_trading_changed':False}}
 open(OUT,'w',encoding='utf-8').write(json.dumps(receipt,indent=2,sort_keys=True)); print(json.dumps(receipt,sort_keys=True));
if __name__=='__main__': main()

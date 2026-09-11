from __future__ import annotations
import json,time,urllib.request
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf,pitindex
PIN='2df030e5c9be7c83cf4b28c3d8597d74d274757e'; YEARS=list(range(2018,2025)); N=40; COST=.0025
UA='CommandCenter MarketResearch P388 turnover research@example.invalid'; OUT=Path('research/artifacts/p388_pit_asset_turnover_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
def cf(cik):
 req=urllib.request.Request(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json',headers={'User-Agent':UA,'Accept':'application/json'}); return json.loads(urllib.request.urlopen(req,timeout=30).read().decode())
def turnover(facts,asof):
 g=facts.get('facts',{}).get('us-gaap',{}); rev=[]
 for concept in ['RevenueFromContractWithCustomerExcludingAssessedTax','Revenues','SalesRevenueNet']:
  for v in g.get(concept,{}).get('units',{}).get('USD',[]):
   if v.get('form')=='10-K' and v.get('start') and v.get('end') and v.get('filed') and v['filed']<=asof and v['end']<=asof and v.get('val') is not None:
    try: days=(pd.Timestamp(v['end'])-pd.Timestamp(v['start'])).days
    except Exception: continue
    if 300<=days<=430: rev.append((v['filed'],v['end'],float(v['val'])))
 if not rev:return None
 r=max(rev,key=lambda x:(x[0],x[1])); assets=[]
 for v in g.get('Assets',{}).get('units',{}).get('USD',[]):
  if v.get('form')=='10-K' and not v.get('start') and v.get('end')==r[1] and v.get('filed') and v['filed']<=asof and v.get('val') is not None: assets.append((v['filed'],float(v['val'])))
 if not assets:return None
 a=max(assets,key=lambda x:x[0])[1]; return None if a<=0 else r[2]/a
def returns(tickers,start,end):
 raw=yf.download(tickers,start=start,end=end,auto_adjust=True,progress=False,threads=False)
 if raw.empty:return {}; c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
 c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
 if isinstance(c,pd.Series): c=c.to_frame(tickers[0])
 out={}
 for t in tickers:
  if t in c.columns:
   s=c[t].dropna()
   if len(s)>=2: out[t]=float(s.iloc[-1]/s.iloc[0]-1)
 return out
cache={}; cohorts=[]
for y in YEARS:
 asof=f'{y}-06-30'; u=pitindex.get_constituents(asof,index='sp500')[['ticker','cik']].copy(); u['ticker']=u.ticker.astype(str).str.upper().str.replace('.','-',regex=False); u['cik']=pd.to_numeric(u.cik,errors='coerce'); u=u.dropna().sort_values('ticker').drop_duplicates('ticker'); idx=[round(i*(len(u)-1)/(N-1)) for i in range(N)]; s=u.iloc[idx].drop_duplicates('ticker'); feats=[]
 for _,r in s.iterrows():
  cik=int(r.cik)
  try:
   if cik not in cache: cache[cik]=cf(cik); time.sleep(.06)
   v=turnover(cache[cik],asof)
   if v is not None: feats.append((r.ticker,v))
  except Exception: pass
 tick=[t for t,_ in feats]; rets=returns(tick+['SPY'],f'{y}-07-01',f'{y+1}-07-10'); usable=sorted([(t,v) for t,v in feats if t in rets],key=lambda x:x[1]); k=max(1,len(usable)//4); top=usable[-k:] if usable else []; fr=len(feats)/len(s); pr=len(usable)/len(s); ready=fr>=.80 and pr>=.80 and len(top)>=8 and 'SPY' in rets
 if ready: cand=float(np.mean([rets[t] for t,_ in top]))-COST; ctl=float(np.mean([rets[t] for t,_ in usable]))-COST; spy=rets['SPY']-COST
 else: cand=ctl=spy=None
 cohorts.append({'year':y,'sample_n':len(s),'feature_n':len(feats),'usable_n':len(usable),'feature_rate':fr,'price_rate':pr,'selected_n':len(top),'ready':ready,'candidate_return':cand,'same_universe_control_return':ctl,'spy_return':spy,'excess_vs_control':None if not ready else cand-ctl,'excess_vs_spy':None if not ready else cand-spy,'selected':[t for t,_ in top]})
valid=[x for x in cohorts if x['ready']]; all_ready=len(valid)==7; pc=sum(x['excess_vs_control']>0 for x in valid); ps=sum(x['excess_vs_spy']>0 for x in valid)
if all_ready: cg=float(np.prod([1+x['candidate_return'] for x in valid])**(1/7)-1); bg=float(np.prod([1+x['same_universe_control_return'] for x in valid])**(1/7)-1); sg=float(np.prod([1+x['spy_return'] for x in valid])**(1/7)-1)
else: cg=bg=sg=None
support=all_ready and pc>=5 and ps>=4 and cg>bg and cg>sg
decision='P388_PIT_ASSET_TURNOVER_SUPPORTED' if support else ('P388_PIT_ASSET_TURNOVER_NOT_SUPPORTED' if all_ready else 'P388_PIT_ASSET_TURNOVER_DATA_NOT_READY')
out={'schema':'research.p388_pit_asset_turnover_r1.v1','workload_id':'P388_PIT_ASSET_TURNOVER_R1','parent':'P388_POINT_IN_TIME_FUNDAMENTAL_SELECTION','membership_source':{'repository':'arielNacamulli/pitindex','pinned_commit':PIN},'contract':{'years':YEARS,'sample_n':N,'feature':'latest filed-at annual revenue / same-period positive Assets','portfolio':'top quartile','cost_bps':25,'coverage_min':.80,'matched_controls':['equal-weight same PIT sample','SPY'],'support_rule':'all 7 ready; >=5/7 positive vs same-universe; >=4/7 positive vs SPY; compounded CAGR > both; no rescue'},'cohorts':cohorts,'summary':{'ready_years':len(valid),'positive_vs_control_years':pc,'positive_vs_spy_years':ps,'candidate_cagr':cg,'control_cagr':bg,'spy_cagr':sg,'excess_cagr_vs_control':None if cg is None else cg-bg,'excess_cagr_vs_spy':None if cg is None else cg-sg},'decision':decision,'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'summary':out['summary'],'coverage':{str(x['year']):[round(x['feature_rate'],2),round(x['price_rate'],2),x['ready']] for x in cohorts}},sort_keys=True))
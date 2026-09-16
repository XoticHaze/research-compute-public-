from __future__ import annotations
import json,re,time,urllib.request
from io import StringIO
from pathlib import Path
import numpy as np,pandas as pd,requests,yfinance as yf
UA='CommandCenter MarketResearch P463 research@example.invalid'; YEARS=list(range(2018,2025)); N=20; COST=.0025
OUT=Path('research/artifacts/p463_pit_profitability_alpha_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
def hist(target):
 p={'action':'query','format':'json','prop':'revisions','titles':'List of S&P 500 companies','rvprop':'ids|timestamp','rvlimit':'1','rvstart':target+'T23:59:59Z'}
 j=requests.get('https://en.wikipedia.org/w/api.php',params=p,headers={'User-Agent':UA},timeout=30).json(); rev=next(iter(j['query']['pages'].values()))['revisions'][0]
 h=requests.get(f"https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid={rev['revid']}",headers={'User-Agent':UA},timeout=30); h.raise_for_status()
 for t in pd.read_html(StringIO(h.text)):
  low={re.sub(r'[^a-z0-9]+','',str(c).lower()):c for c in t.columns}; sk=next((low[k] for k in low if k in ('symbol','ticker','tickersymbol')),None); ck=next((low[k] for k in low if 'cik' in k),None)
  if sk and ck:
   z=t[[sk,ck]].copy(); z.columns=['ticker','cik']; z['ticker']=z.ticker.astype(str).str.strip().str.upper().str.replace('.','-',regex=False); z['cik']=pd.to_numeric(z.cik,errors='coerce').astype('Int64'); return rev,z.dropna(subset=['cik']).sort_values('ticker')
 raise RuntimeError('NO_HIST_TABLE')
def cf(cik):
 req=urllib.request.Request(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json',headers={'User-Agent':UA,'Accept':'application/json'})
 return json.loads(urllib.request.urlopen(req,timeout=30).read().decode())
def annual_roa(facts,asof):
 g=facts.get('facts',{}).get('us-gaap',{}); ni=[]
 for concept in ['NetIncomeLoss','ProfitLoss']:
  for v in g.get(concept,{}).get('units',{}).get('USD',[]):
   if v.get('form')=='10-K' and v.get('start') and v.get('end') and v.get('filed') and v['filed']<=asof and v['end']<=asof:
    days=(pd.Timestamp(v['end'])-pd.Timestamp(v['start'])).days
    if 300<=days<=430: ni.append((v['filed'],v['end'],v.get('val'),concept,v.get('accn')))
 if not ni:return None
 n=max(ni,key=lambda x:(x[0],x[1])); end=n[1]; assets=[]
 for v in g.get('Assets',{}).get('units',{}).get('USD',[]):
  if v.get('form')=='10-K' and not v.get('start') and v.get('end')==end and v.get('filed') and v['filed']<=asof: assets.append((v['filed'],v.get('val'),v.get('accn')))
 if not assets:return None
 a=max(assets,key=lambda x:x[0]);
 if not a[1]:return None
 return {'roa':float(n[2])/float(a[1]),'ni':n[2],'assets':a[1],'period_end':end,'ni_filed':n[0],'assets_filed':a[0]}
def fwd_returns(tickers,start,end):
 if not tickers:return {}
 raw=yf.download(tickers,start=start,end=end,auto_adjust=True,progress=False,threads=False)
 if raw.empty:return {}
 c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
 if isinstance(c,pd.Series): c=c.to_frame(tickers[0])
 out={}
 for t in tickers:
  if t not in c.columns:continue
  s=c[t].dropna()
  if len(s)>=2: out[t]=float(s.iloc[-1]/s.iloc[0]-1)
 return out
cache={}; cohorts=[]
for y in YEARS:
 asof=f'{y}-06-30'; rev,z=hist(asof); idx=[round(i*(len(z)-1)/(N-1)) for i in range(N)]; s=z.iloc[idx].drop_duplicates('ticker')
 feats=[]
 for _,row in s.iterrows():
  cik=int(row.cik)
  try:
   if cik not in cache: cache[cik]=cf(cik); time.sleep(.08)
   f=annual_roa(cache[cik],asof)
   if f: feats.append({'ticker':row.ticker,'cik':str(cik),**f})
  except Exception: pass
 tick=[x['ticker'] for x in feats]; rets=fwd_returns(tick,f'{y}-07-01',f'{y+1}-07-10')
 usable=[x for x in feats if x['ticker'] in rets]; feature_rate=len(feats)/len(s); price_rate=len(usable)/len(s)
 usable=sorted(usable,key=lambda a:a['roa']); k=max(1,len(usable)//4); top=usable[-k:] if usable else []
 ready=feature_rate>=.80 and price_rate>=.80 and len(top)>=4
 if ready:
  cand=float(np.mean([rets[x['ticker']] for x in top]))-COST; ctl=float(np.mean([rets[x['ticker']] for x in usable]))-COST; excess=cand-ctl
 else: cand=ctl=excess=None
 cohorts.append({'year':y,'asof':asof,'revision_id':int(rev['revid']),'sample_n':len(s),'feature_n':len(feats),'usable_price_n':len(usable),'feature_rate':feature_rate,'price_rate':price_rate,'selected_n':len(top),'ready':ready,'candidate_return':cand,'same_universe_control_return':ctl,'after_cost_excess_return':excess,'selected_tickers':[x['ticker'] for x in top]})
valid=[x for x in cohorts if x['ready']]; pos=sum(x['after_cost_excess_return']>0 for x in valid); all_ready=len(valid)==len(YEARS)
if all_ready:
 cg=float(np.prod([1+x['candidate_return'] for x in valid])**(1/len(valid))-1); bg=float(np.prod([1+x['same_universe_control_return'] for x in valid])**(1/len(valid))-1); ex=cg-bg
else: cg=bg=ex=None
supported=all_ready and pos>=5 and ex is not None and ex>0
decision='PIT_PROFITABILITY_ALPHA_SUPPORTED' if supported else ('PIT_PROFITABILITY_ALPHA_NOT_SUPPORTED' if all_ready else 'PIT_PROFITABILITY_ALPHA_DATA_NOT_READY')
out={'schema':'research.p463_pit_profitability_alpha_r1.v1','workload_id':'P463_PIT_PROFITABILITY_ALPHA_R1','parent':'PIT_FUNDAMENTAL_CROSS_SECTIONAL_SELECTION','claim':'First causal economic discriminator after membership and SEC-feature gates: on fixed June-30 historical S&P universes, deterministic 20-name samples, rank by latest annual 10-K net-income/assets filed by rebalance date; compare top quartile forward 12-month adjusted return after fixed costs against equal-weight same-universe sample. No current membership, future filings, ticker dropping after returns, threshold/date/product tuning, or value-factor blending.','contract':{'years':YEARS,'sample_n':N,'sample_rule':'20 evenly spaced after ticker sort','feature':'latest causal annual 10-K NetIncomeLoss-or-ProfitLoss divided by Assets at same fiscal period end','portfolio':'top quartile ROA','matched_control':'equal-weight same deterministic historical sample','endpoint_cost_bps':25,'annual_feature_and_price_coverage_min':.80,'all_years_required':True},'cohorts':cohorts,'summary':{'ready_years':len(valid),'positive_excess_years':pos,'candidate_compound_cagr':cg,'control_compound_cagr':bg,'after_cost_excess_cagr':ex},'decision_rule':'Support only if every fixed year clears >=80% causal feature and price coverage, >=5/7 annual cohorts have positive after-cost same-universe excess, and compounded candidate CAGR exceeds the same-universe control. Otherwise reject or classify data-not-ready; no rescue.','decision':decision,'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'summary':out['summary'],'coverage':{str(x['year']):[round(x['feature_rate'],2),round(x['price_rate'],2),x['ready']] for x in cohorts}},sort_keys=True))
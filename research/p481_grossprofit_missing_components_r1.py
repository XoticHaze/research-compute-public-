from __future__ import annotations
import json,re,time,urllib.request
from io import StringIO
from pathlib import Path
import pandas as pd,requests
UA='CommandCenter MarketResearch P481 research@example.invalid'; YEARS=list(range(2018,2025)); N=20
REV=['RevenueFromContractWithCustomerExcludingAssessedTax','SalesRevenueNet','Revenues']; COGS=['CostOfRevenue','CostOfGoodsAndServicesSold','CostOfGoodsSold']
OUT=Path('research/artifacts/p481_grossprofit_missing_components_r1.json');OUT.parent.mkdir(parents=True,exist_ok=True)
def hist(target):
 p={'action':'query','format':'json','prop':'revisions','titles':'List of S&P 500 companies','rvprop':'ids|timestamp','rvlimit':'1','rvstart':target+'T23:59:59Z'};j=requests.get('https://en.wikipedia.org/w/api.php',params=p,headers={'User-Agent':UA},timeout=30).json();rev=next(iter(j['query']['pages'].values()))['revisions'][0]
 h=requests.get(f"https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid={rev['revid']}",headers={'User-Agent':UA},timeout=30);h.raise_for_status()
 for t in pd.read_html(StringIO(h.text)):
  low={re.sub(r'[^a-z0-9]+','',str(c).lower()):c for c in t.columns};sk=next((low[k] for k in low if k in ('symbol','ticker','tickersymbol')),None);ck=next((low[k] for k in low if 'cik' in k),None);nk=next((low[k] for k in low if k in ('security','company','companyname','name')),None)
  if sk and ck:
   cols=[sk,ck]+([nk] if nk else []);z=t[cols].copy();z.columns=['ticker','cik']+(['name'] if nk else []);z['ticker']=z.ticker.astype(str).str.strip().str.upper().str.replace('.','-',regex=False);z['cik']=pd.to_numeric(z.cik,errors='coerce').astype('Int64');return rev,z.dropna(subset=['cik']).sort_values('ticker')
 raise RuntimeError('NO_HIST_TABLE')
def cf(cik):
 req=urllib.request.Request(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json',headers={'User-Agent':UA,'Accept':'application/json'});return json.loads(urllib.request.urlopen(req,timeout=30).read().decode())
def annual(g,tag,asof):
 return [v for v in g.get(tag,{}).get('units',{}).get('USD',[]) if v.get('form')=='10-K' and v.get('start') and v.get('end') and v.get('filed') and v['filed']<=asof and v['end']<=asof and v.get('val') is not None and 300<=(pd.Timestamp(v['end'])-pd.Timestamp(v['start'])).days<=430]
def classify(facts,asof):
 g=facts.get('facts',{}).get('us-gaap',{});gp=annual(g,'GrossProfit',asof);rev=sum((annual(g,t,asof) for t in REV),[]);cogs=sum((annual(g,t,asof) for t in COGS),[]); common=bool(set(v['end'] for v in rev)&set(v['end'] for v in cogs))
 assets=[v for v in g.get('Assets',{}).get('units',{}).get('USD',[]) if v.get('form')=='10-K' and not v.get('start') and v.get('end') and v.get('filed') and v['filed']<=asof and v.get('val') is not None and float(v['val'])>0]
 flow_ends=sorted(set([v['end'] for v in gp]+list(set(v['end'] for v in rev)&set(v['end'] for v in cogs))))
 lagged=any(any(a['end']<e for a in assets) for e in flow_ends)
 return {'direct_grossprofit':bool(gp),'revenue':bool(rev),'cost':bool(cogs),'common_rev_cost_period':common,'assets':bool(assets),'lagged_assets_for_flow':lagged,'feature_possible':bool(flow_ends and lagged)}
cache={};coh=[];aggregate={}
for y in YEARS:
 asof=f'{y}-06-30';rev,z=hist(asof);idx=[round(i*(len(z)-1)/(N-1)) for i in range(N)];s=z.iloc[idx].drop_duplicates('ticker');rows=[]
 for _,r in s.iterrows():
  cik=int(r.cik)
  try:
   if cik not in cache:cache[cik]=cf(cik);time.sleep(.07)
   c=classify(cache[cik],asof);rows.append({'ticker':r.ticker,'name':str(r.get('name','')),'cik':str(cik),**c})
  except Exception as e:rows.append({'ticker':r.ticker,'name':str(r.get('name','')),'cik':str(cik),'fetch_error':type(e).__name__,'feature_possible':False})
 missing=[r for r in rows if not r['feature_possible']];coh.append({'year':y,'missing_n':len(missing),'missing':missing})
 for r in missing:
  key='fetch_error' if r.get('fetch_error') else ('no_gross_profit_flow' if not (r.get('direct_grossprofit') or r.get('common_rev_cost_period')) else 'no_lagged_assets')
  aggregate[key]=aggregate.get(key,0)+1
out={'schema':'research.p481_grossprofit_missing_components_r1.v1','workload_id':'P481_GROSSPROFIT_MISSING_COMPONENTS_R1','parent':'PIT_FUNDAMENTAL_CROSS_SECTIONAL_SELECTION','claim':'Classify why frozen-sample names fail prospective gross-profitability feature construction without reading forward prices or returns.','contract':{'years':YEARS,'sample_n':N,'returns_inspected':False,'price_data_inspected':False,'tags_frozen_from_P478':True},'aggregate_missing_reasons':aggregate,'cohorts':coh,'decision':'SOURCE_COMPONENT_DIAGNOSTIC_COMPLETE','scientific_consequence':'Use component evidence only to decide whether a principled non-performance-informed source repair exists; do not select new tags or exclude issuers from return feedback.','boundaries':{'performance_inspection':False,'constituent_drop':False,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False));print(json.dumps({'aggregate_missing_reasons':aggregate,'missing_names':{str(x['year']):[r['ticker'] for r in x['missing']] for x in coh}},sort_keys=True))
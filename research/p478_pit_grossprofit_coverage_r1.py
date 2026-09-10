from __future__ import annotations
import json,re,time,urllib.request
from io import StringIO
from pathlib import Path
import pandas as pd,requests
UA='CommandCenter MarketResearch P478 research@example.invalid'; YEARS=list(range(2018,2025)); N=20
REV_TAGS=['RevenueFromContractWithCustomerExcludingAssessedTax','SalesRevenueNet','Revenues']; COGS_TAGS=['CostOfRevenue','CostOfGoodsAndServicesSold','CostOfGoodsSold']; GP_TAG='GrossProfit'
OUT=Path('research/artifacts/p478_pit_grossprofit_coverage_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
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
 req=urllib.request.Request(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json',headers={'User-Agent':UA,'Accept':'application/json'}); return json.loads(urllib.request.urlopen(req,timeout=30).read().decode())
def annual(g,tag,asof):
 vals=[]
 for v in g.get(tag,{}).get('units',{}).get('USD',[]):
  if v.get('form')=='10-K' and v.get('start') and v.get('end') and v.get('filed') and v['filed']<=asof and v['end']<=asof and v.get('val') is not None:
   d=(pd.Timestamp(v['end'])-pd.Timestamp(v['start'])).days
   if 300<=d<=430: vals.append((v['end'],v['filed'],float(v['val']),tag,v['start']))
 return vals
def feature(facts,asof):
 g=facts.get('facts',{}).get('us-gaap',{}); direct=annual(g,GP_TAG,asof)
 candidates=[]
 for x in direct:candidates.append((x[0],x[1],x[2],'DIRECT_GROSSPROFIT',x[3]))
 rev=[]; cogs=[]
 for tag in REV_TAGS: rev += annual(g,tag,asof)
 for tag in COGS_TAGS: cogs += annual(g,tag,asof)
 for end in sorted(set(x[0] for x in rev)&set(x[0] for x in cogs)):
  rv=max([x for x in rev if x[0]==end],key=lambda x:x[1]); cv=max([x for x in cogs if x[0]==end],key=lambda x:x[1]); candidates.append((end,max(rv[1],cv[1]),rv[2]-cv[2],'REV_MINUS_COST',rv[3]+'|'+cv[3]))
 if not candidates:return None
 gp=max(candidates,key=lambda x:(x[0],x[1],x[3]=='DIRECT_GROSSPROFIT'))
 assets=[]
 for v in g.get('Assets',{}).get('units',{}).get('USD',[]):
  if v.get('form')=='10-K' and not v.get('start') and v.get('end') and v.get('filed') and v['filed']<=asof and v.get('val') is not None: assets.append((v['end'],v['filed'],float(v['val'])))
 prior=[x for x in assets if x[0] < gp[0] and x[2]>0]
 if not prior:return None
 pa=max(prior,key=lambda x:(x[0],x[1])); return {'gross_profitability':gp[2]/pa[2],'source':gp[3],'tags':gp[4],'period_end':gp[0],'filed':gp[1],'assets_period_end':pa[0],'assets_filed':pa[1]}
cache={}; rows=[]
for y in YEARS:
 asof=f'{y}-06-30'; rev,z=hist(asof); idx=[round(i*(len(z)-1)/(N-1)) for i in range(N)]; s=z.iloc[idx].drop_duplicates('ticker'); found=[]
 for _,r in s.iterrows():
  cik=int(r.cik)
  try:
   if cik not in cache: cache[cik]=cf(cik); time.sleep(.07)
   x=feature(cache[cik],asof)
   if x: found.append({'ticker':r.ticker,'cik':str(cik),**x})
  except Exception: pass
 direct=sum(x['source']=='DIRECT_GROSSPROFIT' for x in found); rate=len(found)/len(s)
 rows.append({'year':y,'revision_id':int(rev['revid']),'sample_n':len(s),'feature_n':len(found),'feature_rate':rate,'direct_grossprofit_n':direct,'derived_n':len(found)-direct,'ready':rate>=.80,'features':found})
ready=all(x['ready'] for x in rows)
out={'schema':'research.p478_pit_grossprofit_coverage_r1.v1','workload_id':'P478_PIT_GROSSPROFIT_COVERAGE_R1','parent':'PIT_FUNDAMENTAL_CROSS_SECTIONAL_SELECTION','claim':'Prospective coverage-only repair: admit the standard us-gaap GrossProfit annual 10-K concept as an economically identical direct source for gross profit, falling back to the already-frozen revenue-minus-cost construction. Do not fetch or inspect forward returns.','contract':{'years':YEARS,'sample_n':N,'sample_rule':'identical 20 evenly spaced historical S&P members after ticker sort','gross_profit_sources':['GrossProfit','frozen revenue-minus-cost tags'],'denominator':'latest prior annual 10-K Assets','feature_coverage_min':.80,'forward_returns_inspected':False,'no_post_return_selection':True},'cohorts':rows,'decision':'GROSS_PROFITABILITY_FEATURE_COVERAGE_READY' if ready else 'GROSS_PROFITABILITY_FEATURE_COVERAGE_STILL_NOT_READY','scientific_consequence':'Feature-side coverage repair is prospectively validated; next test price coverage separately before rerunning frozen economics.' if ready else 'Direct GrossProfit is insufficient to clear the frozen feature gate; keep economics untested and do not tune tags from returns.','boundaries':{'performance_inspection':False,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'coverage':{str(x['year']):{'rate':x['feature_rate'],'direct':x['direct_grossprofit_n'],'derived':x['derived_n']} for x in rows}},sort_keys=True))

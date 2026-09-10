from __future__ import annotations
import json, urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

UA='XoticHaze market-research source-validation contact@example.com'
ISSUERS={'AAPL':'0000320193','MSFT':'0000789019','AMZN':'0001018724','GOOGL':'0001652044','NVDA':'0001045810'}
CONCEPTS=['RevenueFromContractWithCustomerExcludingAssessedTax','SalesRevenueNet','Revenues','NetIncomeLoss']
def get(url):
 req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'application/json'})
 return json.loads(urllib.request.urlopen(req,timeout=30).read().decode())
def days(a,b): return (date.fromisoformat(b)-date.fromisoformat(a)).days
rows=[]
for ticker,cik in ISSUERS.items():
 facts=get(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json').get('facts',{}).get('us-gaap',{})
 for concept in CONCEPTS:
  node=facts.get(concept)
  if not node: continue
  for unit,vals in node.get('units',{}).items():
   if unit!='USD': continue
   for v in vals:
    if v.get('form')!='10-Q' or not all(v.get(k) for k in ('start','end','filed','accn')): continue
    if v['filed']<'2018-01-01' or v.get('fp') not in ('Q2','Q3'): continue
    d=days(v['start'],v['end'])
    if 60<=d<=120 and v['end']<=v['filed']:
     rows.append({'ticker':ticker,'concept':concept,'filed':v['filed'],'accn':v['accn'],'fp':v.get('fp'),'start':v['start'],'end':v['end'],'days':d,'value':v.get('val')})
groups=defaultdict(list)
for r in rows: groups[(r['ticker'],r['concept'],r['filed'],r['accn'],r['fp'])].append(r)
outgroups=[]
for key,vals in sorted(groups.items()):
 # SEC may repeat the same semantic fact row across frames. Canonicalize exact semantic duplicates,
 # then use only filing chronology: the direct-quarter period ending latest before filed_at.
 sem={(x['start'],x['end'],x['value']):x for x in vals}
 uniq=list(sem.values())
 latest_end=max(x['end'] for x in uniq)
 latest=[x for x in uniq if x['end']==latest_end]
 outgroups.append({'key':key,'raw_direct_count':len(vals),'semantic_direct_count':len(uniq),'latest_end':latest_end,'latest_semantic_count':len(latest),'unique_latest':len(latest)==1,'selected':latest[0] if len(latest)==1 else None})
n=len(outgroups); unique=sum(x['unique_latest'] for x in outgroups); rate=unique/n if n else 0.0
pass_gate=n>=40 and rate>=0.80
out={'schema':'research.p375_sec_latest_period_adjudicator.v1','workload_id':'P375_SEC_LATEST_PERIOD_ADJUDICATOR_R1','parent_context':'P289/P374','claim':'After P374 proved duration alone non-unique, adjudicate whether exact-semantic dedupe plus latest direct-quarter period end not after filed_at deterministically identifies the current-quarter flow fact, without dropping issuers/concepts or changing the frozen 60-120 day direct-quarter representation.','issuer_ciks':ISSUERS,'concepts':CONCEPTS,'scope':'filed>=2018-01-01; form=10-Q; fp in Q2,Q3; USD; 60<=duration<=120; end<=filed','selector_rule':'Deduplicate exact (start,end,value) semantic copies, then select the unique candidate with maximum end date within each ticker/concept/filed/accession/fp group.','eligible_group_count':n,'unique_latest_count':unique,'unique_latest_rate':rate,'decision_rule':'PASS only if >=40 eligible groups and unique latest-period semantic fact rate >=80%. No issuer/concept dropping, duration tuning, value tie-break, or alpha inference.','decision':'SEC_LATEST_PERIOD_SELECTOR_SUPPORTED' if pass_gate else 'SEC_LATEST_PERIOD_SELECTOR_NOT_YET_SUPPORTED','scientific_consequence':('Admit this filing-context chronology rule as representation evidence and next test point-in-time selector economics on a frozen constituent corpus.' if pass_gate else 'Remain in DATA/REPRESENTATION failure. Do not infer model failure or choose arbitrary values; require an orthogonal filing-context source/field before alpha inference.'),'sample_groups':outgroups[:40],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p375_sec_latest_period_adjudicator_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({k:out[k] for k in ['eligible_group_count','unique_latest_count','unique_latest_rate','decision']},sort_keys=True))

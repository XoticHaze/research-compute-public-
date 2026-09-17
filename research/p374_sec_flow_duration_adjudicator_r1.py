from __future__ import annotations
import json, urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

UA='XoticHaze market-research source-validation contact@example.com'
ISSUERS={
 'AAPL':'0000320193','MSFT':'0000789019','AMZN':'0001018724','GOOGL':'0001652044','NVDA':'0001045810'
}
CONCEPTS=['RevenueFromContractWithCustomerExcludingAssessedTax','SalesRevenueNet','Revenues','NetIncomeLoss']

def get(url):
 req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'application/json'})
 return json.loads(urllib.request.urlopen(req,timeout=30).read().decode())

def days(a,b):
 return (date.fromisoformat(b)-date.fromisoformat(a)).days

rows=[]
for ticker,cik in ISSUERS.items():
 facts=get(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json').get('facts',{}).get('us-gaap',{})
 for concept in CONCEPTS:
  node=facts.get(concept)
  if not node: continue
  for unit,vals in node.get('units',{}).items():
   if unit!='USD': continue
   for v in vals:
    if v.get('form')!='10-Q' or not v.get('start') or not v.get('end') or not v.get('filed') or not v.get('accn'): continue
    if v['filed']<'2018-01-01' or v.get('fp') not in ('Q2','Q3'): continue
    d=days(v['start'],v['end'])
    bucket='DIRECT_QUARTER' if 60<=d<=120 else ('YTD' if 150<=d<=310 else 'OTHER')
    rows.append({'ticker':ticker,'concept':concept,'filed':v['filed'],'accn':v['accn'],'fp':v.get('fp'),'start':v['start'],'end':v['end'],'days':d,'bucket':bucket,'value':v.get('val')})

groups=defaultdict(list)
for r in rows: groups[(r['ticker'],r['concept'],r['filed'],r['accn'],r['fp'])].append(r)
eligible=[]
for key,vals in sorted(groups.items()):
 direct=[x for x in vals if x['bucket']=='DIRECT_QUARTER']
 ytd=[x for x in vals if x['bucket']=='YTD']
 if direct or ytd:
  eligible.append({'key':key,'direct_count':len(direct),'ytd_count':len(ytd),'other_count':sum(x['bucket']=='OTHER' for x in vals),'direct_unique':len(direct)==1,'both_present':bool(direct and ytd),'direct':direct,'ytd':ytd})

n=len(eligible)
direct_present=sum(x['direct_count']>0 for x in eligible)
direct_unique=sum(x['direct_unique'] for x in eligible)
both=sum(x['both_present'] for x in eligible)
present_rate=direct_present/n if n else 0.0
unique_rate=direct_unique/n if n else 0.0
both_rate=both/n if n else 0.0
# Claim-relevant gate: duration should recover one direct-quarter fact in most Q2/Q3 filing-concept groups.
# Presence >=80% and uniqueness >=80% are required before using duration as deterministic selector authority.
pass_gate=n>=40 and present_rate>=0.80 and unique_rate>=0.80
out={
 'schema':'research.p374_sec_flow_duration_adjudicator.v1',
 'workload_id':'P374_SEC_FLOW_DURATION_ADJUDICATOR_R1',
 'parent_context':'P289_SEC_POINT_IN_TIME_FUNDAMENTALS',
 'claim':'Adjudicate whether filed-at-safe start/end duration can deterministically distinguish direct-quarter flow facts from half-year or nine-month YTD facts for Q2/Q3 10-Q observations before any alpha inference.',
 'issuer_ciks':ISSUERS,'concepts':CONCEPTS,'window':'filed>=2018-01-01; form=10-Q; fp in Q2,Q3',
 'bucket_rule':{'DIRECT_QUARTER':'60<=duration_days<=120','YTD':'150<=duration_days<=310','OTHER':'otherwise'},
 'eligible_group_count':n,'direct_present_count':direct_present,'direct_unique_count':direct_unique,'both_present_count':both,
 'direct_present_rate':present_rate,'direct_unique_rate':unique_rate,'both_present_rate':both_rate,
 'decision_rule':'PASS only if >=40 eligible filing-concept groups and both direct-quarter presence and exact-one direct-quarter uniqueness are >=80%. No concept/ticker dropping or threshold search.',
 'decision':'SEC_FLOW_DURATION_SELECTOR_SUPPORTED' if pass_gate else 'SEC_FLOW_DURATION_SELECTOR_NOT_YET_SUPPORTED',
 'scientific_consequence':('Duration is admissible as a deterministic representation layer for Q2/Q3 flow facts; next test must validate point-in-time selector economics without changing concepts/universe.' if pass_gate else 'Do not infer fundamental-model failure. Treat as data/representation weakness and require a different causal filing-context rule before alpha testing; do not rescue by dropping issuers/concepts or tuning duration bands.'),
 'sample_groups':eligible[:30],
 'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}
}
Path('research/artifacts').mkdir(parents=True,exist_ok=True)
Path('research/artifacts/p374_sec_flow_duration_adjudicator_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({k:out[k] for k in ['eligible_group_count','direct_present_rate','direct_unique_rate','both_present_rate','decision']},sort_keys=True))

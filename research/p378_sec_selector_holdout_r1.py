from __future__ import annotations
import json, urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path
UA='XoticHaze market-research source-validation contact@example.com'
ISSUERS={'JPM':'0000019617','JNJ':'0000200406','PG':'0000080424','HD':'0000354950','CAT':'0000018230','KO':'0000021344','PEP':'0000077476','WMT':'0000104169','CVX':'0000093410','COST':'0000909832'}
CONCEPTS=['RevenueFromContractWithCustomerExcludingAssessedTax','SalesRevenueNet','Revenues','NetIncomeLoss']
def get(url):
 req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'application/json'}); return json.loads(urllib.request.urlopen(req,timeout=30).read().decode())
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
     rows.append({'ticker':ticker,'concept':concept,'filed':v['filed'],'accn':v['accn'],'fp':v.get('fp'),'start':v['start'],'end':v['end'],'value':v.get('val')})
groups=defaultdict(list)
for r in rows: groups[(r['ticker'],r['concept'],r['filed'],r['accn'],r['fp'])].append(r)
outgroups=[]
for key,vals in sorted(groups.items()):
 sem={(x['start'],x['end'],x['value']):x for x in vals}; uniq=list(sem.values()); latest_end=max(x['end'] for x in uniq); latest=[x for x in uniq if x['end']==latest_end]
 outgroups.append({'key':key,'semantic_direct_count':len(uniq),'latest_end':latest_end,'latest_semantic_count':len(latest),'unique_latest':len(latest)==1})
n=len(outgroups); unique=sum(x['unique_latest'] for x in outgroups); rate=unique/n if n else 0.0; represented=len({x['key'][0] for x in outgroups})
pass_gate=n>=100 and represented>=8 and rate>=0.80
out={'schema':'research.p378_sec_selector_holdout.v1','workload_id':'P378_SEC_SELECTOR_HOLDOUT_R1','parent_context':'P375','claim':'Test P375 exact-semantic dedupe plus latest-period-end selector on a completely disjoint fixed ten-issuer cross-sector holdout, without changing concepts, duration representation, filing scope, or uniqueness threshold.','issuer_ciks':ISSUERS,'concepts':CONCEPTS,'scope':'filed>=2018-01-01; form=10-Q; fp in Q2,Q3; USD; 60<=duration<=120; end<=filed','eligible_group_count':n,'represented_issuer_count':represented,'unique_latest_count':unique,'unique_latest_rate':rate,'decision_rule':'PASS only if >=100 eligible groups, >=8/10 issuers represented, and unique latest-period semantic fact rate >=80%. No issuer/concept dropping or rule tuning after observation.','decision':'SEC_LATEST_PERIOD_SELECTOR_HOLDOUT_SUPPORTED' if pass_gate else 'SEC_LATEST_PERIOD_SELECTOR_HOLDOUT_NOT_SUPPORTED','scientific_consequence':('Independent issuer holdout supports transport of P375 representation rule; issuer lineage and historical membership remain separate gates before alpha.' if pass_gate else 'Record REGIME/REPRESENTATION transport weakness only; preserve original P375 scope and do not infer fundamental-model failure or tune the selector.'),'sample_groups':outgroups[:40],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p378_sec_selector_holdout_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({k:out[k] for k in ['eligible_group_count','represented_issuer_count','unique_latest_rate','decision']},sort_keys=True))

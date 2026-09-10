from __future__ import annotations
import json,time,urllib.request
from pathlib import Path
from collections import defaultdict

TICKERS=['AAPL','MSFT','NVDA','AMAT','CAT','JPM','JNJ','PG','HD']
UA='XoticHaze market-research source-validation contact@example.com'
FAMILIES={
 'revenue':['RevenueFromContractWithCustomerExcludingAssessedTax','Revenues','SalesRevenueNet','SalesRevenueGoodsNet','SalesRevenueServicesNet','InterestAndDividendIncomeOperating'],
 'net_income':['NetIncomeLoss','ProfitLoss'],
 'assets':['Assets'],
 'equity':['StockholdersEquity','StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest','PartnersCapital']}

def get(url):
 req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'application/json'})
 return json.loads(urllib.request.urlopen(req,timeout=30).read().decode())

def family_rows(us,aliases):
 out=[]
 for rank,concept in enumerate(aliases):
  for unit,vals in us.get(concept,{}).get('units',{}).items():
   for v in vals:
    if v.get('form') not in ('10-K','10-Q') or not v.get('filed') or not v.get('end') or v.get('val') is None: continue
    out.append({'concept':concept,'concept_rank':rank,'unit':unit,'filed':v['filed'],'end':v['end'],'form':v['form'],'accn':v.get('accn'),'val':v['val']})
 return out

def select(rows,asof):
 eligible=[r for r in rows if r['filed']<=asof]
 if not eligible:return None
 max_end=max(r['end'] for r in eligible); same_end=[r for r in eligible if r['end']==max_end]
 max_filed=max(r['filed'] for r in same_end); same=[r for r in same_end if r['filed']==max_filed]
 units=sorted({r['unit'] for r in same}); preferred=[r for r in same if r['unit']=='USD'] or same
 best=sorted(preferred,key=lambda r:(r['concept_rank'],0 if r['form']=='10-K' else 1,r.get('accn') or ''))[0]
 semantic={(r['concept'],r['form'],r['unit'],r.get('accn')) for r in preferred}
 return {'selected':best,'candidate_count':len(preferred),'semantic_candidate_count':len(semantic)}

mp=get('https://www.sec.gov/files/company_tickers.json'); ciks={v['ticker'].upper():str(v['cik_str']).zfill(10) for v in mp.values()}
asofs=[f'{y}-{m:02d}-01' for y in range(2015,2027) for m in (1,4,7,10) if f'{y}-{m:02d}-01'<='2026-09-10']
results={}; total=unique=ambiguous=0
for t in TICKERS:
 data=get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{ciks[t]}.json"); us=data.get('facts',{}).get('us-gaap',{}); tr={}
 for fam,aliases in FAMILIES.items():
  rows=family_rows(us,aliases); selections=[]
  for a in asofs:
   s=select(rows,a)
   if s:
    total+=1; unique+=int(s['candidate_count']==1); ambiguous+=int(s['candidate_count']>1); selections.append({'asof':a,**s})
  tr[fam]={'available_asofs':len(selections),'unique_fraction':(sum(x['candidate_count']==1 for x in selections)/len(selections) if selections else 0),'ambiguous_asofs':sum(x['candidate_count']>1 for x in selections),'max_candidates':max([x['candidate_count'] for x in selections] or [0])}
 results[t]=tr; time.sleep(.12)
unique_fraction=unique/total if total else 0
coverage=min((v[f]['available_asofs'] for v in results.values() for f in FAMILIES),default=0)
decision='P289_ASOF_ACCESSION_POLICY_OPERATIONAL' if total and unique_fraction>=0.80 and coverage>=20 else 'P289_ASOF_ACCESSION_AMBIGUITY_NEEDS_MODEL_POLICY'
out={'schema':'research.p289_sec_asof_accession_r1','parent':'P289','claim':'Determine whether filed-date-only SEC companyfacts can be transformed into deterministic chronology-safe point-in-time fundamentals with a frozen concept/form/unit/accession precedence, without using facts before filing or silently relying on restated future knowledge.','sample_tickers':TICKERS,'asof_grid':'quarterly 2015-01 through 2026-07','concept_families':FAMILIES,'selection_policy':'at each as-of date use only filed<=asof; choose latest period end; then latest filing date; prefer USD; then fixed concept precedence, 10-K before 10-Q, lexical accession tie-break','results':results,'summary':{'selection_count':total,'unique_without_tiebreak_fraction':unique_fraction,'ambiguous_selection_count':ambiguous,'minimum_family_asof_coverage':coverage},'decision_rule':'Operational if >=80% of eligible selections are unique before final concept/form/accession tie-break and every ticker/family has >=20 quarterly as-of selections. Otherwise require an explicit economic comparability policy before alpha inference.','decision':decision,'limitations':['Fixed current-ticker sample is source validation, not historical investable membership','XOM intentionally excluded because P287 independently established issuer-lineage authority is required before using it historically','A later economic model must preserve this filed<=asof rule and independently solve historical universe membership','scientific source/causality evidence only; no allocation/ranking/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p289_sec_asof_accession_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))

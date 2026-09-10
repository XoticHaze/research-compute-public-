from __future__ import annotations
import json,time,urllib.request
from pathlib import Path

TICKERS=['AAPL','MSFT','NVDA','AMAT','CAT','JPM','JNJ','PG','HD','XOM']
UA='XoticHaze market-research source-validation contact@example.com'
FAMILIES={
 'revenue':{'aliases':['RevenueFromContractWithCustomerExcludingAssessedTax','Revenues','SalesRevenueNet','SalesRevenueGoodsNet','SalesRevenueServicesNet','InterestAndDividendIncomeOperating'],'kind':'flow'},
 'net_income':{'aliases':['NetIncomeLoss','ProfitLoss'],'kind':'flow'},
 'assets':{'aliases':['Assets'],'kind':'instant'},
 'equity':{'aliases':['StockholdersEquity','StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest','PartnersCapital'],'kind':'instant'}
}
XOM_CIKS=['0000034088','0002115436']

def get(url):
 req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'application/json'})
 return json.loads(urllib.request.urlopen(req,timeout=30).read().decode())

def facts_for(cik):
 return get(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json')

def rows(us,aliases,kind):
 out=[]
 for rank,concept in enumerate(aliases):
  for unit,vals in us.get(concept,{}).get('units',{}).items():
   for v in vals:
    if v.get('form') not in ('10-K','10-Q') or not v.get('filed') or not v.get('end') or v.get('val') is None: continue
    dur=None
    if v.get('start'):
     try: dur=(__import__('datetime').date.fromisoformat(v['end'])-__import__('datetime').date.fromisoformat(v['start'])).days
     except Exception: dur=None
    if kind=='flow':
     valid=(v['form']=='10-Q' and dur is not None and 70<=dur<=110) or (v['form']=='10-K' and dur is not None and 300<=dur<=400)
     if not valid: continue
    out.append({'concept':concept,'concept_rank':rank,'unit':unit,'filed':v['filed'],'start':v.get('start'),'end':v['end'],'form':v['form'],'accn':v.get('accn'),'val':float(v['val']),'duration_days':dur})
 return out

def lineage_us(ticker,ciks):
 merged={}
 entities=[]
 for cik in ciks:
  d=facts_for(cik); entities.append({'cik':cik,'entityName':d.get('entityName')})
  us=d.get('facts',{}).get('us-gaap',{})
  for concept,blob in us.items():
   dst=merged.setdefault(concept,{'units':{}})
   for unit,vals in blob.get('units',{}).items(): dst['units'].setdefault(unit,[]).extend(vals)
 return merged,entities

def select(candidates,asof):
 eligible=[r for r in candidates if r['filed']<=asof]
 if not eligible:return None
 max_end=max(r['end'] for r in eligible); same_end=[r for r in eligible if r['end']==max_end]
 max_filed=max(r['filed'] for r in same_end); same=[r for r in same_end if r['filed']==max_filed]
 usd=[r for r in same if r['unit']=='USD'] or same
 best=sorted(usd,key=lambda r:(r['concept_rank'],0 if r['form']=='10-K' else 1,r.get('accn') or ''))[0]
 vals=[r['val'] for r in usd]
 scale=max(abs(best['val']),1.0)
 material_conflict=any(abs(v-best['val'])/scale>0.01 for v in vals)
 return {'selected':best,'candidate_count':len(usd),'material_value_conflict':material_conflict,'candidate_values':vals[:8]}

mapping=get('https://www.sec.gov/files/company_tickers.json'); ciks={v['ticker'].upper():str(v['cik_str']).zfill(10) for v in mapping.values()}
asofs=[f'{y}-{m:02d}-01' for y in range(2015,2027) for m in (1,4,7,10) if f'{y}-{m:02d}-01'<='2026-09-10']
results={}; total=conflicts=0; min_coverage=10**9; lineage={}
for t in TICKERS:
 use=XOM_CIKS if t=='XOM' else [ciks[t]]
 us,entities=lineage_us(t,use); lineage[t]=entities; tr={}
 for fam,spec in FAMILIES.items():
  rr=rows(us,spec['aliases'],spec['kind']); sels=[]
  for a in asofs:
   s=select(rr,a)
   if s:
    total+=1; conflicts+=int(s['material_value_conflict']); sels.append({'asof':a,**s})
  cov=len(sels); min_coverage=min(min_coverage,cov)
  tr[fam]={'available_asofs':cov,'material_conflict_fraction':(sum(x['material_value_conflict'] for x in sels)/cov if cov else 1.0),'ambiguous_asofs':sum(x['candidate_count']>1 for x in sels),'material_conflict_asofs':sum(x['material_value_conflict'] for x in sels)}
 results[t]=tr; time.sleep(.12)
conflict_fraction=conflicts/total if total else 1.0
xom_names=' '.join(x['entityName'] or '' for x in lineage['XOM']).upper(); xom_lineage_ok=('EXXON MOBIL' in xom_names or 'EXXONMOBIL' in xom_names) and len(lineage['XOM'])==2
passes=(total>0 and conflict_fraction<=0.05 and min_coverage>=20 and xom_lineage_ok)
decision='P309_SEC_ECONOMIC_COMPARABILITY_ADMITTED' if passes else 'P309_SEC_ECONOMIC_COMPARABILITY_NOT_ADMITTED'
out={'schema':'research.p309_sec_economic_comparability_r1','parent':'P309','claim':'Adjudicate whether normalized SEC companyfacts can support deterministic economically comparable point-in-time fields after filed-at chronology, form-duration filtering, concept precedence, accession tie-break, and explicit XOM issuer lineage. This is admission evidence only, not alpha.','sample_tickers':TICKERS,'families':FAMILIES,'selection_policy':'filed<=asof; latest end; latest filed; USD preferred; flow concepts require 10-Q 70-110d or 10-K 300-400d duration; fixed concept precedence; 10-K before 10-Q; lexical accession tie-break; explicit XOM predecessor+successor lineage only for comparability adjudication','results':results,'summary':{'selection_count':total,'material_value_conflict_fraction':conflict_fraction,'minimum_family_asof_coverage':min_coverage,'xom_lineage_ok':xom_lineage_ok,'xom_entities':lineage['XOM']},'decision_rule':'Admit only if material alternative-value conflicts are <=5%, every ticker/family has >=20 quarterly as-of selections, and explicit XOM two-entity lineage resolves to Exxon Mobil identity. Failure blocks raw SEC alpha without rejecting broader fundamentals alpha.','decision':decision,'limitations':['fixed current-ticker source/comparability sample, not historical investable membership','XOM lineage is explicit adjudication evidence, not a general corporate-actions master','no raw alpha inference or portfolio ranking','no product/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p309_sec_economic_comparability_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))

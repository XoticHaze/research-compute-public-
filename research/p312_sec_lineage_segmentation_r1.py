from __future__ import annotations
import json,time,urllib.request,datetime
from pathlib import Path
TICKERS=['AAPL','MSFT','NVDA','AMAT','CAT','JPM','JNJ','PG','HD','XOM']; UA='XoticHaze market-research source-validation contact@example.com'
FAMILIES={'revenue':{'aliases':['RevenueFromContractWithCustomerExcludingAssessedTax','Revenues','SalesRevenueNet','SalesRevenueGoodsNet','SalesRevenueServicesNet','InterestAndDividendIncomeOperating'],'kind':'flow'},'net_income':{'aliases':['NetIncomeLoss','ProfitLoss'],'kind':'flow'},'assets':{'aliases':['Assets'],'kind':'instant'},'equity':{'aliases':['StockholdersEquity','StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest','PartnersCapital'],'kind':'instant'}}
LEGACY='0000034088'; SUCCESSOR='0002115436'
def get(url):
 req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'application/json'}); return json.loads(urllib.request.urlopen(req,timeout=30).read().decode())
def fetch(cik): return get(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json')
def collect(data,cik,aliases,kind):
 us=data.get('facts',{}).get('us-gaap',{}); out=[]
 for rank,c in enumerate(aliases):
  for unit,vals in us.get(c,{}).get('units',{}).items():
   for v in vals:
    if v.get('form') not in ('10-K','10-Q') or not v.get('filed') or not v.get('end') or v.get('val') is None: continue
    dur=None
    if v.get('start'):
     try: dur=(datetime.date.fromisoformat(v['end'])-datetime.date.fromisoformat(v['start'])).days
     except Exception: pass
    if kind=='flow' and not ((v['form']=='10-Q' and dur is not None and 70<=dur<=110) or (v['form']=='10-K' and dur is not None and 300<=dur<=400)): continue
    out.append({'source_cik':cik,'concept':c,'concept_rank':rank,'unit':unit,'filed':v['filed'],'start':v.get('start'),'end':v['end'],'form':v['form'],'accn':v.get('accn'),'val':float(v['val']),'duration_days':dur})
 return out
def select(rr,asof):
 eligible=[r for r in rr if r['filed']<=asof]
 if not eligible:return None
 e=max(r['end'] for r in eligible); q=[r for r in eligible if r['end']==e]; f=max(r['filed'] for r in q); q=[r for r in q if r['filed']==f]; q=[r for r in q if r['unit']=='USD'] or q; best=sorted(q,key=lambda r:(r['concept_rank'],0 if r['form']=='10-K' else 1,r.get('accn') or ''))[0]; scale=max(abs(best['val']),1.0); conflict=any(abs(r['val']-best['val'])/scale>0.01 for r in q); return {'selected':best,'candidate_count':len(q),'material_value_conflict':conflict}
mp=get('https://www.sec.gov/files/company_tickers.json'); ciks={v['ticker'].upper():str(v['cik_str']).zfill(10) for v in mp.values()}; successor=fetch(SUCCESSOR); successor_filed=[]
for c in successor.get('facts',{}).get('us-gaap',{}).values():
 for vals in c.get('units',{}).values(): successor_filed += [v['filed'] for v in vals if v.get('filed')]
transition=min(successor_filed); asofs=[f'{y}-{m:02d}-01' for y in range(2015,2027) for m in (1,4,7,10) if f'{y}-{m:02d}-01'<='2026-09-10']; results={}; total=conflicts=0; mincov=10**9
for t in TICKERS:
 datasets=[(ciks[t],fetch(ciks[t]))] if t!='XOM' else [(LEGACY,fetch(LEGACY)),(SUCCESSOR,successor)]
 tr={}
 for fam,spec in FAMILIES.items():
  rr=[]
  for cik,d in datasets: rr += collect(d,cik,spec['aliases'],spec['kind'])
  if t=='XOM': rr=[r for r in rr if (r['source_cik']==LEGACY and r['filed']<transition) or (r['source_cik']==SUCCESSOR and r['filed']>=transition)]
  sels=[]
  for a in asofs:
   s=select(rr,a)
   if s: total+=1; conflicts+=int(s['material_value_conflict']); sels.append(s)
  cov=len(sels); mincov=min(mincov,cov); tr[fam]={'available_asofs':cov,'material_conflict_fraction':sum(x['material_value_conflict'] for x in sels)/cov if cov else 1.0,'material_conflict_asofs':sum(x['material_value_conflict'] for x in sels)}
 results[t]=tr; time.sleep(.12)
frac=conflicts/total if total else 1.0; passed=total>0 and frac<=0.05 and mincov>=20; decision='P312_SEC_LINEAGE_SEGMENTATION_ADMITS_COMPARABILITY' if passed else 'P312_SEC_LINEAGE_SEGMENTATION_DOES_NOT_ADMIT_COMPARABILITY'
out={'schema':'research.p312_sec_lineage_segmentation_r1','parent':'P312','claim':'Rerun the unchanged P309 comparability gate with one predeclared non-overlapping XOM predecessor/successor segmentation rule: predecessor facts filed before the successor first-filed boundary, successor facts filed at/after it. Preserve source CIK/accession/period/filed provenance.','transition_rule':{'legacy_cik':LEGACY,'successor_cik':SUCCESSOR,'successor_first_filed':transition,'legacy_allowed':'filed < successor_first_filed','successor_allowed':'filed >= successor_first_filed'},'results':results,'summary':{'selection_count':total,'material_value_conflict_fraction':frac,'minimum_family_asof_coverage':mincov,'xom':results['XOM']},'decision_rule':'Unchanged P309 gate: <=5% aggregate material-value conflicts and >=20 quarterly selections for every ticker/family. No threshold, sample, concept, form, duration, window or tolerance changes.','decision':decision,'limitations':['fixed source/comparability sample, not investable membership','lineage segmentation is a deterministic representation adjudicator, not alpha','no allocation/ranking/product/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p312_sec_lineage_segmentation_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))

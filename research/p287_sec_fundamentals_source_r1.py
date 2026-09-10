from __future__ import annotations
import json,time,urllib.request
from pathlib import Path
TICKERS=['AAPL','MSFT','NVDA','AMAT','CAT','JPM','XOM','JNJ','PG','HD']
FACTS=['Revenues','RevenueFromContractWithCustomerExcludingAssessedTax','NetIncomeLoss','StockholdersEquity','Assets','CommonStockSharesOutstanding']
UA='XoticHaze market-research source-validation contact@example.com'
def get(url):
 req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'application/json'}); return json.loads(urllib.request.urlopen(req,timeout=30).read().decode('utf-8'))
mp=get('https://www.sec.gov/files/company_tickers.json'); cik={v['ticker'].upper():str(v['cik_str']).zfill(10) for v in mp.values()}; rows={}
for t in TICKERS:
 c=cik.get(t); rec={'cik':c,'facts':{},'pass':False}
 if not c: rows[t]=rec; continue
 data=get(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{c}.json'); us=data.get('facts',{}).get('us-gaap',{})
 for f in FACTS:
  units=us.get(f,{}).get('units',{}); xs=[]
  for unit,vals in units.items():
   for v in vals:
    if v.get('form') in ('10-K','10-Q') and v.get('filed') and v.get('end'):
     xs.append({'unit':unit,'end':v.get('end'),'filed':v.get('filed'),'form':v.get('form'),'fy':v.get('fy'),'fp':v.get('fp'),'val':v.get('val'),'accn':v.get('accn')})
  xs=sorted(xs,key=lambda x:(x['filed'],x['end'],x.get('accn') or ''))
  rec['facts'][f]={'observations':len(xs),'first_filed':xs[0]['filed'] if xs else None,'last_filed':xs[-1]['filed'] if xs else None,'distinct_period_ends':len(set(x['end'] for x in xs)),'has_filed_timestamp':bool(xs)}
 core_rev=max(rec['facts']['Revenues']['observations'],rec['facts']['RevenueFromContractWithCustomerExcludingAssessedTax']['observations'])
 rec['pass']=core_rev>=20 and rec['facts']['NetIncomeLoss']['observations']>=20 and rec['facts']['Assets']['observations']>=20 and rec['facts']['StockholdersEquity']['observations']>=12
 rows[t]=rec; time.sleep(.12)
passn=sum(v['pass'] for v in rows.values()); decision='P287_SEC_POINT_IN_TIME_SOURCE_ADMISSIBLE_FOR_NEXT_ECONOMIC_TEST' if passn>=8 else 'P287_SEC_SOURCE_COVERAGE_NOT_ADMITTED'
out={'schema':'research.p287_sec_fundamentals_source_r1','parent':'P287','claim':'Determine whether the SEC companyfacts route exposes filed-at, period-end, accession-identified accounting facts with enough fixed-sample coverage to support a chronology-safe point-in-time profitability/value model without relying on current fundamentals or revised-price labels.','sample_tickers':TICKERS,'required_core_fields':['revenue_or_contract_revenue','NetIncomeLoss','Assets','StockholdersEquity'],'ticker_results':rows,'passing_tickers':passn,'ticker_count':len(TICKERS),'decision_rule':'Admit source feasibility only if at least 8/10 fixed cross-sector tickers expose >=20 filed observations for revenue, net income and assets and >=12 for equity. Admission authorizes only a next economic discriminator with as-of filed-date filtering; it does not establish alpha.','decision':decision,'limitations':['SEC companyfacts may include later amendments/restatements; economic evaluator must select facts by filed date and freeze a deterministic accession policy','fixed source-feasibility sample is not an investable universe','CIK/ticker mapping is current and must not be used as historical membership authority','scientific source evidence only; no allocation/ranking/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p287_sec_fundamentals_source_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))

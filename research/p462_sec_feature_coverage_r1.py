from __future__ import annotations
import json,re,time,urllib.request
from io import StringIO
from pathlib import Path
import pandas as pd,requests
UA='CommandCenter MarketResearch P462 research@example.invalid'
DATES=[f'{y}-12-31' for y in range(2018,2026)]; SAMPLE_N=20
OUT=Path('research/artifacts/p462_sec_feature_coverage_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
CONCEPTS={'assets':['Assets'],'equity':['StockholdersEquity','StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest'],'net_income':['NetIncomeLoss','ProfitLoss']}
def hist_table(target):
 p={'action':'query','format':'json','prop':'revisions','titles':'List of S&P 500 companies','rvprop':'ids|timestamp','rvlimit':'1','rvstart':target+'T23:59:59Z'}
 j=requests.get('https://en.wikipedia.org/w/api.php',params=p,headers={'User-Agent':UA},timeout=30).json(); rev=next(iter(j['query']['pages'].values()))['revisions'][0]
 h=requests.get(f"https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid={rev['revid']}",headers={'User-Agent':UA},timeout=30); h.raise_for_status()
 for t in pd.read_html(StringIO(h.text)):
  low={re.sub(r'[^a-z0-9]+','',str(c).lower()):c for c in t.columns}; sk=next((low[k] for k in low if k in ('symbol','ticker','tickersymbol')),None); ck=next((low[k] for k in low if 'cik' in k),None)
  if sk and ck:
   z=t[[sk,ck]].copy(); z.columns=['ticker','cik']; z['ticker']=z.ticker.astype(str).str.strip().str.upper().str.replace('.','-',regex=False); z['cik']=pd.to_numeric(z.cik,errors='coerce').astype('Int64'); return rev,z.dropna(subset=['cik']).sort_values('ticker')
 raise RuntimeError('NO_HIST_TABLE')
def facts(cik):
 req=urllib.request.Request(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json',headers={'User-Agent':UA,'Accept':'application/json'})
 return json.loads(urllib.request.urlopen(req,timeout=30).read().decode())
def latest_value(cf,names,asof,instant):
 g=cf.get('facts',{}).get('us-gaap',{})
 candidates=[]
 for name in names:
  node=g.get(name,{})
  for unit,vals in node.get('units',{}).items():
   if unit!='USD': continue
   for v in vals:
    if not v.get('filed') or v['filed']>asof or not v.get('end') or v['end']>asof or v.get('form') not in ('10-K','10-Q'): continue
    if instant and v.get('start'): continue
    if not instant and not v.get('start'): continue
    candidates.append((v['filed'],v['end'],v.get('val'),name,v.get('form'),v.get('accn')))
 if not candidates:return None
 return max(candidates,key=lambda x:(x[0],x[1]))
cache={}; rows=[]
for d in DATES:
 rev,z=hist_table(d); idx=[round(i*(len(z)-1)/(SAMPLE_N-1)) for i in range(SAMPLE_N)]; sample=z.iloc[idx].drop_duplicates('ticker')
 ok=0; details=[]
 for _,r in sample.iterrows():
  cik=int(r.cik)
  try:
   if cik not in cache: cache[cik]=facts(cik); time.sleep(.08)
   cf=cache[cik]; a=latest_value(cf,CONCEPTS['assets'],d,True); e=latest_value(cf,CONCEPTS['equity'],d,True); ni=latest_value(cf,CONCEPTS['net_income'],d,False)
   ready=all(x is not None for x in (a,e,ni)); ok+=int(ready)
   details.append({'ticker':r.ticker,'cik':str(cik),'ready':ready,'assets':a,'equity':e,'net_income':ni})
  except Exception as ex: details.append({'ticker':r.ticker,'cik':str(cik),'ready':False,'error':str(ex)[:200]})
 rate=ok/len(sample) if len(sample) else 0
 rows.append({'target':d,'revision_id':int(rev['revid']),'sample_n':len(sample),'feature_ready':ok,'feature_ready_rate':rate,'rows':details,'ready':rate>=.80})
ready=sum(x['ready'] for x in rows); decision='FILED_AT_SEC_FEATURE_COVERAGE_READY' if ready==len(rows) else 'FILED_AT_SEC_FEATURE_COVERAGE_NOT_READY'
out={'schema':'research.p462_sec_feature_coverage_r1.v1','workload_id':'P462_SEC_FEATURE_COVERAGE_R1','parent':'PIT_FUNDAMENTAL_CROSS_SECTIONAL_SELECTION','claim':'After the dense historical membership gate passed, test whether a deterministic evenly-spaced 20-issuer sample from each fixed annual 2018-2025 historical S&P universe has causal filed-at assets, equity, and net-income facts available by each as-of date. This is a feature/corpus gate before economic ranking, not alpha inference.','contract':{'dates':DATES,'sample_rule':'20 evenly spaced rows after ticker sort, fixed before facts inspection','features':CONCEPTS,'forms':['10-K','10-Q'],'filed_must_be_on_or_before_asof':True,'period_end_must_be_on_or_before_asof':True,'annual_pass_rate_min':.80,'all_dates_required':True,'no_current_membership_fill':True},'snapshots':rows,'counts':{'dates':len(rows),'ready_dates':ready},'decision':decision,'scientific_consequence':('Feature representation is dense enough to justify one fixed point-in-time profitability/value economic discriminator on historical membership.' if decision.endswith('READY') else 'Do not infer model failure; localize feature/source coverage misses before full economic evaluation, without dropping issuers post-observation.'),'boundaries':{'alpha_inference_this_run':False,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'rates':{x['target']:round(x['feature_ready_rate'],3) for x in rows}},sort_keys=True))

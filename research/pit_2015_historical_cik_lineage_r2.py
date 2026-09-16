from __future__ import annotations
import json,re,time
from io import StringIO
from pathlib import Path
import pandas as pd,requests
RESIDUAL=['AABA','ANDV','APTV','ARNC','BHGE','BKNG','JEF','KDP','SPGI','TPR','UAA','VMRK','WYND']
DATES=['2015-12-31','2016-12-31','2017-12-31','2018-12-31','2019-12-31','2020-12-31']
UA={'User-Agent':'CommandCenter-MarketResearch-HistoricalCIK/1.0 research@example.invalid'}
OUT=Path('research/artifacts/pit_2015_historical_cik_lineage_r2.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
def nt(x): return str(x).strip().upper().replace('.','-')
def table_at(date):
 p={'action':'query','format':'json','prop':'revisions','titles':'List of S&P 500 companies','rvprop':'ids|timestamp','rvlimit':'1','rvstart':date+'T23:59:59Z'}
 j=requests.get('https://en.wikipedia.org/w/api.php',params=p,headers=UA,timeout=30).json(); rev=next(iter(j['query']['pages'].values()))['revisions'][0]
 h=requests.get(f"https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid={rev['revid']}",headers=UA,timeout=30); h.raise_for_status()
 for t in pd.read_html(StringIO(h.text)):
  low={re.sub(r'[^a-z0-9]+','',str(c).lower()):c for c in t.columns}; sk=next((low[k] for k in low if k in ('symbol','ticker','tickersymbol')),None); ck=next((low[k] for k in low if 'cik' in k),None); nk=next((low[k] for k in low if k in ('security','company','companyname','name')),None)
  if sk and ck and nk:
   q=t[[sk,nk,ck]].copy(); q.columns=['ticker','name','cik']; q['ticker']=q.ticker.map(nt); q['cik']=pd.to_numeric(q.cik,errors='coerce').astype('Int64'); return {'date':date,'revision_id':int(rev['revid']),'revision_timestamp':rev['timestamp']},q
 raise RuntimeError('NO_IDENTITY_TABLE_'+date)
snaps={}; meta=[]
for d in DATES:
 m,t=table_at(d); meta.append(m); snaps[d]=t; time.sleep(.15)
base=snaps['2015-12-31']; rows=[]
for ticker in RESIDUAL:
 obs=[]
 for d in DATES[1:]:
  z=snaps[d].loc[snaps[d].ticker==ticker]
  for _,r in z.iterrows():
   obs.append({'date':d,'ticker':ticker,'name':str(r['name']),'cik':None if pd.isna(r.cik) else str(int(r.cik))})
 ciks=sorted({o['cik'] for o in obs if o['cik']})
 rec={'membership_ticker':ticker,'dated_observations':obs,'distinct_dated_ciks':ciks}
 if len(ciks)!=1:
  rec['status']='NO_UNIQUE_DATED_CIK_LINEAGE'; rows.append(rec); continue
 cik=int(ciks[0]); old=base.loc[base.cik==cik]
 if len(old)==1:
  r=old.iloc[0]; rec.update({'status':'EXACT_HISTORICAL_CIK_LINEAGE_MATCH','historical_2015_ticker':r.ticker,'historical_2015_name':str(r['name']),'historical_cik':str(cik)})
 elif len(old)==0: rec['status']='DATED_CIK_NOT_PRESENT_IN_2015_TABLE'
 else: rec.update({'status':'AMBIGUOUS_2015_CIK','candidate_count':int(len(old))})
 rows.append(rec)
resolved=[r for r in rows if r['status']=='EXACT_HISTORICAL_CIK_LINEAGE_MATCH']; unresolved=[r['membership_ticker'] for r in rows if r['status']!='EXACT_HISTORICAL_CIK_LINEAGE_MATCH']
out={'schema':'research.pit_2015_historical_cik_lineage_r2.v1','workload_id':'PIT_2015_HISTORICAL_CIK_LINEAGE_R2','parent':'POINT_IN_TIME_FUNDAMENTAL_SELECTION','claim':'Resolve fixed 2015 ticker aliases only when one CIK observed in dated 2016-2020 historical Wikipedia snapshots maps uniquely to a 2015 historical Wikipedia row. No current SEC identity is consulted.','source_contract':{'historical_snapshots':meta,'residual_input':RESIDUAL,'current_sec_used':False,'constituent_drop':False},'counts':{'input_residual':len(RESIDUAL),'resolved_by_historical_cik_lineage':len(resolved),'remaining_unresolved':len(unresolved)},'rows':rows,'unresolved':unresolved,'decision':'ALL_RESIDUAL_ALIASES_RESOLVED_BY_HISTORICAL_CIK_LINEAGE' if not unresolved else 'HISTORICAL_CIK_LINEAGE_PARTIAL','scientific_consequence':('All residual ticker aliases now have dated identifier continuity back to 2015; combine with prior exact-name resolutions and rerun the all-target identity gate before any SEC alpha inference.' if not unresolved else 'Consume only exact historical CIK lineage matches. Keep residuals fail-closed and require a separate dated corporate-action/filing identity source; do not use current ticker-CIK identity as historical authority.'),'boundaries':{'alpha_inference_this_run':False,'current_sec_identity_authority':False,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'counts':out['counts'],'resolved':[{k:r[k] for k in ('membership_ticker','historical_2015_ticker','historical_2015_name','historical_cik')} for r in resolved],'unresolved':unresolved},sort_keys=True))

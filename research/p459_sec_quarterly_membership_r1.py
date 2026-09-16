from __future__ import annotations
import json,re,time
from io import StringIO
from pathlib import Path
import pandas as pd,requests
UA={'User-Agent':'CommandCenter-MarketResearch-P459/1.0 research@example.invalid'}
DATES=[f'{y}-{m:02d}-{d}' for y in range(2016,2026) for m,d in [(3,31),(6,30),(9,30),(12,31)]]
OUT=Path('research/artifacts/p459_sec_quarterly_membership_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
def norm_ticker(x): return str(x).strip().upper().replace('.','-')
def one(target):
 p={'action':'query','format':'json','prop':'revisions','titles':'List of S&P 500 companies','rvprop':'ids|timestamp','rvlimit':'1','rvstart':target+'T23:59:59Z'}
 j=requests.get('https://en.wikipedia.org/w/api.php',params=p,headers=UA,timeout=30).json(); rev=next(iter(j['query']['pages'].values()))['revisions'][0]
 h=requests.get(f"https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid={rev['revid']}",headers=UA,timeout=30); h.raise_for_status(); chosen=None
 for t in pd.read_html(StringIO(h.text)):
  low={re.sub(r'[^a-z0-9]+','',str(c).lower()):c for c in t.columns}; sk=next((low[k] for k in low if k in ('symbol','ticker','tickersymbol')),None); ck=next((low[k] for k in low if 'cik' in k),None); nk=next((low[k] for k in low if k in ('security','company','companyname','name')),None)
  if sk and ck and nk:
   chosen=t[[sk,nk,ck]].copy(); chosen.columns=['ticker','name','cik']; break
 if chosen is None: raise RuntimeError('NO_MEMBERSHIP_IDENTITY_TABLE_'+target)
 chosen['ticker']=chosen.ticker.map(norm_ticker); chosen['cik']=pd.to_numeric(chosen.cik,errors='coerce').astype('Int64')
 n=len(chosen); cik_cov=float(chosen.cik.notna().mean()) if n else 0.0; ticker_unique=int(chosen.ticker.nunique())==n; duplicate_tickers=int(chosen.ticker.duplicated(keep=False).sum()); ready=(480<=n<=520 and cik_cov>=.98 and ticker_unique and duplicate_tickers==0)
 return {'target':target,'revision_id':int(rev['revid']),'revision_timestamp':rev['timestamp'],'rows':n,'cik_coverage':cik_cov,'unique_tickers':ticker_unique,'duplicate_ticker_rows':duplicate_tickers,'ready':ready}
rows=[]
for d in DATES:
 try: rows.append(one(d))
 except Exception as e: rows.append({'target':d,'ready':False,'error':str(e)[:300]})
 time.sleep(.05)
ready=sum(bool(x.get('ready')) for x in rows); bad=[x for x in rows if not x.get('ready')]; all_ready=ready==len(rows)
out={'schema':'research.p459_sec_quarterly_membership_r1.v1','workload_id':'P459_SEC_QUARTERLY_MEMBERSHIP_R1','parent':'PIT_FUNDAMENTAL_CROSS_SECTIONAL_SELECTION','claim':'Test whether dated historical S&P 500 revisions provide a dense post-2015 as-of membership+CIK corpus suitable for causal filed-at SEC cross-sectional research, without current-membership backfill.','source_contract':{'source':'MediaWiki historical revisions of List of S&P 500 companies','targets':DATES,'selection':'latest revision at or before each quarter-end','current_membership_fill':False},'acceptance':{'rows_min':480,'rows_max':520,'cik_coverage_min':.98,'duplicate_ticker_rows_max':0,'all_40_quarterly_targets_required':True},'snapshots':rows,'counts':{'targets':len(rows),'ready':ready,'failed':len(bad)},'decision':'POST2015_QUARTERLY_MEMBERSHIP_CIK_CORPUS_READY' if all_ready else 'POST2015_QUARTERLY_MEMBERSHIP_CIK_CORPUS_NOT_READY','scientific_consequence':('Historical membership+issuer identity is sufficiently dense to execute one fixed annual/quarterly filed-at SEC fundamental selector with same-universe matched benchmark and chronology gates.' if all_ready else 'Do not infer model failure. Keep fundamental alpha blocked on exact failed quarter snapshots and repair only source/identity representation without current-member fill or constituent dropping.'),'boundaries':{'alpha_inference_this_run':False,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'counts':out['counts'],'failed_targets':[{'target':x['target'],'rows':x.get('rows'),'cik_coverage':x.get('cik_coverage'),'duplicates':x.get('duplicate_ticker_rows'),'error':x.get('error')} for x in bad]},sort_keys=True))

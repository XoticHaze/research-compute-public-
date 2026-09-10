from __future__ import annotations
import json,re
from io import StringIO
from pathlib import Path
import pandas as pd, requests
TARGET='2020-12-31'; NAMES=['AABA','BHGE','KDP','VMRK','WYND']
UA={'User-Agent':'CommandCenter-MarketResearch-PIT-Changes/1.0 research@example.invalid'}
OUT=Path('research/artifacts/pit_five_change_table_r4.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
p={'action':'query','format':'json','prop':'revisions','titles':'List of S&P 500 companies','rvprop':'ids|timestamp','rvlimit':'1','rvstart':TARGET+'T23:59:59Z'}
j=requests.get('https://en.wikipedia.org/w/api.php',params=p,headers=UA,timeout=30).json(); rev=next(iter(j['query']['pages'].values()))['revisions'][0]
h=requests.get(f"https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid={rev['revid']}",headers=UA,timeout=30); h.raise_for_status(); tabs=pd.read_html(StringIO(h.text))
hits={x:[] for x in NAMES}; scanned=0
for ti,t in enumerate(tabs):
 flat=' '.join(map(str,t.columns)).lower()
 if not (('added' in flat and 'removed' in flat) or ('date' in flat and ('reason' in flat or 'changes' in flat))): continue
 scanned+=1
 for _,row in t.iterrows():
  vals=[str(v) for v in row.tolist()]; raw=' | '.join(vals); up=raw.upper().replace('.','-')
  for x in NAMES:
   if re.search(r'(^|\W)'+re.escape(x)+r'(\W|$)',up):
    hits[x].append({'table_index':ti,'columns':[str(c) for c in t.columns],'row':{str(k):str(v) for k,v in row.to_dict().items()}})
out={'schema':'research.pit_five_change_table_r4.v1','workload_id':'PIT_FIVE_CHANGE_TABLE_R4','parent':'POINT_IN_TIME_FUNDAMENTAL_SELECTION','claim':'Search historical S&P change tables visible in the fixed 2020-12-31 point-in-time revision for explicit transition evidence concerning only the five unresolved 2015 aliases.','source':{'target_revision_date':TARGET,'revision_id':int(rev['revid']),'revision_timestamp':rev['timestamp'],'change_tables_scanned':scanned,'current_sec_used':False},'targets':NAMES,'hits':hits,'decision':'EXPLICIT_CHANGE_EVIDENCE_FOUND' if any(hits.values()) else 'NO_EXPLICIT_CHANGE_EVIDENCE','scientific_consequence':'Any row is discovery evidence only. A predecessor mapping may be admitted only when the row explicitly ties the target to a predecessor/rename/reorganization; otherwise keep the identity fail-closed.','boundaries':{'mapping_inference_without_explicit_row':False,'alpha_inference':False,'current_sec_identity_authority':False,'constituent_drop':False,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'revision':out['source'],'hit_counts':{k:len(v) for k,v in hits.items()},'hits':hits},sort_keys=True))

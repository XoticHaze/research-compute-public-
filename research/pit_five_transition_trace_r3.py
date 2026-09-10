from __future__ import annotations
import json,re,time
from io import StringIO
from pathlib import Path
import pandas as pd, requests

TARGETS=['AABA','BHGE','KDP','VMRK','WYND']
UA={'User-Agent':'CommandCenter-MarketResearch-PIT-Transition/1.0 research@example.invalid'}
OUT=Path('research/artifacts/pit_five_transition_trace_r3.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
def nt(x): return str(x).strip().upper().replace('.','-')
def snapshot(date):
 p={'action':'query','format':'json','prop':'revisions','titles':'List of S&P 500 companies','rvprop':'ids|timestamp','rvlimit':'1','rvstart':date+'T23:59:59Z'}
 j=requests.get('https://en.wikipedia.org/w/api.php',params=p,headers=UA,timeout=30).json(); rev=next(iter(j['query']['pages'].values()))['revisions'][0]
 h=requests.get(f"https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid={rev['revid']}",headers=UA,timeout=30); h.raise_for_status()
 tables=pd.read_html(StringIO(h.text)); ident=None; changes=[]
 for t in tables:
  cols=[re.sub(r'[^a-z0-9]+','',str(c).lower()) for c in t.columns]
  if any(c in ('symbol','ticker','tickersymbol') for c in cols) and any('cik' in c for c in cols):
   low={c:orig for c,orig in zip(cols,t.columns)}; sk=next(low[c] for c in low if c in ('symbol','ticker','tickersymbol')); ck=next(low[c] for c in low if 'cik' in c); nk=next((low[c] for c in low if c in ('security','company','companyname','name')),None)
   if nk is not None:
    ident=t[[sk,nk,ck]].copy(); ident.columns=['ticker','name','cik']; ident['ticker']=ident.ticker.map(nt); ident['cik']=pd.to_numeric(ident.cik,errors='coerce').astype('Int64')
  flat=' '.join(map(str,t.columns)).lower()
  if ('added' in flat and 'removed' in flat) or ('date' in flat and 'reason' in flat):
   changes.append(t.astype(str))
 return {'date':date,'revision_id':int(rev['revid']),'revision_timestamp':rev['timestamp']},ident,changes
# Month-end snapshots densely cover short-lived rename/reorg states while remaining point-in-time.
dates=pd.date_range('2016-01-31','2020-12-31',freq='ME').strftime('%Y-%m-%d').tolist()
appear={t:[] for t in TARGETS}; change_hits={t:[] for t in TARGETS}; revisions=[]
seen_revs=set()
for date in dates:
 meta,ident,changes=snapshot(date)
 if meta['revision_id'] in seen_revs: continue
 seen_revs.add(meta['revision_id']); revisions.append(meta)
 if ident is not None:
  for target in TARGETS:
   z=ident.loc[ident.ticker==target]
   for _,r in z.iterrows(): appear[target].append({'date':date,'revision_id':meta['revision_id'],'ticker':target,'name':str(r['name']),'cik':None if pd.isna(r.cik) else str(int(r.cik))})
 for target in TARGETS:
  for ti,t in enumerate(changes):
   mask=t.apply(lambda row: row.astype(str).str.upper().str.replace('.','-',regex=False).str.contains(r'(^|\W)'+re.escape(target)+r'(\W|$)',regex=True).any(),axis=1)
   for _,row in t.loc[mask].iterrows(): change_hits[target].append({'snapshot_date':date,'revision_id':meta['revision_id'],'table_index':ti,'row':{str(k):str(v) for k,v in row.to_dict().items()}})
 time.sleep(.05)
rows=[]
for t in TARGETS:
 obs=appear[t]; hits=change_hits[t]
 rows.append({'membership_ticker':t,'appearance_count':len(obs),'first_appearance':obs[0] if obs else None,'last_appearance':obs[-1] if obs else None,'distinct_dated_ciks':sorted({o['cik'] for o in obs if o['cik']}),'dated_appearances':obs,'change_table_hits':hits})
out={'schema':'research.pit_five_transition_trace_r3.v1','workload_id':'PIT_FIVE_TRANSITION_TRACE_R3','parent':'POINT_IN_TIME_FUNDAMENTAL_SELECTION','claim':'Trace only the five remaining 2015 alias residuals across point-in-time monthly S&P snapshots and contemporaneously visible change tables. This is source discovery, not mapping authority by itself.','source_contract':{'targets':TARGETS,'window':'2016-01-31 through 2020-12-31 month-end revisions','current_sec_used':False,'mapping_inference_this_run':False},'revisions_sampled':revisions,'rows':rows,'decision':'TRANSITION_EVIDENCE_MATERIALIZED','scientific_consequence':'Use first appearances, dated CIKs, and explicit historical change-table rows to construct only evidence-backed predecessor mappings. A target with no appearance/change evidence remains fail-closed; do not hand-map it.','boundaries':{'alpha_inference':False,'current_sec_identity_authority':False,'constituent_drop':False,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'summary':{r['membership_ticker']:{'appearances':r['appearance_count'],'first':r['first_appearance'],'ciks':r['distinct_dated_ciks'],'change_hits':len(r['change_table_hits'])} for r in rows}},sort_keys=True))

from __future__ import annotations
import json,re,hashlib
from io import StringIO
from pathlib import Path
import pandas as pd, requests

TARGET='2015-12-31'; UA={'User-Agent':'CommandCenter-MarketResearch-PIT-CorporateAction/1.0 research@example.invalid'}
OUT=Path('research/artifacts/pit_five_corporate_action_resolver_r5.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
# Fixed dated primary records. These prove transition identity; current SEC ticker lookup is never used.
CASES={
 'AABA':{'pred':'YHOO','url':'https://www.sec.gov/Archives/edgar/data/1011006/000119312517206955/d389206d8k.htm','need':['changed its name to','AABA','Previously','YHOO']},
 'BHGE':{'pred':'BHI','url':'https://www.sec.gov/Archives/edgar/data/1701605/000119312517220852/d343521d8k12b.htm','need':['successor issuer to Baker Hughes','common stock of Baker Hughes']},
 'KDP':{'pred':'DPS','url':'https://www.sec.gov/Archives/edgar/data/1418135/000141813519000007/kdp-10kx12312018.htm','need':['Dr Pepper Snapple Group','DPS','changed its name to','Keurig Dr Pepper']},
 'WYND':{'pred':'WYN','url':'https://www.sec.gov/Archives/edgar/data/1361658/000110465918032536/a18-13272_2ex99d1.htm','need':['Wyndham Worldwide Corporation','renamed Wyndham Destinations','WYN','WYND']},
 'VMRK':{'pred':'EQR','url':'https://www.sec.gov/Archives/edgar/data/906107/000090610726000044/xslF345X06/form3.xml','need':['Vivmark Residential','f/k/a Equity Residential','VMRK']},
}
def norm(x): return str(x).strip().upper().replace('.','-')
def revision_2015():
 p={'action':'query','format':'json','prop':'revisions','titles':'List of S&P 500 companies','rvprop':'ids|timestamp','rvlimit':'1','rvstart':TARGET+'T23:59:59Z'}
 j=requests.get('https://en.wikipedia.org/w/api.php',params=p,headers=UA,timeout=30).json(); rev=next(iter(j['query']['pages'].values()))['revisions'][0]
 h=requests.get(f"https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid={rev['revid']}",headers=UA,timeout=30); h.raise_for_status()
 for t in pd.read_html(StringIO(h.text)):
  low={re.sub(r'[^a-z0-9]+','',str(c).lower()):c for c in t.columns}; sk=next((low[k] for k in low if k in ('symbol','ticker','tickersymbol')),None); ck=next((low[k] for k in low if 'cik' in k),None); nk=next((low[k] for k in low if k in ('security','company','companyname','name')),None)
  if sk and ck and nk:
   q=t[[sk,nk,ck]].copy(); q.columns=['ticker','name','cik']; q['ticker']=q.ticker.map(norm); q['cik']=pd.to_numeric(q.cik,errors='coerce').astype('Int64'); return rev,q
 raise SystemExit('NO_2015_IDENTITY_TABLE')
rev,w=revision_2015(); rows=[]
for future,c in CASES.items():
 r=requests.get(c['url'],headers=UA,timeout=30); r.raise_for_status(); text=re.sub(r'\s+',' ',r.text)
 checks={needle:bool(re.search(re.escape(needle),text,re.I)) for needle in c['need']}
 old=w.loc[w.ticker==c['pred']]
 historical_unique=len(old)==1
 rec={'membership_ticker':future,'historical_2015_ticker':c['pred'],'primary_record_url':c['url'],'primary_record_sha256':hashlib.sha256(r.content).hexdigest(),'transition_text_checks':checks,'all_transition_checks_pass':all(checks.values()),'historical_2015_row_unique':historical_unique}
 if historical_unique:
  x=old.iloc[0]; rec.update({'historical_2015_name':str(x['name']),'historical_2015_cik':None if pd.isna(x.cik) else str(int(x.cik))})
 rec['resolved']=bool(rec['all_transition_checks_pass'] and historical_unique)
 rows.append(rec)
resolved=[r for r in rows if r['resolved']]; residual=[r['membership_ticker'] for r in rows if not r['resolved']]
out={'schema':'research.pit_five_corporate_action_resolver_r5.v1','workload_id':'PIT_FIVE_CORPORATE_ACTION_RESOLVER_R5','parent':'POINT_IN_TIME_FUNDAMENTAL_SELECTION','claim':'Resolve the final five frozen 2015 ticker aliases only when a fixed dated primary corporate-action/SEC record proves the transition and the predecessor ticker exists uniquely in the contemporaneous 2015 S&P identity table.','source_contract':{'historical_identity_revision_id':int(rev['revid']),'historical_identity_revision_timestamp':rev['timestamp'],'target':TARGET,'current_sec_ticker_mapping_used':False,'cases':{k:{'predecessor':v['pred'],'primary_record':v['url']} for k,v in CASES.items()}},'rows':rows,'counts':{'input':len(rows),'resolved':len(resolved),'unresolved':len(residual)},'unresolved':residual,'decision':'ALL_FINAL_FIVE_CORPORATE_ACTION_ALIASES_RESOLVED' if not residual else 'FINAL_FIVE_CORPORATE_ACTION_RESOLUTION_INCOMPLETE','scientific_consequence':('The complete fixed 15-alias seam now has evidence-backed historical predecessors: combine these five corporate-action mappings with the prior two exact-name and eight historical-CIK mappings, then rerun the all-target PIT identity gate before any SEC filed-at alpha inference.' if not residual else 'Consume only cases with both primary transition proof and unique 2015 predecessor row. Keep residuals fail-closed and do not infer alpha.'),'boundaries':{'alpha_inference_this_run':False,'current_sec_identity_authority':False,'constituent_drop':False,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'counts':out['counts'],'resolved':[{k:r.get(k) for k in ('membership_ticker','historical_2015_ticker','historical_2015_name','historical_2015_cik','resolved')} for r in rows],'unresolved':residual},sort_keys=True))

from __future__ import annotations
import json,re,time
from io import StringIO
from pathlib import Path
import pandas as pd,requests
UA={'User-Agent':'CommandCenter-MarketResearch-PITTransition/1.0 research@example.invalid'}
CASES={
 'AABA':{'old':'YHOO','url':'https://altaba.com/press-releases/altaba-completes-name-change-registers-investment-company/','need':['YHOO','AABA']},
 'BHGE':{'old':'BHI','url':'https://investors.bakerhughes.com/news/press-releases/news-details/2017/Baker-Hughes-Stockholders-Approve-Combination-with-GE-Oil-Gas-06-30-2017/default.aspx','need':['BHI','BHGE']},
 'KDP':{'old':'DPS','url':'https://investors.keurigdrpepper.com/2018-06-26-Dr-Pepper-Snapple-Group-Sets-Record-Date-for-Special-Dividend-Contemplated-by-Keurig-Transaction-and-Provides-Estimated-Earnings-and-Profits','need':['DPS','KDP']},
 'VMRK':{'old':'EQR','url':'https://investors.vivmarkresidential.com/news-events/press-releases/detail/113/vivmark-residential-launches-as-one-of-the-countrys-leading-real-estate-companies','need':['EQR','VMRK']},
 'WYND':{'old':'WYN','url':'https://investor.travelandleisureco.com/news-events/press-releases/detail/230/wyndham-destinations-rings-opening-bell-on-new-york-stock-exchange','need':['Wyndham Worldwide','WYND']},
}
OUT=Path('research/artifacts/p456_pit_five_transition_trace_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
def nt(x): return str(x).strip().upper().replace('.','-')
def base2015():
 p={'action':'query','format':'json','prop':'revisions','titles':'List of S&P 500 companies','rvprop':'ids|timestamp','rvlimit':'1','rvstart':'2015-12-31T23:59:59Z'}
 j=requests.get('https://en.wikipedia.org/w/api.php',params=p,headers=UA,timeout=30).json(); rev=next(iter(j['query']['pages'].values()))['revisions'][0]
 h=requests.get(f"https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid={rev['revid']}",headers=UA,timeout=30); h.raise_for_status()
 for t in pd.read_html(StringIO(h.text)):
  low={re.sub(r'[^a-z0-9]+','',str(c).lower()):c for c in t.columns}; sk=next((low[k] for k in low if k in ('symbol','ticker','tickersymbol')),None); ck=next((low[k] for k in low if 'cik' in k),None); nk=next((low[k] for k in low if k in ('security','company','companyname','name')),None)
  if sk and ck and nk:
   q=t[[sk,nk,ck]].copy(); q.columns=['ticker','name','cik']; q['ticker']=q.ticker.map(nt); q['cik']=pd.to_numeric(q.cik,errors='coerce').astype('Int64'); return {'revision_id':int(rev['revid']),'revision_timestamp':rev['timestamp']},q
 raise RuntimeError('NO_2015_IDENTITY_TABLE')
meta,base=base2015(); rows=[]
for new,s in CASES.items():
 rec={'membership_ticker':new,'historical_2015_ticker':s['old'],'transition_source':s['url']}
 try:
  h=requests.get(s['url'],headers=UA,timeout=30); h.raise_for_status(); txt=re.sub(r'\s+',' ',h.text)
  missing=[x for x in s['need'] if x.lower() not in txt.lower()]; rec['source_http_status']=h.status_code; rec['transition_tokens_present']=not missing; rec['missing_tokens']=missing
 except Exception as e:
  rec.update({'source_http_status':None,'transition_tokens_present':False,'source_error':str(e)[:300]})
 z=base.loc[base.ticker==s['old']]
 if len(z)==1:
  r=z.iloc[0]; rec.update({'historical_2015_name':str(r['name']),'historical_cik':str(int(r['cik'])) if not pd.isna(r['cik']) else None,'historical_row_unique':True})
 else: rec.update({'historical_row_unique':False,'historical_candidate_count':int(len(z))})
 rec['status']='TRANSITION_AND_2015_IDENTITY_CONFIRMED' if rec.get('transition_tokens_present') and rec.get('historical_row_unique') and rec.get('historical_cik') else 'FAIL_CLOSED'
 rows.append(rec); time.sleep(.1)
resolved=[r for r in rows if r['status']=='TRANSITION_AND_2015_IDENTITY_CONFIRMED']; unresolved=[r['membership_ticker'] for r in rows if r['status']!='TRANSITION_AND_2015_IDENTITY_CONFIRMED']
out={'schema':'research.p456_pit_five_transition_trace_r1.v1','workload_id':'P456_PIT_FIVE_TRANSITION_TRACE_R1','parent':'POINT_IN_TIME_FUNDAMENTAL_SELECTION','claim':'Resolve only the frozen five remaining aliases using dated corporate-action/company transition evidence plus the exact 2015 historical S&P identity table; no current SEC ticker-CIK lookup, constituent dropping, or alpha inference.','source_contract':{'historical_2015_snapshot':meta,'cases':CASES,'current_sec_used':False},'rows':rows,'counts':{'input':5,'resolved':len(resolved),'unresolved':len(unresolved)},'unresolved':unresolved,'decision':'ALL_FIVE_TRANSITION_IDENTITIES_CONFIRMED' if not unresolved else 'TRANSITION_TRACE_PARTIAL','scientific_consequence':'If all five confirm, combine with the prior ten resolved aliases and rerun the all-target PIT identity gate before filed-at SEC fundamentals; otherwise keep only unresolved aliases fail-closed.','boundaries':{'alpha_inference_this_run':False,'current_sec_identity_authority':False,'constituent_drop':False,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'resolved':[{k:r.get(k) for k in ('membership_ticker','historical_2015_ticker','historical_2015_name','historical_cik')} for r in resolved],'unresolved':unresolved},sort_keys=True))

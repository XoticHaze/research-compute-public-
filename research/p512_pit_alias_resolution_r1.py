from __future__ import annotations
import json,re
from difflib import SequenceMatcher
from io import StringIO
from pathlib import Path
import pandas as pd,requests,pitindex
TARGET='2015-12-31';UA={'User-Agent':'CommandCenter-MarketResearch-P512/1.0 research@example.invalid'};OUT=Path('research/artifacts/p512_pit_alias_resolution_r1.json');OUT.parent.mkdir(parents=True,exist_ok=True)
def nt(x):
 s=str(x).strip().upper().replace('.','-') if x is not None else '';return s or None
def nn(x):
 s=str(x).upper();s=re.sub(r'\b(INCORPORATED|INC|CORPORATION|CORP|COMPANY|CO|PLC|LTD|LIMITED|HOLDINGS|HOLDING|GROUP|THE)\b',' ',s);return re.sub(r'[^A-Z0-9]+','',s)
def nc(x):
 if x is None or pd.isna(x):return None
 s=re.sub(r'[^0-9]','',str(x));return str(int(s)) if s else None
p={'action':'query','format':'json','prop':'revisions','titles':'List of S&P 500 companies','rvprop':'ids|timestamp','rvlimit':'1','rvstart':TARGET+'T23:59:59Z'}
j=requests.get('https://en.wikipedia.org/w/api.php',params=p,headers=UA,timeout=30).json();rev=next(iter(j['query']['pages'].values()))['revisions'][0]
h=requests.get(f"https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid={rev['revid']}",headers=UA,timeout=30);h.raise_for_status();w=None
for t in pd.read_html(StringIO(h.text)):
 low={re.sub(r'[^a-z0-9]+','',str(c).lower()):c for c in t.columns};sk=next((k for k in low if k in ('symbol','ticker','tickersymbol')),None);ck=next((k for k in low if 'cik' in k),None);nk=next((k for k in low if k in ('security','company','companyname','name')),None)
 if sk and ck and nk:
  w=t.copy();w['ticker_norm']=w[low[sk]].map(nt);w['wiki_cik']=w[low[ck]].map(nc);w['name_raw']=w[low[nk]].astype(str);w['name_norm']=w.name_raw.map(nn);break
if w is None:raise SystemExit('NO_WIKI_TABLE')
pit=pitindex.get_constituents(TARGET,index='sp500').copy();pit['ticker_norm']=pit.ticker.map(nt);pit['pit_cik']=pit.cik.map(nc);pit['name_raw']=pit['name'].astype(str);pit['name_norm']=pit.name_raw.map(nn)
ps=set(pit.ticker_norm.dropna());ws=set(w.ticker_norm.dropna());pit_only=sorted(ps-ws);wiki_only=sorted(ws-ps)
wp=w[w.ticker_norm.isin(wiki_only)][['ticker_norm','wiki_cik','name_raw','name_norm']].drop_duplicates('ticker_norm')
rows=[]
for _,r in pit[pit.ticker_norm.isin(pit_only)].iterrows():
 scores=[]
 for _,x in wp.iterrows():
  sim=SequenceMatcher(None,r.name_norm,x.name_norm).ratio();exact=bool(r.name_norm and r.name_norm==x.name_norm)
  scores.append((1 if exact else 0,sim,x))
 scores.sort(key=lambda z:(z[0],z[1]),reverse=True);best=scores[0];second=scores[1] if len(scores)>1 else (0,0,None);unique_margin=best[1]-second[1]
 accepted=bool(best[0]==1 or (best[1]>=0.84 and unique_margin>=0.08))
 x=best[2]
 rows.append({'pit_ticker':r.ticker_norm,'pit_name':r.name_raw,'pit_cik_unsafe':r.pit_cik,'historical_ticker':x.ticker_norm if accepted else None,'historical_name':x.name_raw if accepted else None,'historical_cik':x.wiki_cik if accepted else None,'name_similarity':round(float(best[1]),6),'runner_up_similarity':round(float(second[1]),6),'unique_margin':round(float(unique_margin),6),'match_class':'EXACT_NORMALIZED_NAME' if accepted and best[0] else ('HIGH_CONFIDENCE_UNIQUE_NAME' if accepted else 'UNRESOLVED')})
resolved=sum(x['historical_ticker'] is not None for x in rows);hist_targets={x['historical_ticker'] for x in rows if x['historical_ticker']};unique=len(hist_targets)==resolved;all15=len(rows)==15 and resolved==15 and unique
dec='PIT_2015_ALIAS_GATE_PASSED' if all15 else 'PIT_2015_ALIAS_GATE_NOT_READY'
out={'schema':'research.p512_pit_alias_resolution_r1.v1','workload_id':'P512_PIT_ALIAS_RESOLUTION_R1','parent':'POINT_IN_TIME_FUNDAMENTAL_SELECTION','claim':'Resolve the exact frozen 2015 pitindex-vs-contemporaneous-Wikipedia ticker non-overlaps by contemporaneous company-name identity only. pitindex native CIK is retained only as explicitly unsafe diagnostic context and cannot authorize a match. No constituent dropping, current SEC identity, date relaxation, manual target editing, or post-result alias insertion.','source_contract':{'membership':'pitindex historical S&P500 constituents at '+TARGET,'historical_identity':'Wikipedia historical revision '+str(rev['revid'])+' at '+str(rev['timestamp']),'target':TARGET,'matching':'normalized contemporaneous company name; exact or predeclared similarity>=0.84 with runner-up margin>=0.08'},'counts':{'pit_members':len(ps),'wiki_members':len(ws),'pit_only':len(pit_only),'wiki_only':len(wiki_only),'resolved':resolved,'unique_historical_targets':len(hist_targets)},'pit_only_tickers':pit_only,'wiki_only_tickers':wiki_only,'aliases':rows,'acceptance':{'required_frozen_nonoverlaps':15,'all_resolved':True,'one_to_one':True,'current_sec_identity_allowed':False,'constituent_drop_allowed':False},'decision':dec,'scientific_consequence':('The frozen 2015 ticker-alias identity seam passes. Historical membership timing may now be joined to contemporaneous issuer identity using these dated aliases; the next scientific boundary is to rerun the filed-at SEC feature join with all targets retained and no current-CIK authority.' if all15 else 'Historical identity seam remains blocked. Do not drop unresolved constituents, use current SEC ticker identity, or add aliases after seeing results; preserve exact unresolved rows for a genuinely independent dated identity source.'),'boundaries':{'fundamental_alpha_inference_this_run':False,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False));print(json.dumps({'decision':dec,'counts':out['counts'],'aliases':rows},sort_keys=True))

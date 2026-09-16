from __future__ import annotations
import json,re,time
from io import StringIO
from pathlib import Path
import pandas as pd,requests,pitindex
TARGET='2015-12-31'; OUT=Path('research/artifacts/p530_pit_wikidata_alias_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
UA={'User-Agent':'CommandCenter-MarketResearch-P530/1.0 research@example.invalid'}
def nt(x):
    s=str(x).strip().upper().replace('.','-') if x is not None else ''; return s or None
# Reconstruct the exact frozen P512 non-overlap sets from the same source pins/date.
p={'action':'query','format':'json','prop':'revisions','titles':'List of S&P 500 companies','rvprop':'ids|timestamp','rvlimit':'1','rvstart':TARGET+'T23:59:59Z'}
j=requests.get('https://en.wikipedia.org/w/api.php',params=p,headers=UA,timeout=30).json(); rev=next(iter(j['query']['pages'].values()))['revisions'][0]
h=requests.get(f"https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid={rev['revid']}",headers=UA,timeout=30); h.raise_for_status(); w=None
for t in pd.read_html(StringIO(h.text)):
    low={re.sub(r'[^a-z0-9]+','',str(c).lower()):c for c in t.columns}; sk=next((k for k in low if k in ('symbol','ticker','tickersymbol')),None)
    if sk:
        w=t.copy(); w['ticker_norm']=w[low[sk]].map(nt); break
if w is None: raise SystemExit('NO_WIKI_TABLE')
pit=pitindex.get_constituents(TARGET,index='sp500').copy(); pit['ticker_norm']=pit.ticker.map(nt)
ps=set(pit.ticker_norm.dropna()); ws=set(w.ticker_norm.dropna()); pit_only=sorted(ps-ws); wiki_only=sorted(ws-ps)
# Preserve P512's two already-resolved rows; this child acts only on the exact remainder.
already={'CBRE':'CBG','WELL':'HCN'}; unresolved=[x for x in pit_only if x not in already]
values=' '.join(json.dumps(x) for x in unresolved)
query=f'''SELECT ?target ?item ?hist ?start ?end WHERE {{
  VALUES ?target {{ {values} }}
  ?item p:P249 ?curStmt . ?curStmt ps:P249 ?target .
  ?item p:P249 ?histStmt . ?histStmt ps:P249 ?hist .
  OPTIONAL {{ ?histStmt pq:P580 ?start . }}
  OPTIONAL {{ ?histStmt pq:P582 ?end . }}
}}'''
r=requests.get('https://query.wikidata.org/sparql',params={'query':query,'format':'json'},headers=UA,timeout=60); r.raise_for_status(); bindings=r.json()['results']['bindings']
rows=[]
for b in bindings:
    rows.append({'target':nt(b['target']['value']),'item':b['item']['value'].rsplit('/',1)[-1],'hist':nt(b['hist']['value']),'start':b.get('start',{}).get('value'),'end':b.get('end',{}).get('value')})
def active_2015(x):
    # Require explicit statement dating sufficient to establish the ticker covered the frozen target date.
    s=x['start'][:10] if x['start'] else None; e=x['end'][:10] if x['end'] else None
    return bool((s is not None or e is not None) and (s is None or s<=TARGET) and (e is None or e>=TARGET))
resolved=[]; detail=[]
for target in unresolved:
    cand=[x for x in rows if x['target']==target and x['hist'] in wiki_only and active_2015(x)]
    uniq=sorted({x['hist'] for x in cand})
    accepted=len(uniq)==1
    detail.append({'pit_ticker':target,'candidate_historical_tickers':uniq,'dated_statements':cand,'match_class':'UNIQUE_WIKIDATA_DATED_TICKER_INTERVAL' if accepted else 'UNRESOLVED'})
    if accepted: resolved.append({'pit_ticker':target,'historical_ticker':uniq[0],'source':'Wikidata P249 ticker statement with P580/P582 interval covering '+TARGET})
all_aliases=[{'pit_ticker':k,'historical_ticker':v,'source':'P512 contemporaneous exact-name resolution'} for k,v in already.items()]+resolved
all_targets={x['historical_ticker'] for x in all_aliases}; passed=len(all_aliases)==15 and len(all_targets)==15
decision='PIT_2015_ALIAS_GATE_PASSED_INDEPENDENT_DATED_SOURCE' if passed else 'PIT_2015_ALIAS_GATE_STILL_NOT_READY'
out={'schema':'research.p530_pit_wikidata_alias_r1.v1','workload_id':'P530_PIT_WIKIDATA_ALIAS_R1','parent':'POINT_IN_TIME_FUNDAMENTAL_SELECTION','claim':'Use a genuinely independent structured issuer-history source to resolve only the exact P512 unresolved 2015 ticker identities.','source_contract':{'membership':'pitindex historical S&P500 constituents at '+TARGET,'frozen_historical_target_set':'Wikipedia revision '+str(rev['revid'])+' at '+str(rev['timestamp']),'independent_identity_source':'Wikidata ticker-symbol statements (P249) with dated start/end qualifiers P580/P582','acceptance':'for each unresolved pit ticker, exactly one ticker in the frozen Wikipedia-only set must have a Wikidata ticker statement whose explicit dated interval covers '+TARGET,'current_sec_cik_allowed':False,'name_similarity_allowed':False,'manual_alias_insertion_allowed':False,'constituent_drop_allowed':False},'counts':{'pit_only':len(pit_only),'wiki_only':len(wiki_only),'p512_already_resolved':len(already),'p530_newly_resolved':len(resolved),'remaining_unresolved':len(unresolved)-len(resolved),'total_resolved':len(all_aliases)},'newly_resolved':resolved,'detail':detail,'combined_aliases':sorted(all_aliases,key=lambda x:x['pit_ticker']),'decision':decision,'scientific_consequence':('The frozen 2015 identity seam is fully resolved without current SEC identity or manual row insertion; the filed-at SEC fundamental feature join may be rerun with all constituents retained.' if passed else 'Keep the filed-at SEC fundamental alpha gate closed for the remaining exact unresolved identities. Do not relax dates, matching, or targets; a further independent dated issuer-history source is required.'),'boundaries':{'fundamental_alpha_inference_this_run':False,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'counts':out['counts'],'newly_resolved':resolved},sort_keys=True))

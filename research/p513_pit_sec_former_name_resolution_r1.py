from __future__ import annotations
import json,re,time
from io import StringIO
from pathlib import Path
import pandas as pd,requests,pitindex
TARGET='2015-12-31';PIN='2df030e5c9be7c83cf4b28c3d8597d74d274757e';UA={'User-Agent':'CommandCenter-MarketResearch-P513/1.0 research@example.invalid'};OUT=Path('research/artifacts/p513_pit_sec_former_name_resolution_r1.json');OUT.parent.mkdir(parents=True,exist_ok=True)
def nt(x):
 s=str(x).strip().upper().replace('.','-') if x is not None else '';return s or None
def nn(x):
 s=str(x).upper();s=re.sub(r'\b(INCORPORATED|INC|CORPORATION|CORP|COMPANY|CO|PLC|LTD|LIMITED|HOLDINGS|HOLDING|GROUP|THE|CLASS|A|B)\b',' ',s);return re.sub(r'[^A-Z0-9]+','',s)
def nc(x):
 if x is None or pd.isna(x):return None
 s=re.sub(r'[^0-9]','',str(x));return str(int(s)) if s else None
def get(url):
 r=requests.get(url,headers=UA,timeout=30);r.raise_for_status();return r
p={'action':'query','format':'json','prop':'revisions','titles':'List of S&P 500 companies','rvprop':'ids|timestamp','rvlimit':'1','rvstart':TARGET+'T23:59:59Z'}
j=requests.get('https://en.wikipedia.org/w/api.php',params=p,headers=UA,timeout=30).json();rev=next(iter(j['query']['pages'].values()))['revisions'][0]
h=get(f"https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid={rev['revid']}");w=None
for t in pd.read_html(StringIO(h.text)):
 low={re.sub(r'[^a-z0-9]+','',str(c).lower()):c for c in t.columns};sk=next((k for k in low if k in ('symbol','ticker','tickersymbol')),None);ck=next((k for k in low if 'cik' in k),None);nk=next((k for k in low if k in ('security','company','companyname','name')),None)
 if sk and ck and nk:
  w=t.copy();w['ticker_norm']=w[low[sk]].map(nt);w['wiki_cik']=w[low[ck]].map(nc);w['wiki_name']=w[low[nk]].astype(str);w['name_norm']=w.wiki_name.map(nn);break
if w is None:raise SystemExit('NO_WIKI_TABLE')
pit=pitindex.get_constituents(TARGET,index='sp500').copy();pit['ticker_norm']=pit.ticker.map(nt);pit['pit_name']=pit['name'].where(pit['name'].notna(),None);pit['name_norm']=pit.pit_name.map(lambda x:nn(x) if x else '')
ps=set(pit.ticker_norm.dropna());ws=set(w.ticker_norm.dropna());pit_only=sorted(ps-ws);wiki_only=sorted(ws-ps)
# P512 exact-name matches are excluded from the unresolved set without re-tuning their rule.
exact={}
for _,r in pit[pit.ticker_norm.isin(pit_only)].iterrows():
 if not r.name_norm:continue
 cand=w[(w.ticker_norm.isin(wiki_only))&(w.name_norm==r.name_norm)]
 if len(cand)==1:exact[r.ticker_norm]=cand.iloc[0].ticker_norm
unresolved=[x for x in pit_only if x not in exact]
current=get('https://www.sec.gov/files/company_tickers.json').json();cur={nt(v['ticker']):{'cik':str(int(v['cik_str'])),'title':str(v['title'])} for v in current.values()}
ww=w[w.ticker_norm.isin(wiki_only)].drop_duplicates('ticker_norm').set_index('ticker_norm')
rows=[]
for ticker in unresolved:
 loc=cur.get(ticker); evidence=[]
 if loc:
  cik=loc['cik']; sub=get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json").json(); names=[{'name':str(sub.get('name') or loc['title']),'from':None,'to':None,'kind':'current_entity_name'}]
  for f in sub.get('formerNames') or []:names.append({'name':str(f.get('name') or ''),'from':f.get('from'),'to':f.get('to'),'kind':'sec_former_name'})
  for ht,wr in ww.iterrows():
   if nc(wr.wiki_cik)!=cik:continue
   for n in names:
    if nn(n['name']) and nn(n['name'])==nn(wr.wiki_name): evidence.append({'historical_ticker':ht,'historical_name':str(wr.wiki_name),'historical_cik':nc(wr.wiki_cik),'sec_name':n['name'],'sec_name_kind':n['kind'],'sec_from':n['from'],'sec_to':n['to']})
  time.sleep(.11)
 uniq={e['historical_ticker'] for e in evidence}; accepted=len(uniq)==1; chosen=next(iter(uniq)) if accepted else None; ev=next((e for e in evidence if e['historical_ticker']==chosen),None) if accepted else None
 rows.append({'pit_ticker':ticker,'pit_name':next((str(x) for x in pit.loc[pit.ticker_norm==ticker,'pit_name'] if x is not None),None),'locator_current_sec_cik':loc['cik'] if loc else None,'locator_only_not_historical_authority':True,'historical_ticker':chosen,'historical_name':ev['historical_name'] if ev else None,'historical_cik':ev['historical_cik'] if ev else None,'sec_name_evidence':ev,'candidate_match_count':len(uniq),'match_class':'HISTORICAL_WIKI_CIK_PLUS_SEC_FORMER_NAME' if accepted else 'UNRESOLVED'})
resolved=sum(r['historical_ticker'] is not None for r in rows);total_resolved=resolved+len(exact);one_to_one=len({*exact.values(),*[r['historical_ticker'] for r in rows if r['historical_ticker']]})==total_resolved;passed=len(pit_only)==15 and total_resolved==15 and one_to_one
dec='PIT_2015_ALIAS_GATE_PASSED' if passed else 'PIT_2015_ALIAS_GATE_NOT_READY'
out={'schema':'research.p513_pit_sec_former_name_resolution_r1.v1','workload_id':'P513_PIT_SEC_FORMER_NAME_RESOLUTION_R1','parent':'POINT_IN_TIME_FUNDAMENTAL_SELECTION','claim':'Second-source resolution of the exact frozen 2015 alias seam. Current SEC ticker-to-CIK is permitted only as a locator into SEC submissions; it cannot authorize historical identity. A new alias is accepted only when the contemporaneous 2015 Wikipedia row has the same CIK and its historical company name exactly matches an SEC submissions current/former issuer name. P512 exact-name matches remain frozen. No target dropping, threshold search, current-CIK-only mapping, date relaxation, or manual alias insertion.','source_contract':{'membership':'pitindex@'+PIN+' at '+TARGET,'historical_membership_identity':'Wikipedia revision '+str(rev['revid'])+' '+str(rev['timestamp']),'independent_issuer_history':'SEC submissions formerNames fetched in-run','current_sec_company_tickers':'locator only, never historical identity authority'},'p512_frozen_exact_aliases':exact,'counts':{'pit_only':len(pit_only),'p512_exact_resolved':len(exact),'p513_new_resolved':resolved,'total_resolved':total_resolved,'remaining':len(pit_only)-total_resolved},'resolution_rows':rows,'decision':dec,'scientific_consequence':('All 15 frozen 2015 ticker non-overlaps are now accounted for by dated/contemporaneous identity evidence without using current SEC CIK as historical authority. Reopen the filed-at SEC feature join with every constituent retained and these immutable alias mappings.' if passed else 'SEC issuer-name history resolves only a subset of the remaining frozen aliases. Keep the filed-at SEC join closed and preserve the exact residual unresolved identities for a third independent dated corporate-action source; do not relax the identity gate.'),'boundaries':{'fundamental_alpha_inference_this_run':False,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False));print(json.dumps({'decision':dec,'counts':out['counts'],'p512':exact,'new':[r for r in rows if r['historical_ticker']],'unresolved':[r['pit_ticker'] for r in rows if not r['historical_ticker']]},sort_keys=True))

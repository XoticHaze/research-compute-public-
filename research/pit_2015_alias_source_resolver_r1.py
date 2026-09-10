from __future__ import annotations
import json,re,unicodedata,math
from io import StringIO
from pathlib import Path
import pandas as pd, requests, pitindex

TARGET='2015-12-31'
FIXED=['AABA','ANDV','APTV','ARNC','BHGE','BKNG','CBRE','JEF','KDP','SPGI','TPR','UAA','VMRK','WELL','WYND']
UA={'User-Agent':'CommandCenter-MarketResearch-PIT-Alias/1.0 research@example.invalid'}
OUT=Path('research/artifacts/pit_2015_alias_source_resolver_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
def nt(x): return str(x).strip().upper().replace('.','-') if x is not None else None
def norm_name(x):
    s=unicodedata.normalize('NFKD',str(x)).encode('ascii','ignore').decode().lower(); s=s.replace('&',' and '); s=re.sub(r'[^a-z0-9]+',' ',s)
    toks=s.split(); suffix={'inc','incorporated','corp','corporation','co','company','ltd','limited','plc','llc','group','holdings','holding'}
    while toks and toks[-1] in suffix: toks.pop()
    return ' '.join(toks)
def clean(x):
    if isinstance(x,dict): return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)): return [clean(v) for v in x]
    if isinstance(x,float) and not math.isfinite(x): return None
    if pd.isna(x) if not isinstance(x,(dict,list,tuple)) else False: return None
    if hasattr(x,'item'):
        try:return clean(x.item())
        except Exception:pass
    return x
def wiki():
    p={'action':'query','format':'json','prop':'revisions','titles':'List of S&P 500 companies','rvprop':'ids|timestamp','rvlimit':'1','rvstart':TARGET+'T23:59:59Z'}
    j=requests.get('https://en.wikipedia.org/w/api.php',params=p,headers=UA,timeout=30).json(); rev=next(iter(j['query']['pages'].values()))['revisions'][0]
    h=requests.get(f"https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid={rev['revid']}",headers=UA,timeout=30); h.raise_for_status()
    for t in pd.read_html(StringIO(h.text)):
        low={re.sub(r'[^a-z0-9]+','',str(c).lower()):c for c in t.columns}; sk=next((low[k] for k in low if k in ('symbol','ticker','tickersymbol')),None); ck=next((low[k] for k in low if 'cik' in k),None); nk=next((low[k] for k in low if k in ('security','company','companyname','name')),None)
        if sk and ck and nk:
            q=t[[sk,nk,ck]].copy(); q.columns=['wiki_ticker','wiki_name','wiki_cik']; q['wiki_ticker']=q.wiki_ticker.map(nt); q['name_key']=q.wiki_name.map(norm_name); return rev,q
    raise SystemExit('NO_WIKI_IDENTITY_TABLE')
rev,w=wiki(); pit=pitindex.get_constituents(TARGET,index='sp500').copy(); pit['ticker_norm']=pit.ticker.map(nt)
if 'name' not in pit.columns: raise SystemExit('PIT_NAME_COLUMN_MISSING')
pit['pit_name']=pit['name'].astype(str); pit['name_key']=pit.pit_name.map(norm_name); rows=[]
for ticker in FIXED:
    p=pit.loc[pit.ticker_norm==ticker]
    if len(p)!=1: rows.append({'pit_ticker':ticker,'status':'PIT_ROW_NOT_UNIQUE','pit_rows':int(len(p))}); continue
    pr=p.iloc[0]; cand=w.loc[w.name_key==pr.name_key]; rec={'pit_ticker':ticker,'pit_name':str(pr.pit_name),'name_key':str(pr.name_key),'candidate_count':int(len(cand))}
    if len(cand)==1:
        wr=cand.iloc[0]; rec.update({'status':'EXACT_UNIQUE_CONTEMPORANEOUS_NAME_MATCH','wiki_2015_ticker':clean(wr.wiki_ticker),'wiki_2015_name':clean(wr.wiki_name),'wiki_2015_cik':clean(wr.wiki_cik)})
    elif len(cand)==0: rec['status']='NO_EXACT_CONTEMPORANEOUS_NAME_MATCH'
    else: rec.update({'status':'AMBIGUOUS_CONTEMPORANEOUS_NAME_MATCH','candidates':clean(cand[['wiki_ticker','wiki_name','wiki_cik']].to_dict('records'))})
    rows.append(rec)
resolved=sum(r['status']=='EXACT_UNIQUE_CONTEMPORANEOUS_NAME_MATCH' for r in rows); all_pass=resolved==len(FIXED)
out={'schema':'research.pit_2015_alias_source_resolver_r1.v1','workload_id':'PIT_2015_ALIAS_SOURCE_RESOLVER_R1','parent':'POINT_IN_TIME_FUNDAMENTAL_SELECTION','claim':'Resolve the exact frozen 15 2015 ticker non-overlaps only when the pinned membership issuer name has one exact deterministic normalized-name match in the contemporaneous 2015 Wikipedia identity table.','source_contract':{'membership':'pitindex@2df030e5c9be7c83cf4b28c3d8597d74d274757e','target':TARGET,'historical_identity':'Wikipedia revision '+str(rev['revid']),'revision_timestamp':rev['timestamp'],'fixed_unresolved':FIXED,'normalization':'unicode ASCII, lowercase, punctuation-space, ampersand->and, trailing legal-form suffix removal only'},'counts':{'fixed':len(FIXED),'resolved_exact_unique':resolved,'unresolved':len(FIXED)-resolved},'rows':rows,'decision':'ALL_FIXED_2015_ALIASES_CAUSALLY_RESOLVED' if all_pass else 'FIXED_2015_ALIAS_RESOLUTION_INCOMPLETE','scientific_consequence':('All 15 frozen ticker non-overlaps have exact unique contemporaneous issuer identity candidates; this specific alias seam can be consumed into the all-target identity gate without current SEC identity.' if all_pass else 'Use exact matches only as durable resolved evidence. Keep unresolved names fail-closed and run a different contemporaneous issuer-identity source discriminator for the residual set; do not hand-map from current tickers or drop constituents.'),'boundaries':{'alpha_inference_this_run':False,'current_sec_identity_authority':False,'constituent_drop':False,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
out=clean(out); OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'counts':out['counts'],'rows':out['rows']},sort_keys=True,allow_nan=False))

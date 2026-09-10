from __future__ import annotations
import json,re
from io import StringIO
from pathlib import Path
import pandas as pd, requests, pitindex

DATES=['2015-12-31','2020-12-31','2025-12-31']; UA={'User-Agent':'CommandCenter-MarketResearch-P439/1.0'}
OUT=Path('research/artifacts/p439_pit_wikipedia_cik_join_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)

def nt(x):
    if x is None:return None
    s=str(x).strip().upper().replace('.','-')
    return s if s and s not in {'NAN','NONE','<NA>'} else None

def nc(x):
    if x is None or pd.isna(x):return None
    s=re.sub(r'[^0-9]','',str(x))
    return str(int(s)) if s else None

def wiki(target):
    p={'action':'query','format':'json','prop':'revisions','titles':'List of S&P 500 companies','rvprop':'ids|timestamp','rvlimit':'1','rvstart':target+'T23:59:59Z'}
    j=requests.get('https://en.wikipedia.org/w/api.php',params=p,headers=UA,timeout=30).json(); rev=next(iter(j['query']['pages'].values()))['revisions'][0]
    h=requests.get(f"https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid={rev['revid']}",headers=UA,timeout=30); h.raise_for_status()
    chosen=None
    for t in pd.read_html(StringIO(h.text)):
        low={re.sub(r'[^a-z0-9]+','',str(c).lower()):c for c in t.columns}
        sk=next((k for k in low if k in ('symbol','ticker','tickersymbol')),None); ck=next((k for k in low if 'cik' in k),None)
        if sk and ck: chosen=t[[low[sk],low[ck]]].copy(); chosen.columns=['ticker','cik']; break
    if chosen is None: raise RuntimeError('NO_WIKI_SYMBOL_CIK_TABLE')
    chosen['ticker_norm']=chosen.ticker.map(nt); chosen['cik_norm']=chosen.cik.map(nc)
    return rev,chosen.dropna(subset=['ticker_norm','cik_norm'])

rows=[]
for d in DATES:
    pit=pitindex.get_constituents(d,index='sp500').copy(); pit['ticker_norm']=pit.ticker.map(nt); pit['pit_cik_norm']=pit.cik.map(nc) if 'cik' in pit.columns else None
    rev,w=wiki(d)
    duplicate_tickers=int(w.ticker_norm.duplicated(keep=False).sum()); lookup=w.drop_duplicates('ticker_norm').set_index('ticker_norm').cik_norm.to_dict()
    pit['wiki_cik_norm']=pit.ticker_norm.map(lookup)
    matched=pit.wiki_cik_norm.notna(); native=pit.pit_cik_norm.notna() if 'pit_cik_norm' in pit else pd.Series(False,index=pit.index)
    agree=(pit.loc[native & matched,'pit_cik_norm']==pit.loc[native & matched,'wiki_cik_norm'])
    conflicts=int((~agree).sum()); comparable=int(len(agree)); n=len(pit)
    coverage=float(matched.mean()) if n else 0.0; agreement=float(agree.mean()) if comparable else 1.0
    unresolved=pit.loc[~matched,'ticker_norm'].dropna().astype(str).tolist()
    ready=coverage>=.98 and agreement>=.99 and duplicate_tickers==0 and len(unresolved)<=10
    rows.append({'target':d,'pit_members':n,'wiki_revision_id':int(rev['revid']),'wiki_revision_timestamp':rev['timestamp'],'wiki_rows':int(len(w)),'pit_member_wikipedia_cik_coverage':coverage,'native_cik_comparable_rows':comparable,'native_cik_agreement':agreement,'native_cik_conflicts':conflicts,'wiki_duplicate_ticker_rows':duplicate_tickers,'unresolved_pit_tickers':unresolved,'ready':ready})
passed=all(x['ready'] for x in rows)
out={'schema':'research.p439_pit_wikipedia_cik_join_r1.v1','workload_id':'P439_PIT_WIKIPEDIA_CIK_JOIN_R1','parent':'POINT_IN_TIME_FUNDAMENTAL_SELECTION','claim':'P435 contemporaneous Wikipedia ticker-to-CIK identity can causally fill the pinned pitindex post-2014 membership snapshots without dropping constituents, while agreeing with native PIT CIK where native identity exists.','source_contract':{'membership_source':'pitindex','membership_ref':'2df030e5c9be7c83cf4b28c3d8597d74d274757e','identity_source':'MediaWiki historical revisions','targets':DATES},'acceptance':{'pit_member_wikipedia_cik_coverage_min':.98,'native_cik_agreement_min':.99,'wiki_duplicate_ticker_rows_max':0,'unresolved_pit_tickers_max':10,'all_targets_required':True},'snapshots':rows,'decision':'POST2014_PIT_WIKIPEDIA_IDENTITY_JOIN_READY' if passed else 'POST2014_PIT_WIKIPEDIA_IDENTITY_JOIN_NOT_READY','scientific_consequence':('Unlock one post-2014 filed-at SEC feature-representation adjudicator while preserving unmatched rows fail-closed and keeping pre-2014 history blocked.' if passed else 'Keep constituent-level SEC alpha inference blocked; inspect only source/date/ticker identity disagreements, never drop unresolved constituents or backfill from current membership.'),'boundaries':{'scientific_authority':True,'alpha_inference_this_run':False,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'snapshots':[{k:x[k] for k in ('target','pit_members','wiki_rows','pit_member_wikipedia_cik_coverage','native_cik_comparable_rows','native_cik_agreement','native_cik_conflicts','wiki_duplicate_ticker_rows','ready')}|{'unresolved_count':len(x['unresolved_pit_tickers'])} for x in rows]},sort_keys=True))

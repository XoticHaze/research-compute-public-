from __future__ import annotations
import hashlib, json, re
from io import StringIO
from pathlib import Path
import pandas as pd, requests

TARGETS=['2015-12-31','2020-12-31','2025-12-31']
TITLE='List_of_S%26P_500_companies'
UA={'User-Agent':'CommandCenter-MarketResearch-P435/1.0 (research audit)'}
OUT=Path('research/artifacts/p435_wikipedia_pit_cik_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)

def revision_at(target):
    ts=target+'T23:59:59Z'
    p={'action':'query','format':'json','prop':'revisions','titles':'List of S&P 500 companies','rvprop':'ids|timestamp','rvlimit':'1','rvstart':ts}
    r=requests.get('https://en.wikipedia.org/w/api.php',params=p,headers=UA,timeout=30); r.raise_for_status()
    page=next(iter(r.json()['query']['pages'].values()))
    rev=page.get('revisions',[None])[0]
    if not rev: return None
    oldid=int(rev['revid'])
    url=f'https://en.wikipedia.org/w/index.php?title={TITLE}&oldid={oldid}'
    h=requests.get(url,headers=UA,timeout=30); h.raise_for_status()
    return rev,h.text,url

def norm(x): return re.sub(r'[^a-z0-9]+','',str(x).lower())

def audit(target):
    got=revision_at(target)
    if not got: return {'target':target,'ready':False,'failure':'NO_REVISION'}
    rev,html,url=got
    tabs=pd.read_html(StringIO(html))
    chosen=None
    for t in tabs:
        cols=[norm(c) for c in t.columns]
        if any(c in ('symbol','ticker','tickersymbol') for c in cols) and any('cik' in c for c in cols):
            chosen=t.copy(); break
    if chosen is None:
        return {'target':target,'ready':False,'failure':'NO_SYMBOL_CIK_TABLE','revision_id':int(rev['revid']),'revision_timestamp':rev['timestamp'],'html_sha256':hashlib.sha256(html.encode()).hexdigest(),'url':url}
    cmap={norm(c):c for c in chosen.columns}
    scol=next(cmap[k] for k in cmap if k in ('symbol','ticker','tickersymbol'))
    ccol=next(cmap[k] for k in cmap if 'cik' in k)
    sym=chosen[scol].astype(str).str.strip()
    cik=chosen[ccol].astype(str).str.replace(r'[^0-9]','',regex=True)
    valid_sym=(sym!='') & (sym.str.lower()!='nan')
    valid_cik=cik.str.len().between(1,10) & (cik!='')
    n=len(chosen)
    sym_cov=float(valid_sym.mean()) if n else 0.0
    cik_cov=float(valid_cik.mean()) if n else 0.0
    sym_unique=float(sym[valid_sym].nunique()/max(1,valid_sym.sum()))
    table_bytes=chosen.to_csv(index=False).encode()
    ready=(480<=n<=520 and sym_cov>=.995 and cik_cov>=.98 and sym_unique>=.995)
    return {'target':target,'ready':ready,'revision_id':int(rev['revid']),'revision_timestamp':rev['timestamp'],'url':url,'rows':n,'symbol_coverage':sym_cov,'cik_coverage':cik_cov,'symbol_uniqueness':sym_unique,'table_sha256':hashlib.sha256(table_bytes).hexdigest(),'html_sha256':hashlib.sha256(html.encode()).hexdigest(),'symbol_column':str(scol),'cik_column':str(ccol)}

rows=[]
for t in TARGETS:
    try: rows.append(audit(t))
    except Exception as e: rows.append({'target':t,'ready':False,'failure':type(e).__name__+':'+str(e)[:180]})
passed=all(x.get('ready') for x in rows)
out={'schema':'research.p435_wikipedia_pit_cik_r1.v1','workload_id':'P435_WIKIPEDIA_PIT_CIK_R1','parent':'POINT_IN_TIME_FUNDAMENTAL_SELECTION','claim':'Contemporaneous Wikipedia revisions selected by timestamp before table inspection can provide high-coverage S&P 500 ticker-to-CIK identity for fixed post-2014 snapshots, independently of pitindex/sp500-scraper stored snapshots.','source_contract':{'api':'MediaWiki revisions','page':'List of S&P 500 companies','targets':TARGETS,'selection':'latest revision at-or-before target 23:59:59Z','performance_data_used':False},'acceptance':{'rows_min':480,'rows_max':520,'symbol_coverage_min':.995,'cik_coverage_min':.98,'symbol_uniqueness_min':.995,'all_targets_required':True},'snapshots':rows,'decision':'DIRECT_WIKIPEDIA_POST2014_CIK_SOURCE_READY' if passed else 'DIRECT_WIKIPEDIA_POST2014_CIK_SOURCE_NOT_READY','scientific_consequence':('Permit one independent cross-source identity join against the pinned PIT membership chain before any fundamentals alpha inference.' if passed else 'Keep PIT fundamentals blocked on historical identifier lineage; do not drop unresolved constituents or infer alpha.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'snapshots':[{k:x.get(k) for k in ('target','revision_id','revision_timestamp','rows','cik_coverage','symbol_coverage','ready','failure')} for x in rows]},sort_keys=True))

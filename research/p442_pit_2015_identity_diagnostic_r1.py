from __future__ import annotations
import json,re
from io import StringIO
from pathlib import Path
import pandas as pd, requests, pitindex

TARGET='2015-12-31'; UA={'User-Agent':'CommandCenter-MarketResearch-P442/1.0'}
OUT=Path('research/artifacts/p442_pit_2015_identity_diagnostic_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)

def nt(x):
    if x is None:return None
    s=str(x).strip().upper().replace('.','-')
    return s if s and s not in {'NAN','NONE','<NA>'} else None

def nc(x):
    if x is None or pd.isna(x):return None
    s=re.sub(r'[^0-9]','',str(x)); return str(int(s)) if s else None

def wiki(target):
    p={'action':'query','format':'json','prop':'revisions','titles':'List of S&P 500 companies','rvprop':'ids|timestamp','rvlimit':'1','rvstart':target+'T23:59:59Z'}
    j=requests.get('https://en.wikipedia.org/w/api.php',params=p,headers=UA,timeout=30).json(); rev=next(iter(j['query']['pages'].values()))['revisions'][0]
    h=requests.get(f"https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid={rev['revid']}",headers=UA,timeout=30); h.raise_for_status()
    for t in pd.read_html(StringIO(h.text)):
        low={re.sub(r'[^a-z0-9]+','',str(c).lower()):c for c in t.columns}; sk=next((k for k in low if k in ('symbol','ticker','tickersymbol')),None); ck=next((k for k in low if 'cik' in k),None)
        if sk and ck:
            z=t.copy(); z['ticker_norm']=z[low[sk]].map(nt); z['cik_norm']=z[low[ck]].map(nc); return rev,z
    raise RuntimeError('NO_WIKI_SYMBOL_CIK_TABLE')

pit=pitindex.get_constituents(TARGET,index='sp500').copy(); pit['ticker_norm']=pit.ticker.map(nt); pit['pit_cik_norm']=pit.cik.map(nc) if 'cik' in pit.columns else None
rev,w=wiki(TARGET); lookup=w.dropna(subset=['ticker_norm','cik_norm']).drop_duplicates('ticker_norm').set_index('ticker_norm').cik_norm.to_dict(); pit['wiki_cik_norm']=pit.ticker_norm.map(lookup)
issues=[]
for _,r in pit.iterrows():
    p=r.get('pit_cik_norm'); q=r.get('wiki_cik_norm'); kind=None
    if q is None or pd.isna(q): kind='UNRESOLVED_TICKER'
    elif p is not None and not pd.isna(p) and p!=q: kind='CIK_CONFLICT'
    if kind:
        rec={'ticker':r.get('ticker_norm'),'pit_cik':None if pd.isna(p) else p,'wiki_cik':None if pd.isna(q) else q,'kind':kind}
        for c in ('name','company','security'):
            if c in pit.columns and not pd.isna(r.get(c)): rec['pit_name']=str(r.get(c)); break
        issues.append(rec)
conf=[x for x in issues if x['kind']=='CIK_CONFLICT']; unr=[x for x in issues if x['kind']=='UNRESOLVED_TICKER']
out={'schema':'research.p442_pit_2015_identity_diagnostic_r1.v1','workload_id':'P442_PIT_2015_IDENTITY_DIAGNOSTIC_R1','parent':'POINT_IN_TIME_FUNDAMENTAL_SELECTION','target':TARGET,'claim':'Localize every fixed-2015 P439 identity disagreement without dropping constituents or relaxing the all-target gate.','source_contract':{'membership_source':'pitindex','membership_ref':'2df030e5c9be7c83cf4b28c3d8597d74d274757e','identity_source':'MediaWiki historical revision','wiki_revision_id':int(rev['revid']),'wiki_revision_timestamp':rev['timestamp']},'counts':{'pit_members':int(len(pit)),'cik_conflicts':len(conf),'unresolved_tickers':len(unr),'total_issue_rows':len(issues)},'issues':issues,'decision':'2015_IDENTITY_DISAGREEMENTS_LOCALIZED','scientific_consequence':'Use the exact conflict/unresolved set for one contemporaneous issuer-identity adjudicator. Repair only deterministic ticker/date/normalization errors; otherwise retain incompatibility and keep SEC alpha blocked.','boundaries':{'alpha_inference_this_run':False,'gate_relaxation':False,'constituent_dropping':False,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'counts':out['counts'],'issues':issues},sort_keys=True))

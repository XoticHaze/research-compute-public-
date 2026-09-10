from __future__ import annotations
import json,re
from io import StringIO
from pathlib import Path
import pandas as pd,requests,pitindex
D='2015-12-31'; UA={'User-Agent':'CommandCenter-MarketResearch-P442/1.0 research@example.invalid'}
OUT=Path('research/artifacts/p442_pit_2015_cik_conflict_diagnostic_r1.json');OUT.parent.mkdir(parents=True,exist_ok=True)
def nt(x):
 s=str(x).strip().upper().replace('.','-') if x is not None else '';return s if s and s not in {'NAN','NONE','<NA>'} else None
def nc(x):
 if x is None or pd.isna(x):return None
 s=re.sub(r'[^0-9]','',str(x));return str(int(s)) if s else None
# Historical Wikipedia identity selected exactly as P435/P439.
p={'action':'query','format':'json','prop':'revisions','titles':'List of S&P 500 companies','rvprop':'ids|timestamp','rvlimit':'1','rvstart':D+'T23:59:59Z'}
j=requests.get('https://en.wikipedia.org/w/api.php',params=p,headers=UA,timeout=30).json();rev=next(iter(j['query']['pages'].values()))['revisions'][0]
h=requests.get(f"https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid={rev['revid']}",headers=UA,timeout=30);h.raise_for_status()
w=None
for t in pd.read_html(StringIO(h.text)):
 low={re.sub(r'[^a-z0-9]+','',str(c).lower()):c for c in t.columns};sk=next((k for k in low if k in ('symbol','ticker','tickersymbol')),None);ck=next((k for k in low if 'cik' in k),None);nk=next((k for k in low if k in ('security','company','name')),None)
 if sk and ck:
  cols=[low[sk],low[ck]]+([low[nk]] if nk else []);w=t[cols].copy();w.columns=['ticker','cik']+(['wiki_name'] if nk else []);break
if w is None:raise RuntimeError('NO_WIKI_TABLE')
w['ticker_norm']=w.ticker.map(nt);w['wiki_cik']=w.cik.map(nc)
# Pinned PIT roster. Its published API contract states CIK is populated for tickers still members today, while old membership comes from historical seed data.
pit=pitindex.get_constituents(D,index='sp500').copy();pit['ticker_norm']=pit.ticker.map(nt);pit['pit_cik']=pit.cik.map(nc)
# Official SEC current ticker map is used only to test the documented current-roster-backfill mechanism; it is not used as historical identity.
s=requests.get('https://www.sec.gov/files/company_tickers.json',headers=UA,timeout=30);s.raise_for_status();sj=s.json(); sec={}
for v in sj.values():
 tk=nt(v.get('ticker')); ci=nc(v.get('cik_str'))
 if tk:sec[tk]={'cik':ci,'title':v.get('title')}
cols=['ticker_norm','wiki_cik']+(['wiki_name'] if 'wiki_name' in w.columns else [])
z=pit.merge(w[cols],on='ticker_norm',how='left')
z['sec_current_cik']=z.ticker_norm.map(lambda x:(sec.get(x) or {}).get('cik'))
z['sec_current_title']=z.ticker_norm.map(lambda x:(sec.get(x) or {}).get('title'))
conf=z[z.pit_cik.notna() & z.wiki_cik.notna() & (z.pit_cik!=z.wiki_cik)].copy();unres=z[z.wiki_cik.isna()].copy()
conf['pit_equals_sec_current']=conf.pit_cik==conf.sec_current_cik;conf['wiki_equals_sec_current']=conf.wiki_cik==conf.sec_current_cik
backfill=conf.pit_equals_sec_current & ~conf.wiki_equals_sec_current
rate=float(backfill.mean()) if len(conf) else 0.0
def rec(r):
 return {'ticker':r.ticker_norm,'pit_name':None if pd.isna(r.get('name')) else str(r.get('name')),'pit_cik':r.pit_cik,'wiki_name':None if pd.isna(r.get('wiki_name')) else str(r.get('wiki_name')),'wiki_cik':r.wiki_cik,'sec_current_cik':r.sec_current_cik,'sec_current_title':None if pd.isna(r.sec_current_title) else str(r.sec_current_title),'pit_equals_sec_current':bool(r.pit_equals_sec_current),'wiki_equals_sec_current':bool(r.wiki_equals_sec_current)}
conflicts=[rec(r) for _,r in conf.iterrows()]
unresolved=[{'ticker':r.ticker_norm,'pit_name':None if pd.isna(r.get('name')) else str(r.get('name')),'pit_cik':r.pit_cik,'sec_current_cik':r.sec_current_cik,'sec_current_title':None if pd.isna(r.sec_current_title) else str(r.sec_current_title)} for _,r in unres.iterrows()]
decision='P439_NATIVE_CIK_AGREEMENT_CONFOUNDED_BY_CURRENT_ROSTER_BACKFILL' if len(conf)>=5 and rate>=.80 else 'P439_NATIVE_CIK_CONFLICTS_NOT_EXPLAINED_BY_CURRENT_ROSTER_BACKFILL'
out={'schema':'research.p442_pit_2015_cik_conflict_diagnostic_r1.v1','workload_id':'P442_PIT_2015_CIK_CONFLICT_DIAGNOSTIC_R1','parent':'POINT_IN_TIME_FUNDAMENTAL_SELECTION','claim':'P439 2015 native-CIK conflicts may be caused by pitindex documented current-roster CIK enrichment being attached to historical ticker membership, especially under ticker reuse; official SEC current ticker-CIK is used only to diagnose that mechanism, never as historical backfill.','pitindex_ref':'2df030e5c9be7c83cf4b28c3d8597d74d274757e','wikipedia_revision':{'id':int(rev['revid']),'timestamp':rev['timestamp']},'conflict_count':int(len(conf)),'unresolved_wikipedia_identity_count':int(len(unres)),'conflicts_matching_sec_current_pit_cik_only':int(backfill.sum()),'current_backfill_signature_fraction':rate,'conflicts':conflicts,'unresolved':unresolved,'decision_rule':'Classify native-CIK agreement as confounded only if >=5 conflicts exist and >=80% have pitindex CIK equal to official SEC current CIK for that ticker while historical Wikipedia CIK differs. Do not use SEC current mapping to fill historical identity.','decision':decision,'scientific_consequence':('Do not use pitindex native-CIK agreement as a historical-identity veto for this 2015 snapshot; retain P439 coverage failure and resolve the enumerated unmatched PIT members using genuinely historical identity evidence.' if decision.endswith('BACKFILL') else 'Retain P439 native-CIK disagreement as unresolved and keep the alpha chain blocked.'),'boundaries':{'historical_identity_backfill_from_current_sec':False,'alpha_inference':False,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False));print(json.dumps({'decision':decision,'conflict_count':len(conf),'unresolved_count':len(unres),'backfill_signature':int(backfill.sum()),'backfill_fraction':round(rate,4),'conflict_tickers':[x['ticker'] for x in conflicts],'unresolved_tickers':[x['ticker'] for x in unresolved]},sort_keys=True))
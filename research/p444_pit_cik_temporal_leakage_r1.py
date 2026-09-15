from __future__ import annotations
import json,re
from io import StringIO
from pathlib import Path
import pandas as pd,requests,pitindex
TARGET='2015-12-31'; UA={'User-Agent':'CommandCenter-MarketResearch-P444/1.0 research@example.invalid'}; OUT=Path('research/artifacts/p444_pit_cik_temporal_leakage_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
def nt(x):
 s=str(x).strip().upper().replace('.','-') if x is not None else ''; return s or None
def nc(x):
 if x is None or pd.isna(x):return None
 s=re.sub(r'[^0-9]','',str(x)); return str(int(s)) if s else None
p={'action':'query','format':'json','prop':'revisions','titles':'List of S&P 500 companies','rvprop':'ids|timestamp','rvlimit':'1','rvstart':TARGET+'T23:59:59Z'}
j=requests.get('https://en.wikipedia.org/w/api.php',params=p,headers=UA,timeout=30).json(); rev=next(iter(j['query']['pages'].values()))['revisions'][0]
h=requests.get(f"https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid={rev['revid']}",headers=UA,timeout=30); h.raise_for_status()
w=None
for t in pd.read_html(StringIO(h.text)):
 low={re.sub(r'[^a-z0-9]+','',str(c).lower()):c for c in t.columns}; sk=next((k for k in low if k in ('symbol','ticker','tickersymbol')),None); ck=next((k for k in low if 'cik' in k),None)
 if sk and ck:
  w=t.copy(); w['ticker_norm']=w[low[sk]].map(nt); w['wiki_cik']=w[low[ck]].map(nc); break
if w is None: raise SystemExit('NO_WIKI_TABLE')
sec=requests.get('https://www.sec.gov/files/company_tickers.json',headers=UA,timeout=30); sec.raise_for_status(); sj=sec.json(); sm={nt(v['ticker']):str(int(v['cik_str'])) for v in sj.values()}
pit=pitindex.get_constituents(TARGET,index='sp500').copy(); pit['ticker_norm']=pit.ticker.map(nt); pit['pit_cik']=pit.cik.map(nc); wm=w.dropna(subset=['ticker_norm','wiki_cik']).drop_duplicates('ticker_norm').set_index('ticker_norm').wiki_cik.to_dict(); pit['wiki_cik']=pit.ticker_norm.map(wm); pit['sec_current_cik']=pit.ticker_norm.map(sm)
conf=pit[(pit.wiki_cik.notna())&(pit.pit_cik.notna())&(pit.wiki_cik!=pit.pit_cik)].copy(); rows=[]
for _,r in conf.iterrows(): rows.append({'ticker':r.ticker_norm,'pit_cik':r.pit_cik,'wiki_2015_cik':r.wiki_cik,'sec_current_cik':None if pd.isna(r.sec_current_cik) else r.sec_current_cik,'pit_matches_sec_current':bool(not pd.isna(r.sec_current_cik) and r.pit_cik==r.sec_current_cik),'pit_name':str(r['name']) if 'name' in pit.columns and not pd.isna(r.get('name')) else None})
expl=sum(x['pit_matches_sec_current'] for x in rows); ratio=expl/len(rows) if rows else 0; supported=len(rows)>=10 and ratio>=.80
out={'schema':'research.p444_pit_cik_temporal_leakage_r1.v1','workload_id':'P444_PIT_CIK_TEMPORAL_LEAKAGE_R1','parent':'POINT_IN_TIME_FUNDAMENTAL_SELECTION','claim':'P439 2015 native-CIK conflicts are primarily temporal identity leakage: pitindex historical membership rows carry current ticker issuer CIKs rather than contemporaneous 2015 issuer CIKs.','source_contract':{'membership':'pitindex@2df030e5c9be7c83cf4b28c3d8597d74d274757e','historical_identity':'Wikipedia historical revision '+str(rev['revid']),'current_identity':'SEC company_tickers.json fetched in-run','target':TARGET},'counts':{'cik_conflicts':len(rows),'pit_matches_sec_current':expl,'pit_matches_sec_current_ratio':ratio},'conflicts':rows,'acceptance':{'min_conflicts':10,'pit_matches_sec_current_ratio_min':.80},'decision':'PITINDEX_NATIVE_CIK_TEMPORAL_LEAKAGE_SUPPORTED' if supported else 'PITINDEX_NATIVE_CIK_TEMPORAL_LEAKAGE_NOT_SUPPORTED','scientific_consequence':('Do not use pitindex native CIK as historical issuer identity for 2015. Treat membership timing and issuer-identity timing as separate authorities; contemporaneous identity must come from a dated source before SEC filed-at features can be joined.' if supported else 'Temporal leakage does not explain enough conflicts; keep the historical SEC feature chain blocked and investigate another identity authority without dropping constituents.'),'boundaries':{'alpha_inference_this_run':False,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'counts':out['counts'],'conflicts':rows},sort_keys=True))

from __future__ import annotations
import json,re
from io import StringIO
from pathlib import Path
import pandas as pd,requests,pitindex
DATES=['2015-12-31','2020-12-31','2025-12-31']; UA={'User-Agent':'CommandCenter-MarketResearch-P457/1.0'}
OUT=Path('research/artifacts/p457_pit_identity_gate_r2.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
# Fixed 2015 alias map, fully evidence-backed by prior exact-name, dated historical-CIK, and dated corporate-action children.
ALIASES_2015={
 'CBRE':('CBG','1138118'),'WELL':('HCN','766704'),'ANDV':('TSO','50104'),'APTV':('DLPH','1521332'),'ARNC':('AA','4281'),
 'BKNG':('PCLN','1075531'),'JEF':('LUK','96223'),'SPGI':('MHFI','64040'),'TPR':('COH','1116132'),'UAA':('UA','1336917'),
 'AABA':('YHOO','1011006'),'BHGE':('BHI','808362'),'KDP':('DPS','1418135'),'WYND':('WYN','1361658'),'VMRK':('EQR','906107')}
def nt(x):
 if x is None:return None
 s=str(x).strip().upper().replace('.','-'); return s if s and s not in {'NAN','NONE','<NA>'} else None
def nc(x):
 if x is None or pd.isna(x):return None
 s=re.sub(r'[^0-9]','',str(x)); return str(int(s)) if s else None
def wiki(target):
 p={'action':'query','format':'json','prop':'revisions','titles':'List of S&P 500 companies','rvprop':'ids|timestamp','rvlimit':'1','rvstart':target+'T23:59:59Z'}
 j=requests.get('https://en.wikipedia.org/w/api.php',params=p,headers=UA,timeout=30).json(); rev=next(iter(j['query']['pages'].values()))['revisions'][0]
 h=requests.get(f"https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid={rev['revid']}",headers=UA,timeout=30); h.raise_for_status(); chosen=None
 for t in pd.read_html(StringIO(h.text)):
  low={re.sub(r'[^a-z0-9]+','',str(c).lower()):c for c in t.columns}; sk=next((k for k in low if k in ('symbol','ticker','tickersymbol')),None); ck=next((k for k in low if 'cik' in k),None)
  if sk and ck: chosen=t[[low[sk],low[ck]]].copy(); chosen.columns=['ticker','cik']; break
 if chosen is None: raise RuntimeError('NO_WIKI_SYMBOL_CIK_TABLE')
 chosen['ticker_norm']=chosen.ticker.map(nt); chosen['cik_norm']=chosen.cik.map(nc); return rev,chosen.dropna(subset=['ticker_norm','cik_norm'])
rows=[]
for d in DATES:
 pit=pitindex.get_constituents(d,index='sp500').copy(); pit['ticker_norm']=pit.ticker.map(nt); pit['pit_cik_norm']=pit.cik.map(nc) if 'cik' in pit.columns else None
 rev,w=wiki(d); duplicate_tickers=int(w.ticker_norm.duplicated(keep=False).sum()); lookup=w.drop_duplicates('ticker_norm').set_index('ticker_norm').cik_norm.to_dict()
 assigned=[]; methods=[]
 for t in pit.ticker_norm:
  if d=='2015-12-31' and t in ALIASES_2015:
   pred,cik=ALIASES_2015[t]; assigned.append(cik); methods.append('EVIDENCE_BACKED_2015_ALIAS:'+pred)
  else: assigned.append(lookup.get(t)); methods.append('CONTEMPORANEOUS_WIKIPEDIA')
 pit['assigned_cik']=assigned; pit['identity_method']=methods
 matched=pit.assigned_cik.notna(); alias_mask=pit.identity_method.str.startswith('EVIDENCE_BACKED_2015_ALIAS')
 native=pit.pit_cik_norm.notna() if 'pit_cik_norm' in pit else pd.Series(False,index=pit.index)
 # P442/P444 proved native PIT CIK is temporally leaked for alias rows; agreement gate applies only where native identity remains an admissible comparator.
 admissible=native & matched & ~alias_mask
 agree=(pit.loc[admissible,'pit_cik_norm']==pit.loc[admissible,'assigned_cik']); conflicts=int((~agree).sum()); comparable=int(len(agree)); n=len(pit)
 coverage=float(matched.mean()) if n else 0.0; agreement=float(agree.mean()) if comparable else 1.0; unresolved=pit.loc[~matched,'ticker_norm'].dropna().astype(str).tolist()
 alias_rows=pit.loc[alias_mask,['ticker_norm','assigned_cik','identity_method']].to_dict('records')
 ready=coverage>=.98 and agreement>=.99 and duplicate_tickers==0 and len(unresolved)<=10
 rows.append({'target':d,'pit_members':n,'wiki_revision_id':int(rev['revid']),'wiki_revision_timestamp':rev['timestamp'],'pit_member_identity_coverage':coverage,'native_cik_admissible_comparable_rows':comparable,'native_cik_admissible_agreement':agreement,'native_cik_admissible_conflicts':conflicts,'wiki_duplicate_ticker_rows':duplicate_tickers,'evidence_backed_alias_rows':alias_rows,'unresolved_pit_tickers':unresolved,'ready':ready})
passed=all(x['ready'] for x in rows)
out={'schema':'research.p457_pit_identity_gate_r2.v1','workload_id':'P457_PIT_IDENTITY_GATE_R2','parent':'POINT_IN_TIME_FUNDAMENTAL_SELECTION','claim':'Rerun the frozen post-2014 all-target PIT identity gate after the complete fixed 2015 alias seam was independently resolved. Preserve contemporaneous Wikipedia identity for ordinary rows and use only the fifteen evidence-backed historical predecessor CIKs on the 2015 alias rows whose native pitindex CIK was proven temporally leaked.','source_contract':{'membership_source':'pitindex','membership_ref':'2df030e5c9be7c83cf4b28c3d8597d74d274757e','ordinary_identity_source':'MediaWiki historical revisions','fixed_2015_alias_map':ALIASES_2015,'current_sec_ticker_mapping_used':False,'constituent_drop':False},'acceptance':{'pit_member_identity_coverage_min':.98,'native_cik_admissible_agreement_min':.99,'wiki_duplicate_ticker_rows_max':0,'unresolved_pit_tickers_max':10,'all_targets_required':True},'snapshots':rows,'decision':'POST2014_PIT_IDENTITY_GATE_READY_FOR_FILED_AT_SEC' if passed else 'POST2014_PIT_IDENTITY_GATE_NOT_READY','scientific_consequence':('Unlock one post-2014 filed-at SEC feature/alpha discriminator using the repaired causal identity representation; preserve pre-2014 history as separately unresolved.' if passed else 'Keep SEC alpha inference blocked and inspect only remaining exact identity/source failures; no constituent dropping or current-map rescue.'),'boundaries':{'alpha_inference_this_run':False,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'snapshots':[{k:x[k] for k in ('target','pit_members','pit_member_identity_coverage','native_cik_admissible_comparable_rows','native_cik_admissible_agreement','native_cik_admissible_conflicts','wiki_duplicate_ticker_rows','ready')}|{'alias_rows':len(x['evidence_backed_alias_rows']),'unresolved_count':len(x['unresolved_pit_tickers'])} for x in rows]},sort_keys=True))

from __future__ import annotations
import hashlib,json,re,time
from pathlib import Path
import requests

OUT=Path('research/artifacts/p477_pit_alias_corporate_lineage_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
UA={'User-Agent':'xotichaze-market-research/1.0 research contact github.com/XoticHaze'}
CASES=[
 {'alias':'AABA','historical_ticker':'YHOO','historical_cik':'1011006','lineage':'SAME_REGISTRANT_RENAME_AFTER_2015','urls':['https://www.sec.gov/Archives/edgar/data/1011006/000119312517206955/d389206d8k.htm'],'markers':['Yahoo changed its name to','Altaba Inc','ticker symbol','AABA','YHOO']},
 {'alias':'BHGE','historical_ticker':'BHI','historical_cik':'808362','lineage':'NEW_HOLDCO_SUCCESSOR_USE_2015_PREDECESSOR_CIK','urls':['https://www.sec.gov/Archives/edgar/data/808362/000080836216000053/fiscalyear2015form10-k.htm','https://www.sec.gov/Archives/edgar/data/1701605/000119312517220954/d421375d8k.htm'],'markers':['Baker Hughes Incorporated','2015','combination','Baker Hughes','Mergers']},
 {'alias':'KDP','historical_ticker':'DPS','historical_cik':'1418135','lineage':'SAME_REGISTRANT_RENAME_AFTER_2015','urls':['https://www.sec.gov/Archives/edgar/data/1418135/000141813518000025/dps-10qx063018.htm'],'markers':['Dr Pepper Snapple Group','DPS','July 9, 2018','renamed','KDP']},
 {'alias':'VMRK','historical_ticker':'EQR','historical_cik':'906107','lineage':'SAME_REGISTRANT_RENAME_AFTER_2015_AVB_MERGED_IN','urls':['https://www.sec.gov/Archives/edgar/data/906107/000090610716000029/eqr-20151231x10k.htm','https://www.sec.gov/Archives/edgar/data/906107/000114036126033377/ef20080318_8k.htm'],'markers':['EQUITY RESIDENTIAL','2015','changed its name from Equity Residential to Vivmark Residential','VMRK']},
 {'alias':'WYND','historical_ticker':'WYN','historical_cik':'1361658','lineage':'SAME_REGISTRANT_RENAME_AFTER_SPINOFF','urls':['https://www.sec.gov/Archives/edgar/data/1361658/000136165816000028/wyn-20151231x10k.htm','https://www.sec.gov/Archives/edgar/data/1361658/000110465918037818/a18-14563_28k.htm'],'markers':['Wyndham Worldwide','WYN','Wyndham Destinations','WYND']},
]

def norm(s): return re.sub(r'\s+',' ',s.replace('&nbsp;',' '))
results=[]
for case in CASES:
    texts=[]; source=[]
    for url in case['urls']:
        rr=requests.get(url,headers=UA,timeout=30); rr.raise_for_status(); text=norm(rr.text); texts.append(text)
        source.append({'url':url,'sha256':hashlib.sha256(rr.content).hexdigest(),'bytes':len(rr.content)})
        time.sleep(.15)
    joined=' '.join(texts).lower()
    checks={m:(m.lower() in joined) for m in case['markers']}
    results.append({**{k:v for k,v in case.items() if k not in ('urls','markers')},'marker_checks':checks,'all_markers_present':all(checks.values()),'sources':source})
passed=all(r['all_markers_present'] for r in results)
out={'schema':'research.p477_pit_alias_corporate_lineage_r1.v1','workload_id':'P477_PIT_ALIAS_CORPORATE_LINEAGE_R1','parent':'POINT_IN_TIME_FUNDAMENTAL_SELECTION','claim':'The five residual current-symbol aliases can be mapped fail-closed to their actual 2015 issuer identities using dated SEC corporate-action/filing lineage without using current ticker-CIK lookup authority.','contract':{'residual_aliases':[c['alias'] for c in CASES],'rule':'Accept only if dated primary filing text contains the predeclared issuer/corporate-action markers. For new-holdco BHGE, use legacy BHI CIK for 2015 rather than backcasting later BHGE CIK. No constituent dropping or current-ticker identity lookup.'},'results':results,'decision':'PIT_2015_ALIAS_LINEAGE_COMPLETE' if passed else 'PIT_2015_ALIAS_LINEAGE_STILL_INCOMPLETE','resolved_mappings':[{k:r[k] for k in ('alias','historical_ticker','historical_cik','lineage')} for r in results if r['all_markers_present']],'unresolved':[r['alias'] for r in results if not r['all_markers_present']],'scientific_consequence':'Close the fixed five-alias historical identity seam and reopen the frozen PIT filing-coverage/economic pipeline with these mappings.' if passed else 'Keep only failed aliases fail-closed and continue exact corporate-action identity work; do not drop constituents or relax the PIT gate.','boundaries':{'constituent_drop':False,'current_sec_identity_authority':False,'alpha_inference':False,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'resolved':out['resolved_mappings'],'unresolved':out['unresolved']},sort_keys=True))

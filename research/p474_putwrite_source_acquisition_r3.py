from __future__ import annotations
import hashlib,json,urllib.request
from pathlib import Path
URL='https://cdn.cboe.com/api/global/us_indices/daily_prices/PUTW_History.csv'
OUT=Path('research/artifacts/p474_putwrite_source_acquisition_r3.json');OUT.parent.mkdir(parents=True,exist_ok=True)
req=urllib.request.Request(URL,headers={'User-Agent':'CommandCenter MarketResearch source-acquisition/1.0'})
try:
    data=urllib.request.urlopen(req,timeout=30).read()
    text=data.decode('utf-8-sig','replace')
    lines=[x for x in text.splitlines() if x.strip()]
    header=lines[0] if lines else ''
    decision='PUTW_OFFICIAL_HISTORY_ACQUIRED' if len(lines)>24 and ('DATE' in header.upper()) else 'PUTW_OFFICIAL_HISTORY_INVALID'
    out={'schema':'research.p474_putwrite_source_acquisition_r3.v1','workload_id':'P474_PUTWRITE_SOURCE_ACQUISITION_R3','source':'CBOE_OFFICIAL_STATIC','url':URL,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'rows_including_header':len(lines),'header':header,'decision':decision,'next':'If acquired, parse/cache official PUTW history and rerun the already-frozen P474 beta-matched SPY+BIL economic discriminator without changing its windows, costs, controls, or gates.'}
except Exception as e:
    out={'schema':'research.p474_putwrite_source_acquisition_r3.v1','workload_id':'P474_PUTWRITE_SOURCE_ACQUISITION_R3','source':'CBOE_OFFICIAL_STATIC','url':URL,'decision':'PUTW_OFFICIAL_STATIC_TRANSPORT_FAILURE','error_type':type(e).__name__,'error':str(e),'next':'Continue source ladder to official Cboe index-data/download alternatives before any mirror.'}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True));print(json.dumps(out,sort_keys=True))
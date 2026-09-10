from __future__ import annotations
import json
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import numpy as np, pandas as pd

SIGNAL='2026-09-04'; HOLD=20; DELAY=1; COST_BPS=25.0; BENCH='SMH'
# Exact immutable external rows from research-foundry ledger blob 4d92ef44157590423cd13bbadc22594178b92dc0 at branch commit 0a4787db6d78ac843c8b60395b1ff83fc3c4f49d.
PRED={'AMD':766.5040500112505,'MRVL':726.4544999093108,'MU':697.0696897379795,'MCHP':334.07577126875344,'AVGO':326.5879545604015,'NVDA':-178.86072857414976}
RANK={'AMD':1,'MRVL':2,'MU':3,'MCHP':9,'AVGO':10,'NVDA':13}
OUT=Path('research/artifacts/p438_semiconductor_forward_mtd_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)

def price(v): return float(str(v or '').strip().replace('$','').replace(',',''))
def nasdaq(sym):
    asset='etf' if sym==BENCH else 'stocks'; market='etf' if sym==BENCH else 'stocks'
    q=urlencode({'assetclass':asset,'fromdate':'2026-08-20','todate':(date.today()+timedelta(days=2)).isoformat(),'limit':100})
    req=Request(f'https://api.nasdaq.com/api/quote/{sym}/historical?{q}',headers={'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/147 Safari/537.36','Accept':'application/json, text/plain, */*','Referer':f'https://www.nasdaq.com/market-activity/{market}/{sym.lower()}/historical','Origin':'https://www.nasdaq.com'})
    with urlopen(req,timeout=45) as resp: payload=json.loads(resp.read().decode())
    rows=(((payload.get('data') or {}).get('tradesTable') or {}).get('rows') or [])
    f=pd.DataFrame([{'timestamp':pd.to_datetime(r['date'],utc=True),'price':price(r['close'])} for r in rows]).sort_values('timestamp').drop_duplicates('timestamp')
    if len(f)<5 or (f.price<=0).any(): raise RuntimeError(f'Nasdaq integrity failure {sym}: rows={len(f)}')
    return f.set_index('timestamp').price.astype(float)

symbols=list(PRED)+[BENCH]
px={s:nasdaq(s) for s in symbols}
common=sorted(set.intersection(*[set(v.index) for v in px.values()]))
common=pd.DatetimeIndex(common)
signal=pd.Timestamp(SIGNAL,tz='UTC')
pos=np.flatnonzero(common==signal)
if len(pos)!=1: raise RuntimeError(f'signal bar not on exact common calendar: {SIGNAL}; last={common[-1]}')
si=int(pos[0]); ei=si+DELAY; final_i=si+DELAY+HOLD
if ei>=len(common): raise RuntimeError('entry session not available yet')
entry_ts=common[ei]; latest_ts=common[-1]
rows=[]
for s in PRED:
    entry=float(px[s].loc[entry_ts]); latest=float(px[s].loc[latest_ts]); be=float(px[BENCH].loc[entry_ts]); bl=float(px[BENCH].loc[latest_ts])
    path=px[s].reindex(common[ei:]).astype(float); path_bps=(path/entry-1)*10000
    net=(latest/entry-1)*10000-COST_BPS; smh=(bl/be-1)*10000
    rows.append({'symbol':s,'frozen_descriptive_rank':RANK[s],'predicted_fixed20_net_value_bps':PRED[s],'entry_date':entry_ts.date().isoformat(),'latest_common_date':latest_ts.date().isoformat(),'elapsed_close_to_close_sessions':int(len(common[ei:])-1),'remaining_sessions_to_fixed20':int(max(0,final_i-(len(common)-1))),'mark_to_date_net25_bps':float(net),'mark_to_date_smh_gross_bps':float(smh),'mark_to_date_excess_vs_smh_bps':float(net-smh),'path_mfe_bps':float(path_bps.max()),'path_mae_bps':float(path_bps.min()),'final_target_resolved':bool(len(common)-1>=final_i)})
final_resolved=all(r['final_target_resolved'] for r in rows)
out={'schema':'research.p438_semiconductor_forward_mtd_r1.v1','workload_id':'P438_SEMICONDUCTOR_FORWARD_MTD_R1','parent':'SEMICONDUCTOR_PREDICTED_VALUE_SCARCITY_FORWARD','frozen_prediction_identity':{'research_foundry_branch_commit':'0a4787db6d78ac843c8b60395b1ff83fc3c4f49d','prediction_blob_sha':'4d92ef44157590423cd13bbadc22594178b92dc0','generation_bar_date':SIGNAL,'delay_sessions':DELAY,'hold_sessions':HOLD,'cost_bps':COST_BPS},'source':'Nasdaq historical daily Close API, same source family as frozen observer','source_last_dates':{s:px[s].index.max().date().isoformat() for s in symbols},'rows':rows,'classification':'FIXED20_TARGET_RESOLVED' if final_resolved else 'FIXED20_TARGET_UNRESOLVED__DESCRIPTIVE_PATH_ONLY','scientific_rule':'No hit-rate, calibration, rank-IC, model pass/fail, refit, promotion, or rejection may be inferred from this mark-to-date artifact before the immutable delayed 20-session target resolves.','boundaries':{'research_only':True,'final_scorecard_authority':False,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'classification':out['classification'],'latest_common_date':latest_ts.date().isoformat(),'rows':[{k:r[k] for k in ('symbol','predicted_fixed20_net_value_bps','mark_to_date_net25_bps','mark_to_date_excess_vs_smh_bps','path_mfe_bps','path_mae_bps','remaining_sessions_to_fixed20')} for r in rows]},sort_keys=True))

from __future__ import annotations

"""Source-only causal readiness check for Homebuilder rate-context features.

No Homebuilder target returns are loaded. The goal is to prove a market-observable,
revision-free rate-information plane that can later be consumed by the private
Homebuilder model lane without introducing revised macro data or same-day leakage.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

START='2014-01-01'; END='2026-09-03'
SYMBOLS=('ITB','XHB','TLT','IEF','SHY')
OUT=Path('homebuilder_rate_context_preflight_20260905.json')


def epoch(s): return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp())
def load(sym):
    q=urlencode({'period1':epoch(START),'period2':epoch(END),'interval':'1d','events':'history','includeAdjustedClose':'true'})
    req=Request(f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?{q}',headers={'User-Agent':'Mozilla/5.0 research-compute/1.0'})
    with urlopen(req,timeout=30) as r: p=json.loads(r.read().decode())
    x=(p.get('chart',{}).get('result') or [None])[0]
    if not x: raise RuntimeError(f'{sym}: no chart result')
    ind=x.get('indicators',{}); adj=(ind.get('adjclose') or [{}])[0].get('adjclose'); close=adj or (ind.get('quote') or [{}])[0].get('close')
    return pd.DataFrame({'timestamp':pd.to_datetime(x.get('timestamp') or [],unit='s',utc=True),'price':pd.to_numeric(pd.Series(close),errors='coerce')}).dropna().sort_values('timestamp').drop_duplicates('timestamp',keep='last').reset_index(drop=True)


def main():
    raw={s:load(s) for s in SYMBOLS}
    cutoff=min(d.iloc[-1].timestamp for d in raw.values())
    sets=[set(d.loc[d.timestamp<=cutoff,'timestamp']) for d in raw.values()]
    cal=pd.DatetimeIndex(sorted(set.intersection(*sets)))
    if len(cal)<3000: raise RuntimeError(f'insufficient common market-observable calendar={len(cal)}')
    px={s:raw[s].set_index('timestamp').price.reindex(cal) for s in SYMBOLS}
    if any(v.isna().any() for v in px.values()): raise RuntimeError('missing common-calendar price')

    f=pd.DataFrame(index=cal)
    # Every model-consumable field is shifted one session: only information known by prior close.
    for s in SYMBOLS:
        r20=px[s].pct_change(20).shift(1)
        r60=px[s].pct_change(60).shift(1)
        f[f'{s.lower()}_ret20_lag1']=r20
        f[f'{s.lower()}_ret60_lag1']=r60
    f['duration_pressure_20_lag1']=(-px['IEF'].pct_change(20)).shift(1)
    f['long_duration_pressure_20_lag1']=(-px['TLT'].pct_change(20)).shift(1)
    f['curve_proxy_ief_minus_shy_20_lag1']=(px['IEF'].pct_change(20)-px['SHY'].pct_change(20)).shift(1)
    f['curve_proxy_tlt_minus_ief_20_lag1']=(px['TLT'].pct_change(20)-px['IEF'].pct_change(20)).shift(1)
    f['builder_peer_spread_itb_minus_xhb_20_lag1']=(px['ITB'].pct_change(20)-px['XHB'].pct_change(20)).shift(1)
    usable=f.replace([np.inf,-np.inf],np.nan).dropna()
    if len(usable)<2900: raise RuntimeError(f'insufficient usable causal feature rows={len(usable)}')

    out={
        'schema':'public_compute.homebuilder_rate_context_preflight.v1','generated_at':datetime.now(timezone.utc).isoformat(),
        'source':'Yahoo chart adjusted-close market prices only','source_symbols':list(SYMBOLS),'common_cutoff':cutoff.isoformat(),
        'common_calendar_rows':len(cal),'usable_feature_rows':len(usable),'first_usable':usable.index[0].isoformat(),'last_usable':usable.index[-1].isoformat(),
        'candidate_information_families':{
            'industry_state':['itb_ret20_lag1','itb_ret60_lag1','xhb_ret20_lag1','xhb_ret60_lag1','builder_peer_spread_itb_minus_xhb_20_lag1'],
            'rate_duration_state':['tlt_ret20_lag1','tlt_ret60_lag1','ief_ret20_lag1','ief_ret60_lag1','shy_ret20_lag1','shy_ret60_lag1','duration_pressure_20_lag1','long_duration_pressure_20_lag1'],
            'curve_proxies':['curve_proxy_ief_minus_shy_20_lag1','curve_proxy_tlt_minus_ief_20_lag1'],
        },
        'causality':{'all_model_features_shifted_sessions':1,'same_day_close_consumption':False,'revised_macro_series_loaded':False,'fred_or_alfred_loaded':False},
        'next_consumer_boundary':'private Homebuilder model may test these frozen information families against the existing admission control; no target/model outcome is evaluated by this preflight',
        'research_only':True,'promotion_authority':False,'runtime_mutation':False,'live_trading_change':False
    }
    OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
    print('HOMEBUILDER_RATE_CONTEXT_PREFLIGHT='+json.dumps(out,sort_keys=True))

if __name__=='__main__': main()

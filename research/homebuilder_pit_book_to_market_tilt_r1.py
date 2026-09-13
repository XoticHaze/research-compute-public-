#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("valuation_r3", HERE / "homebuilder_pit_valuation_source_probe_r3.py")
r3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r3)
r2 = r3.r2

DEV=("DHI","LEN","PHM","NVR","TOL","MTH","KBH","LGIH")
EXTERNAL="DFH"; ALL=(*DEV,EXTERNAL,"ITB")
REBALANCE=63; DELAY=1; HOLD=63; COMMON_COST_BPS=25.0; MARGINAL_HURDLE_BPS=50.0; TILT=0.25; TOP_N=2; FOLDS=5
MIN_DECISIONS=27; MIN_DEV_PASSES=5; MIN_DEV_EVENTS=3; MIN_EXT_EVENTS=2
OUT=Path("research/results/homebuilder_pit_book_to_market_tilt_r1.json")
SOURCE_REQUIRED="HOMEBUILDER_PIT_VALUATION_SOURCE_ADMITTED_R3"

def adj_prices(symbol:str)->pd.Series:
    q=urlencode({"period1":r2.epoch("2019-01-01"),"period2":r2.epoch("2026-09-14"),"interval":"1d","events":"history","includeAdjustedClose":"true"})
    p=r2.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{q}","Mozilla/5.0 research-compute/1.0")
    x=(p.get("chart",{}).get("result") or [None])[0]
    if not x: raise RuntimeError(f"{symbol}: no chart")
    tz=x.get("meta",{}).get("exchangeTimezoneName") or "America/New_York"
    idx=pd.to_datetime(x.get("timestamp") or [],unit="s",utc=True).tz_convert(tz).normalize().tz_localize(None)
    vals=((x.get("indicators",{}).get("adjclose") or [{}])[0].get("adjclose") or [])
    if not vals: vals=((x.get("indicators",{}).get("quote") or [{}])[0].get("close") or [])
    s=pd.Series(pd.to_numeric(pd.Series(vals),errors="coerce").to_numpy(),index=idx,name=symbol).dropna()
    return s[~s.index.duplicated(keep="last")].sort_index()

def btm_state(cf, raw:pd.Series, asof:pd.Timestamp):
    sh=r2.share_fact(cf,asof); eq=r3.equity_fact(cf,asof); px=r2.px_at(raw,asof)
    if not sh or not eq or not px:return None
    d,p=px
    if d.date()!=asof.date(): return None
    m=sh['value']*p; b=eq['value']/m if m>0 else np.nan
    if not(np.isfinite(m) and np.isfinite(b) and 1e8<=m<=2e11 and .01<=b<=10):return None
    return {'book_to_market':float(b),'market_cap':float(m),'raw_close':float(p),'share_method':sh['method'],'share_end':sh['end'],'share_filed':sh['filed'],'equity_method':eq['concept'],'equity_end':eq['end'],'equity_filed':eq['filed']}

def ann(xs):
    if not xs:return None
    a=np.asarray(xs,float)
    if np.any(a<=-1):return None
    g=float(np.prod(1+a)); return float(g**((252.0/REBALANCE)/len(a))-1)
def avg(xs):return None if not xs else float(np.mean(np.asarray(xs,float)))

def main():
    cm=r2.ciks(); facts={s:r2.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cm[s]:010d}.json") for s in (*DEV,EXTERNAL)}
    raw={s:r2.prices(s) for s in (*DEV,EXTERNAL)}; adj={s:adj_prices(s) for s in ALL}
    common=pd.DatetimeIndex(sorted(set.intersection(*[set(adj[s].index) for s in (*DEV,"ITB")])))
    frame=pd.DataFrame({s:adj[s].reindex(common) for s in (*DEV,"ITB")}).dropna()
    first=next(i for i,t in enumerate(frame.index) if t.date()>=date(2019,3,1))
    idxs=list(range(first,len(frame)-HOLD-DELAY,REBALANCE))
    decisions=[]; per={s:[] for s in DEV}; ext_events=[]
    for i in idxs:
        ts=frame.index[i]; states={s:btm_state(facts[s],raw[s],ts) for s in DEV}
        if any(v is None for v in states.values()):continue
        ranked=sorted(DEV,key=lambda s:(-states[s]['book_to_market'],s)); selected=ranked[:TOP_N]
        ei=i+DELAY; xi=ei+HOLD
        gross={s:float(frame[s].iloc[xi]/frame[s].iloc[ei]-1) for s in DEV}; base_g=float(np.mean(list(gross.values())))
        base_n=base_g-COMMON_COST_BPS/10000; sel_g=float(np.mean([gross[s] for s in selected])); sel_ex=(sel_g-base_g)*10000-MARGINAL_HURDLE_BPS
        overlay=base_n+TILT*(sel_g-base_g-MARGINAL_HURDLE_BPS/10000); itb=float(frame['ITB'].iloc[xi]/frame['ITB'].iloc[ei]-1)-COMMON_COST_BPS/10000
        for s in selected: per[s].append((gross[s]-base_g)*10000-MARGINAL_HURDLE_BPS)
        external=None
        if ts in adj[EXTERNAL].index:
            es=btm_state(facts[EXTERNAL],raw[EXTERNAL],ts)
            loc=adj[EXTERNAL].index.get_loc(ts) if ts in adj[EXTERNAL].index else None
            if es is not None and isinstance(loc,(int,np.integer)) and loc+DELAY+HOLD<len(adj[EXTERNAL]):
                combo={s:states[s]['book_to_market'] for s in DEV}; combo[EXTERNAL]=es['book_to_market']; top=sorted(combo,key=lambda s:(-combo[s],s))[:TOP_N]
                er=float(adj[EXTERNAL].iloc[loc+DELAY+HOLD]/adj[EXTERNAL].iloc[loc+DELAY]-1); ex=(er-base_g)*10000-MARGINAL_HURDLE_BPS; picked=EXTERNAL in top
                if picked:ext_events.append(ex)
                external={'selected_top2':picked,'peer_excess_after50_bps':ex,'state':es,'combined_top2':top}
        decisions.append({'signal_date':ts.isoformat(),'entry_date':frame.index[ei].isoformat(),'exit_date':frame.index[xi].isoformat(),'selected':selected,'states':states,'baseline_equal_dev_net':base_n,'overlay_75core_25value_net':overlay,'incremental_overlay_bps':(overlay-base_n)*10000,'selected_peer_excess_after50_bps':sel_ex,'itb_net':itb,'external_DFH':external})
    if len(decisions)<MIN_DECISIONS: raise RuntimeError(f"eligible decisions {len(decisions)} < {MIN_DECISIONS}")
    parts=[list(map(int,p)) for p in np.array_split(np.arange(len(decisions)),FOLDS)]; folds=[]
    for n,ii in enumerate(parts,1):
        rr=[decisions[j] for j in ii]; folds.append({'fold':n,'decisions':len(rr),'mean_incremental_overlay_bps':avg([x['incremental_overlay_bps'] for x in rr]),'mean_selected_peer_excess_after50_bps':avg([x['selected_peer_excess_after50_bps'] for x in rr])})
    devrows=[]; passes=0
    for s in DEV:
        m=avg(per[s]); ok=len(per[s])>=MIN_DEV_EVENTS and m is not None and m>0; passes+=int(ok); devrows.append({'symbol':s,'selected_events':len(per[s]),'mean_peer_excess_after50_bps':m,'pass':ok})
    base=[x['baseline_equal_dev_net'] for x in decisions]; over=[x['overlay_75core_25value_net'] for x in decisions]; itb=[x['itb_net'] for x in decisions]; se=[x['selected_peer_excess_after50_bps'] for x in decisions]
    ba,oa,ia=ann(base),ann(over),ann(itb); inc=oa-ba if ba is not None and oa is not None else None; pf=sum(x['mean_incremental_overlay_bps'] is not None and x['mean_incremental_overlay_bps']>0 for x in folds); em=avg(ext_events); ep=len(ext_events)>=MIN_EXT_EVENTS and em is not None and em>0
    gate=len(decisions)>=MIN_DECISIONS and inc is not None and inc>0 and avg(se)>0 and pf>=4 and passes>=MIN_DEV_PASSES and ep
    out={'schema':'public.homebuilder_pit_book_to_market_tilt_r1.v1','experiment_id':'HOMEBUILDER-PIT-BOOK-TO-MARKET-TILT-R1','inherits_learning_ids':['SLP-20260913-HOMEBUILDER-SEC-QUALITY-TILT-R1','SLP-20260913-HOMEBUILDER-PIT-VALUATION-SOURCE-R3'],'uncertainty_resolved':'whether point-in-time valuation, rather than rejected quality levels or price consensus, can improve the equal-weight Homebuilder core','claim_tested':'Higher filed-at book-to-market identifies a robust marginal Homebuilder tilt over equal weight.','contract':{'development_symbols':list(DEV),'fresh_external_symbol':EXTERNAL,'feature':'book equity / point-in-time market cap using R3 admitted source contract; high is better','rebalance_sessions':REBALANCE,'delay_sessions':DELAY,'hold_sessions':HOLD,'common_cost_bps':COMMON_COST_BPS,'marginal_hurdle_bps':MARGINAL_HURDLE_BPS,'core_weight':.75,'tilt_weight':TILT,'top_n':TOP_N,'chronology_folds':FOLDS,'primary_control':'equal-weight development builders','secondary_control':'ITB','external_never_fit':True},'decisions':len(decisions),'baseline_equal_dev_annualized':ba,'valuation_overlay_annualized':oa,'itb_annualized':ia,'annualized_increment':inc,'mean_incremental_overlay_bps':avg([x['incremental_overlay_bps'] for x in decisions]),'mean_selected_peer_excess_after50_bps':avg(se),'folds':folds,'positive_folds':pf,'development_symbol_results':devrows,'development_symbol_passes':passes,'external_DFH_selected_events':len(ext_events),'external_DFH_mean_peer_excess_after50_bps':em,'external_DFH_pass':ep,'gates':{'increment_positive':inc is not None and inc>0,'selected_peer_excess_positive':avg(se)>0,'at_least_4_of_5_folds_positive':pf>=4,'at_least_5_dev_symbols_pass':passes>=MIN_DEV_PASSES,'fresh_DFH_pass':ep},'decision':'HOMEBUILDER_PIT_BOOK_TO_MARKET_TILT_PASSES_GATE' if gate else 'HOMEBUILDER_PIT_BOOK_TO_MARKET_TILT_REJECTED_AS_SPECIFIED','forbidden_parameter_rescue':['change top-N','change 75/25 weights','change 63-session horizon','reduce cost or hurdle','drop weak names/folds','change source fallback after outcome','cherry-pick a passing builder'],'authority':'SCIENTIFIC_EVIDENCE_ONLY','portfolio_allocation_authority':False,'live_trading_change':False}
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n'); print(json.dumps(out,indent=2,sort_keys=True))
if __name__=='__main__':main()

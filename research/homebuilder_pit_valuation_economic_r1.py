#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, json
from pathlib import Path
import numpy as np
import pandas as pd

SRC=Path(__file__).with_name('homebuilder_pit_valuation_source_probe_r3.py')
spec=importlib.util.spec_from_file_location('src',SRC); src=importlib.util.module_from_spec(spec); spec.loader.exec_module(src)
r2=src.r2
OUT=Path('research/results/homebuilder_pit_valuation_economic_r1.json')
DEV=r2.DEV; EXTERNAL=r2.EXTERNAL; HOLD=63; DELAY=1; COST_BPS=25.0; HURDLE_BPS=50.0; TILT=0.25; TOP_N=2; FOLDS=5

def ann(rs):
    if not rs:return None
    a=np.asarray(rs,float)
    if np.any(a<=-1):return None
    return float(np.prod(1+a)**((252/HOLD)/len(a))-1)
def mean(xs): return None if not xs else float(np.mean(np.asarray(xs,float)))
def main():
    cm=r2.ciks(); prices={s:r2.prices(s) for s in r2.SYMBOLS}; facts={s:r2.get(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cm[s]:010d}.json') for s in r2.SYMBOLS}
    common=pd.DatetimeIndex(sorted(set.intersection(*[set(prices[s].index) for s in DEV])))
    frame=pd.DataFrame({s:prices[s].reindex(common) for s in DEV}).dropna()
    first=next(i for i,d in enumerate(frame.index) if d>=pd.Timestamp('2019-03-01'))
    idxs=list(range(first,len(frame)-HOLD-DELAY,HOLD)); decisions=[]; per={s:[] for s in DEV}; ext=[]
    for i in idxs:
        sig=frame.index[i]; states={}
        for s in DEV:
            sh=r2.share_fact(facts[s],sig); eq=src.equity_fact(facts[s],sig)
            if not sh or not eq: states={}; break
            m=sh['value']*float(frame[s].iloc[i]); b=eq['value']/m if m>0 else np.nan
            if not np.isfinite(b) or not(.01<=b<=10): states={}; break
            states[s]=float(b)
        if len(states)!=len(DEV):continue
        selected=[s for s,_ in sorted(states.items(),key=lambda x:(-x[1],x[0]))[:TOP_N]]
        ei=i+DELAY; xi=ei+HOLD; gross={s:float(frame[s].iloc[xi]/frame[s].iloc[ei]-1) for s in DEV}; base=float(np.mean(list(gross.values()))); base_net=base-COST_BPS/10000; sel=float(np.mean([gross[s] for s in selected])); peer=(sel-base)*10000-HURDLE_BPS; overlay=base_net+TILT*(sel-base-HURDLE_BPS/10000)
        for s in selected: per[s].append((gross[s]-base)*10000-HURDLE_BPS)
        ex=None
        if sig in prices[EXTERNAL].index:
            sh=r2.share_fact(facts[EXTERNAL],sig); eq=src.equity_fact(facts[EXTERNAL],sig)
            if sh and eq:
                px=float(prices[EXTERNAL].loc[sig]); b=eq['value']/(sh['value']*px); comb={**states,EXTERNAL:float(b)}; top=[s for s,_ in sorted(comb.items(),key=lambda x:(-x[1],x[0]))[:TOP_N]]; loc=prices[EXTERNAL].index.get_loc(sig)
                if isinstance(loc,(int,np.integer)) and loc+DELAY+HOLD<len(prices[EXTERNAL]):
                    er=float(prices[EXTERNAL].iloc[loc+DELAY+HOLD]/prices[EXTERNAL].iloc[loc+DELAY]-1); ee=(er-base)*10000-HURDLE_BPS; chosen=EXTERNAL in top
                    if chosen:ext.append(ee)
                    ex={'selected_top2':chosen,'peer_excess_after50_bps':ee,'book_to_market':float(b)}
        decisions.append({'signal_date':sig.date().isoformat(),'selected':selected,'baseline_equal_dev_net':base_net,'overlay_75core_25value_net':overlay,'incremental_overlay_bps':(overlay-base_net)*10000,'selected_peer_excess_after50_bps':peer,'external_DFH':ex})
    parts=[list(map(int,p)) for p in np.array_split(np.arange(len(decisions)),FOLDS)]; folds=[{'fold':j+1,'decisions':len(p),'mean_incremental_overlay_bps':mean([decisions[i]['incremental_overlay_bps'] for i in p])} for j,p in enumerate(parts)]
    b=ann([d['baseline_equal_dev_net'] for d in decisions]); o=ann([d['overlay_75core_25value_net'] for d in decisions]); inc=None if b is None or o is None else o-b; pos=sum(f['mean_incremental_overlay_bps'] is not None and f['mean_incremental_overlay_bps']>0 for f in folds); devrows=[{'symbol':s,'selected_events':len(per[s]),'mean_peer_excess_after50_bps':mean(per[s]),'pass':len(per[s])>=3 and mean(per[s]) is not None and mean(per[s])>0} for s in DEV]; dp=sum(x['pass'] for x in devrows); em=mean(ext); ep=len(ext)>=2 and em is not None and em>0
    gate=len(decisions)>=27 and inc is not None and inc>0 and mean([d['selected_peer_excess_after50_bps'] for d in decisions])>0 and pos>=4 and dp>=5 and ep
    out={'schema':'public.homebuilder_pit_valuation_economic_r1.v1','experiment_id':'HOMEBUILDER-PIT-VALUATION-ECONOMIC-R1','inherits_learning_ids':['SLP-20260913-HOMEBUILDER-PIT-VALUATION-SOURCE-R3','SLP-20260913-HOMEBUILDER-SEC-QUALITY-TILT-R1'],'uncertainty_resolved':'whether frozen PIT book-to-market adds robust marginal Homebuilder selection value over equal weight','contract':{'signal':'book_to_market descending','core_weight':0.75,'tilt_weight':TILT,'top_n':TOP_N,'delay_sessions':DELAY,'hold_sessions':HOLD,'common_cost_bps':COST_BPS,'marginal_hurdle_bps':HURDLE_BPS,'folds':FOLDS,'external':'untouched DFH'},'decisions':len(decisions),'baseline_equal_dev_annualized':b,'value_overlay_annualized':o,'annualized_increment':inc,'mean_selected_peer_excess_after50_bps':mean([d['selected_peer_excess_after50_bps'] for d in decisions]),'positive_folds':pos,'fold_rows':folds,'development_symbol_passes':dp,'development_rows':devrows,'fresh_DFH_selected_events':len(ext),'fresh_DFH_mean_peer_excess_after50_bps':em,'fresh_DFH_pass':ep,'decision':'HOMEBUILDER_PIT_VALUATION_PASSES_GATE' if gate else 'HOMEBUILDER_PIT_VALUATION_REJECTED_AS_SPECIFIED','decisions_detail':decisions,'live_trading_change':False}
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n'); print(json.dumps({k:out[k] for k in ['decision','decisions','baseline_equal_dev_annualized','value_overlay_annualized','annualized_increment','mean_selected_peer_excess_after50_bps','positive_folds','development_symbol_passes','fresh_DFH_selected_events','fresh_DFH_mean_peer_excess_after50_bps','fresh_DFH_pass']},indent=2))
if __name__=='__main__':main()

#!/usr/bin/env python3
import json
from pathlib import Path
import numpy as np
import pandas as pd
import futures_crossmarket_screen_r1 as base

COSTS=(1.0,2.5,5.0)

def eval_rule(df, weights, cost_bps):
    close=df['Close'].astype(float)
    ret=close.pct_change()
    w=weights.shift(1).fillna(0.0).clip(0,1)
    turn=w.diff().abs().fillna(w.abs())
    cand=w*ret-turn*(cost_bps*1e-4)
    matched=float(w.mean())*ret
    z=pd.concat([cand.rename('c'),matched.rename('b'),w.rename('w')],axis=1).dropna()
    folds=base.fold_excess(z.c,z.b); cm=base.ann_metrics(z.c,252); bm=base.ann_metrics(z.b,252); pos=sum(x['excess']>0 for x in folds)
    return {'candidate':cm,'exposure_matched_static':bm,'mean_exposure':float(z.w.mean()),'annual_turnover':float(turn.reindex(z.index).mean()*252),'positive_excess_folds':pos,'folds':folds,'screen_supported':bool(cm['cagr'] is not None and bm['cagr'] is not None and cm['cagr']>bm['cagr'] and pos>=3 and cm['sharpe'] is not None and bm['sharpe'] is not None and cm['sharpe']>=bm['sharpe'])}

def main():
    out={'schema':'research.futures_crossmarket_rotation_screen_r2','classification':'EXTERNAL_PROXY_SCREEN_ONLY_NOT_CANONICAL_FUTURES_EVIDENCE','scientific_contract':{'purpose':'rotate away from failed 252d monthly trend and overnight/intraday screens without tuning them','markets':base.MARKETS,'mechanisms':{'DONCHIAN20_BREAKOUT':'prior close above prior 20-session high -> long next session, else cash','FIVEDAY_REVERSAL':'prior 5-session return below zero -> long next session, else cash'},'cost_bps_per_turnover_unit':list(COSTS),'primary_cost_bps':2.5,'matched_control':'static exposure to same proxy over identical daily return window at candidate mean exposure','support_gate':'candidate CAGR > matched static, >=3/5 positive excess folds, Sharpe >= matched Sharpe at 2.5 bps','no_parameter_search':True,'no_canonical_roll_claim':True,'no_promotion_authority':True},'markets':{}}
    for name,ticker in base.MARKETS.items():
        try:
            df,sha=base.load_market(ticker); close=df['Close'].astype(float)
            breakout=(close>close.shift(1).rolling(20,min_periods=20).max()).astype(float)
            reversal=(close.pct_change(5)<0).astype(float)
            lane={'ticker':ticker,'rows':int(len(df)),'first':str(df.index.min().date()),'last':str(df.index.max().date()),'normalized_ohlcv_sha256':sha,'tests':{}}
            for bp in COSTS:
                lane['tests'][f'breakout20_{bp:g}bps']=eval_rule(df,breakout,bp)
                lane['tests'][f'reversal5_{bp:g}bps']=eval_rule(df,reversal,bp)
            lane['primary_screen']={'breakout20_supported':lane['tests']['breakout20_2.5bps']['screen_supported'],'reversal5_supported':lane['tests']['reversal5_2.5bps']['screen_supported']}
            out['markets'][name]=lane
        except Exception as e:
            out['markets'][name]={'ticker':ticker,'state':'DATA_OR_PROXY_BLOCKED','error':str(e)}
    out['summary']={'evaluated_markets':sum('primary_screen' in v for v in out['markets'].values()),'breakout20_supported_markets':[k for k,v in out['markets'].items() if v.get('primary_screen',{}).get('breakout20_supported')],'reversal5_supported_markets':[k for k,v in out['markets'].items() if v.get('primary_screen',{}).get('reversal5_supported')],'interpretation':'A supported proxy screen earns canonical roll-aware follow-up. An unsupported screen rejects only this frozen mechanism on this external representation, not the futures market.'}
    Path('futures_crossmarket_rotation_screen_r2.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out['summary'],indent=2,sort_keys=True))
if __name__=='__main__': main()

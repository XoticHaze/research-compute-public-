#!/usr/bin/env python3
import json
from pathlib import Path
import pandas as pd
import futures_crossmarket_screen_r1 as r1
import futures_crossmarket_rotation_screen_r2 as r2

MICROS={'MNQ':'MNQ=F','MES':'MES=F','M2K':'M2K=F','MCL':'MCL=F','MGC':'MGC=F'}
COSTS=(1.0,2.5,5.0)

def main():
    r1.MIN_ROWS=700
    out={'schema':'research.futures_micro_crossmarket_screen_r3','classification':'EXTERNAL_MICRO_PROXY_SCREEN_ONLY_NOT_CANONICAL_FUTURES_EVIDENCE','scientific_contract':{'markets':MICROS,'mechanisms':['TSMOM_252_MONTHLY','OVERNIGHT_VS_INTRADAY_20','DONCHIAN20_BREAKOUT','FIVEDAY_REVERSAL'],'cost_bps':list(COSTS),'primary_cost_bps':2.5,'matched_control':'same proxy / identical return window / exposure-matched static','min_rows':700,'no_parameter_search':True,'no_canonical_roll_claim':True,'no_promotion_authority':True},'markets':{}}
    for name,ticker in MICROS.items():
        try:
            df,sha=r1.load_market(ticker); close=df['Close'].astype(float)
            breakout=(close>close.shift(1).rolling(20,min_periods=20).max()).astype(float)
            reversal=(close.pct_change(5)<0).astype(float)
            lane={'ticker':ticker,'rows':int(len(df)),'first':str(df.index.min().date()),'last':str(df.index.max().date()),'normalized_ohlcv_sha256':sha,'tests':{}}
            for bp in COSTS:
                lane['tests'][f'trend252_{bp:g}bps']=r1.monthly_trend(df,bp)
                lane['tests'][f'overnight20_{bp:g}bps']=r1.overnight_intraday(df,bp)
                lane['tests'][f'breakout20_{bp:g}bps']=r2.eval_rule(df,breakout,bp)
                lane['tests'][f'reversal5_{bp:g}bps']=r2.eval_rule(df,reversal,bp)
            lane['primary_screen']={k:lane['tests'][f'{prefix}_2.5bps']['screen_supported'] for k,prefix in [('trend252_supported','trend252'),('overnight20_supported','overnight20'),('breakout20_supported','breakout20'),('reversal5_supported','reversal5')]}
            out['markets'][name]=lane
        except Exception as e:
            out['markets'][name]={'ticker':ticker,'state':'DATA_OR_PROXY_BLOCKED','error':str(e)}
    out['summary']={'evaluated_markets':sum('primary_screen' in v for v in out['markets'].values()),'supported':{mech:[k for k,v in out['markets'].items() if v.get('primary_screen',{}).get(mech)] for mech in ['trend252_supported','overnight20_supported','breakout20_supported','reversal5_supported']},'blocked':{k:v for k,v in out['markets'].items() if v.get('state')},'interpretation':'Unsupported proxy screens reject only the frozen mechanism on this vendor micro representation. Supported screens earn canonical dated-contract/roll-aware follow-up.'}
    Path('futures_micro_crossmarket_screen_r3.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out['summary'],indent=2,sort_keys=True))
if __name__=='__main__': main()

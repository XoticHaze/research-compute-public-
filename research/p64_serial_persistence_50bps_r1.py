from __future__ import annotations
import json
from pathlib import Path
import p66_combination_serial_persistence_r1 as p66

BP=50

def main():
    fr,close=p66.frame(BP)
    tests={}
    for months in (36,60):
        tests[f'rolling_{months}m_vs_matched']=p66.roll(fr,months,'matched')
        tests[f'rolling_{months}m_vs_qqq']=p66.roll(fr,months,'qqq')
    tests['block_bootstrap_vs_matched']=p66.block_bootstrap(fr,'matched',seed=640)
    tests['block_bootstrap_vs_qqq']=p66.block_bootstrap(fr,'qqq',seed=641)
    out={'schema':'research.p64_serial_persistence_50bps_r1','parent':'P64','hypothesis':'The fixed P64 50/50 cross-asset plus independent-industry blend retains contiguous matched-control and QQQ opportunity-cost persistence at the same 50-bps component cost used when P64 is consumed by P82.','scientific_contract':{'component':'unchanged P64 50/50 parsimonious cross-asset plus independent-industry blend','cost_bps':BP,'rolling_windows_months':[36,60],'moving_block_months':12,'bootstrap_draws':5000,'benchmarks':['matched static blend','QQQ'],'no_parameter_or_weight_tuning':True},'tests':tests}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p64_serial_persistence_50bps_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()

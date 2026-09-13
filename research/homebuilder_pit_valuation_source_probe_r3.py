#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, json
from pathlib import Path
import pandas as pd

BASE=Path(__file__).with_name('homebuilder_pit_valuation_source_probe_r2.py')
spec=importlib.util.spec_from_file_location('r2',BASE); r2=importlib.util.module_from_spec(spec); spec.loader.exec_module(r2)
OUT=Path('research/results/homebuilder_pit_valuation_source_probe_r3.json')

def equity_fact(payload, asof):
    direct=r2.instant(payload,r2.EQUITY,asof)
    if direct:return direct
    a=r2.instant(payload,(("us-gaap","Assets"),),asof); l=r2.instant(payload,(("us-gaap","Liabilities"),),asof)
    if not a or not l:return None
    v=a['value']-l['value']
    if v<=0:return None
    return {'value':v,'concept':'AssetsMinusLiabilities','method':'derived_instant','end':max(a['end'],l['end']),'filed':max(a['filed'],l['filed']),'staleness_days':max(a['staleness_days'],l['staleness_days'])}

def main():
    cm=r2.ciks(); diag={}; rows={}
    for sym in r2.SYMBOLS:
        ps=r2.prices(sym); cf=r2.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cm[sym]:010d}.json"); rr=[]; sm=set(); em=set()
        for a in r2.month_ends():
            px=r2.px_at(ps,a); sh=r2.share_fact(cf,a); eq=equity_fact(cf,a)
            if not px or not sh or not eq:continue
            d,p=px; m=sh['value']*p; b=eq['value']/m if m>0 else float('nan')
            if not(pd.notna(m) and pd.notna(b) and 1e8<=m<=2e11 and .01<=b<=10):continue
            sm.add(sh['method']); em.add(eq.get('concept'))
            rr.append({'asof':a.date().isoformat(),'price_date':d.date().isoformat(),'raw_close':p,'shares':sh,'equity':eq,'market_cap':m,'book_to_market':b})
        rows[sym]=rr; vals=[x['book_to_market'] for x in rr]
        diag[sym]={'eligible_months':len(rr),'first':rr[0]['asof'] if rr else None,'last':rr[-1]['asof'] if rr else None,'share_methods':sorted(sm),'equity_methods':sorted(em),'btm_median':float(pd.Series(vals).median()) if vals else None,'btm_min':min(vals,default=None),'btm_max':max(vals,default=None)}
    gates={'all_dev_min_72_months':all(diag[s]['eligible_months']>=72 for s in r2.DEV),'dfh_min_48_months':diag[r2.EXTERNAL]['eligible_months']>=48,'all_symbols_covered':all(diag[s]['eligible_months']>0 for s in r2.SYMBOLS)}
    out={'schema':'public.homebuilder_pit_valuation_source_probe_r3.v1','experiment_id':'HOMEBUILDER-PIT-VALUATION-SOURCE-PROBE-R3','inherits':['HOMEBUILDER-PIT-VALUATION-SOURCE-PROBE-R1','HOMEBUILDER-PIT-SHARE-CONCEPT-AUDIT-R1','HOMEBUILDER-PIT-VALUATION-SOURCE-PROBE-R2'],'uncertainty_resolved':'whether combining the pre-return weighted-average basic-share fallback with the already-proven SEC PIT Assets-minus-Liabilities equity fallback yields sufficient coverage for the unchanged Homebuilder valuation universe','economic_outcomes_examined':False,'contract':{'shares':'instant preferred; else filed-at 60-110d WeightedAverageNumberOfSharesOutstandingBasic; <=200d stale','equity':'StockholdersEquity; then including-NCI; then filed-at Assets-Liabilities, matching proven Homebuilder SEC PIT precedent c5dfcc2','market_price':'raw contemporaneous close','source_sanity_only':'market cap $0.1b-$200b and B/M 0.01-10'},'diagnostics':diag,'gates':gates,'decision':'HOMEBUILDER_PIT_VALUATION_SOURCE_ADMITTED_R3' if all(gates.values()) else 'HOMEBUILDER_PIT_VALUATION_SOURCE_REJECTED_R3','rows_by_symbol':rows,'authority':'SOURCE_CONTRACT_ONLY','live_trading_change':False}
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n'); print(json.dumps({'decision':out['decision'],'diagnostics':diag,'gates':gates},indent=2,sort_keys=True))
if __name__=='__main__':main()

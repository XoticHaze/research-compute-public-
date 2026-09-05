from __future__ import annotations
import importlib.util, json
from pathlib import Path

spec=importlib.util.spec_from_file_location('base','research/run_xlu_vs_cash.py')
base=importlib.util.module_from_spec(spec); spec.loader.exec_module(base)

def main():
    fs={s:base.load(s) for s in base.SYMBOLS}
    ts={s:base.trades(s,fs[s]) for s in base.SYMBOLS}
    ls={s:base.leg(fs[s],ts[s]) for s in base.SYMBOLS}
    raw={s:fs[s].set_index('timestamp').price.pct_change().dropna() for s in base.SYMBOLS}
    cal=ls['AMAT'].index.union(ls['APH'].index).union(ls['XLU'].index).sort_values()
    ls={s:ls[s].reindex(cal,fill_value=0.) for s in base.SYMBOLS}
    cash=ls['AMAT']*0.; conditional=ls['AMAT']*0.; rows=[]
    for k in range(1,base.FOLDS+1):
        ent=[x for s in base.SYMBOLS for x in ts[s] if x['fold']==k]
        lo=min(x['entry_timestamp'] for x in ent); hi=max(x['exit_timestamp'] for x in ent); m=(cal>=lo)&(cal<=hi)
        w=base.weights(raw,base.SYMBOLS,lo)
        core=w['AMAT']*ls['AMAT'].loc[m]+w['APH']*ls['APH'].loc[m]
        # Precommitted adverse-state rule: activate XLU only when the equal-weight core's
        # trailing 20-session return is negative. shift(1) prevents same-day lookahead.
        trailing=(0.5*raw['AMAT'].reindex(cal).fillna(0)+0.5*raw['APH'].reindex(cal).fillna(0)).rolling(20).sum().shift(1)
        adverse=(trailing.loc[m]<0).astype(float)
        xlu=w['XLU']*ls['XLU'].loc[m]*adverse
        cash.loc[m]=core; conditional.loc[m]=core+xlu
        c=float(core.sum()); d=float((core+xlu).sum())
        rows.append({'fold':k,'adverse_days':int(adverse.sum()),'cash_bps':c*10000,'conditional_bps':d*10000,'incremental_bps':(d-c)*10000,'positive':d>c})
    cm=base.metrics(cash); dm=base.metrics(conditional); pos=sum(r['positive'] for r in rows)
    passed=dm['max_drawdown']>=cm['max_drawdown'] and dm['return_over_volatility']>=cm['return_over_volatility'] and pos>=4
    out={'schema':'foundry.research.xlu_conditional_derisk.v1','rule':'XLU sleeve active only when lagged 20-session equal-weight AMAT/APH return < 0','cash_control':cm,'conditional_xlu':dm,'folds':rows,'gate':{'passed':bool(passed),'positive_increment_folds':pos,'decision':'retain_conditional_xlu_derisk_challenger' if passed else 'reject_conditional_xlu_derisk_challenger'},'research_only':True}
    Path('conditional-result.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n'); print(json.dumps(out,indent=2,sort_keys=True))
if __name__=='__main__': main()

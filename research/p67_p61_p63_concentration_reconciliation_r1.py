from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import fixed_multifactor_cross_sectional_r1 as base
import p61_crossasset_parsimonious_dependence_r1 as p61
import p63_crossasset_parsimonious_regime_r1 as p63


def calc(fr,bps=25):
    cand=fr.gross-fr.turnover*bps/10000; ex=cand-fr.ew; strong=ex.nlargest(5).index; keep=~fr.index.isin(strong)
    cm,bm=base.metrics(cand[keep]),base.metrics(fr.ew[keep])
    return {"months":len(fr),"removed":[str(x.date()) for x in strong],"excess_cagr":cm["cagr"]-bm["cagr"],"annualized_mean_excess":float((cand[keep]-fr.ew[keep]).mean()*12)}

def main():
    a,ca=p61.run(p61.BASE); b,cb=p63.frame(); common=a.index.intersection(b.index)
    diffs={col:float(np.max(np.abs(a.loc[common,col].to_numpy()-b.loc[common,col].to_numpy()))) for col in ("gross","ew","turnover")}
    out={"schema":"research.p67_p61_p63_concentration_reconciliation_r1","parents":["P46","P57"],"hypothesis":"The contradictory P61/P63 five-extreme-month conclusions are attributable to input drift or implementation drift and can be resolved on one execution surface with same-time source hashes.","scientific_contract":{"cost_bps":25,"comparison":["index","gross","matched EW","turnover","removed dates","post-removal excess CAGR"],"no_parameter_tuning":True},"source":{"p61_panel_sha256":base.source_hash(ca),"p63_panel_sha256":base.source_hash(cb)},"comparison":{"p61":calc(a),"p63":calc(b),"common_months":len(common),"index_equal":bool(a.index.equals(b.index)),"max_abs_diffs":diffs}}
    Path("artifacts").mkdir(exist_ok=True); Path("artifacts/p67_p61_p63_concentration_reconciliation_r1.json").write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps(out["comparison"],sort_keys=True))
if __name__=="__main__": main()

#!/usr/bin/env python3
import json
from pathlib import Path
import numpy as np
import pandas as pd
import mnq_cme_session_trend_r13 as r13


def main():
    root=Path('/tmp/mnq-source/plaintext_csv')
    inv=r13.build_session_inventory(root); chain,sched,rolls=r13.build_chain(inv); ref,prov=r13.axb()
    z=pd.concat([chain['return'].rename('chain'),ref.pct_change().rename('ref')],axis=1).dropna()
    z['diff_bps']=(z.chain-z.ref)*10000; z['abs_bps']=z.diff_bps.abs()
    cidx=(1+z.chain).cumprod(); ridx=(1+z.ref).cumprod()
    cm=(1+z.chain).resample('ME').prod()-1; rm=(1+z.ref).resample('ME').prod()-1
    monthly=pd.concat([cm.rename('chain'),rm.rename('ref')],axis=1).dropna()
    # claim-relevant 252-session sign agreement on identical overlap rows
    cs=(cidx/cidx.shift(252)-1); rs=(ridx/ridx.shift(252)-1); sig=pd.concat([cs.rename('chain'),rs.rename('ref')],axis=1).dropna()
    top=[]
    for dt,row in z.nlargest(12,'abs_bps').iterrows():
        top.append({'date':dt.date().isoformat(),'chain_return':float(row.chain),'reference_return':float(row.ref),'difference_bps':float(row.diff_bps)})
    out={'schema':'research.mnq_claim_fidelity_r15','classification':'CLAIM_LEVEL_FIDELITY_DIAGNOSTIC_NOT_NEW_ALPHA_TEST','contract':{'purpose':'judge fidelity at the actual monthly/252-session mechanism level rather than failing the source on a generic daily-correlation threshold','model_claim':'prior 252 completed-session return sign sampled monthly, next month long/cash','no_parameter_change':True},'daily':{'sessions':len(z),'correlation':float(z[['chain','ref']].corr().iloc[0,1]),'median_abs_bps':float(z.abs_bps.median()),'p95_abs_bps':float(z.abs_bps.quantile(.95)),'top_discrepancies':top},'monthly':{'months':len(monthly),'correlation':float(monthly.corr().iloc[0,1]),'median_abs_difference_bps':float(((monthly.chain-monthly.ref)*10000).abs().median()),'max_abs_difference_bps':float(((monthly.chain-monthly.ref)*10000).abs().max())},'signal':{'observations':len(sig),'same_252_sign_fraction':float((np.sign(sig.chain)==np.sign(sig.ref)).mean()) if len(sig) else None,'chain_positive_fraction':float((sig.chain>0).mean()) if len(sig) else None,'reference_positive_fraction':float((sig.ref>0).mean()) if len(sig) else None},'reference':prov}
    # Because current external overlap is <252 sessions after intersection, signal may be unavailable. Monthly fidelity can still validate aggregation while not proving 252-sign fidelity.
    if out['monthly']['correlation']>=.995 and out['monthly']['median_abs_difference_bps']<=5 and (out['signal']['same_252_sign_fraction'] is None or out['signal']['same_252_sign_fraction']>=.98):
        out['decision']='MNQ_CLAIM_LEVEL_FIDELITY_SUPPORTED'
    else:
        out['decision']='MNQ_CLAIM_LEVEL_FIDELITY_INCONCLUSIVE'
    out['consequence']='A supported result validates the chain at the mechanism-relevant aggregation but does not by itself turn R13 into a survivor; R13 economics must still pass. An inconclusive result keeps the science open and requires longer independent dated-contract overlap.'
    Path('mnq_claim_fidelity_r15.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)+'\n'); print(json.dumps(out,sort_keys=True))
if __name__=='__main__':main()

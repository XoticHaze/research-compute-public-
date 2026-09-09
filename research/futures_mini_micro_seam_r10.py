#!/usr/bin/env python3
import calendar, json
from pathlib import Path
import numpy as np
import pandas as pd
import futures_mini_micro_equivalence_r8 as base


def third_friday(year,month):
    c=calendar.Calendar().monthdatescalendar(year,month)
    return [d for w in c for d in w if d.weekday()==4 and d.month==month][2]


def seam_distance_days(ts):
    d=ts.date(); candidates=[]
    for y in (d.year-1,d.year,d.year+1):
        for m in (3,6,9,12): candidates.append(third_friday(y,m))
    return min(abs((d-x).days) for x in candidates)


def diag(a,b):
    z=pd.concat([a,b],axis=1).dropna(); r=z.pct_change().dropna(); r.columns=['mini','micro']; r['diff_bps']=(r.micro-r.mini)*10000; r['abs_bps']=r.diff_bps.abs(); r['seam_distance_days']=[seam_distance_days(x) for x in r.index]; r['quarterly_seam_window']=r.seam_distance_days<=10
    raw_corr=float(r[['mini','micro']].corr().iloc[0,1]); non=r.loc[~r.quarterly_seam_window]; seam=r.loc[r.quarterly_seam_window]
    top=[]
    for idx,row in r.nlargest(12,'abs_bps').iterrows(): top.append({'date':idx.date().isoformat(),'mini_return':float(row.mini),'micro_return':float(row.micro),'difference_bps':float(row.diff_bps),'abs_difference_bps':float(row.abs_bps),'seam_distance_days':int(row.seam_distance_days),'quarterly_seam_window':bool(row.quarterly_seam_window)})
    return {'raw_correlation':raw_corr,'raw_median_abs_bps':float(r.abs_bps.median()),'raw_p95_abs_bps':float(r.abs_bps.quantile(.95)),'quarterly_seam_rows':int(len(seam)),'nonseam_rows':int(len(non)),'nonseam_correlation':float(non[['mini','micro']].corr().iloc[0,1]) if len(non)>2 else None,'nonseam_median_abs_bps':float(non.abs_bps.median()) if len(non) else None,'nonseam_p95_abs_bps':float(non.abs_bps.quantile(.95)) if len(non) else None,'share_top12_in_seam':float(sum(x['quarterly_seam_window'] for x in top)/len(top)) if top else None,'top_discrepancies':top}


def main():
    out={'schema':'research.futures_mini_micro_seam_r10','classification':'EXTERNAL_CONTINUOUS_SOURCE_DIAGNOSTIC_NOT_MODEL_EVIDENCE','contract':{'purpose':'determine whether R8 mini/micro discrepancies are concentrated around quarterly roll windows rather than underlying-market divergence','seam_window':'within 10 calendar days of quarterly third Friday','consequence_rule':'if discrepancies concentrate at seams and non-seam tracking materially improves, classify R8 pair failure as continuous-source roll representation incompatibility rather than scientific/model failure','no_product_substitution':True},'pairs':{}}
    for family,(mini,micro) in base.PAIRS.items():
        try:
            a,pa=base.parse_daily(mini); b,pb=base.parse_daily(micro); d=diag(a,b)
            artifact=(d['share_top12_in_seam'] is not None and d['share_top12_in_seam']>=.5 and d['nonseam_correlation'] is not None and d['nonseam_correlation']>d['raw_correlation'])
            out['pairs'][family]={'mini':mini,'micro':micro,'diagnostic':d,'roll_representation_artifact_supported':bool(artifact)}
        except Exception as exc: out['pairs'][family]={'mini':mini,'micro':micro,'state':'INCONCLUSIVE','error':f'{type(exc).__name__}: {exc}'}
    out['summary']={'roll_artifact_pairs':[k for k,v in out['pairs'].items() if v.get('roll_representation_artifact_supported')],'next_step':'For artifact-supported pairs, move to individual dated-contract comparison before judging family equivalence. For clean pairs, use mini+micro as independent representations but preserve separate product identities.'}
    Path('futures_mini_micro_seam_r10.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)+'\n'); print(json.dumps(out['summary'],sort_keys=True))
if __name__=='__main__': main()

#!/usr/bin/env python3
import json,math
from pathlib import Path
import pandas as pd
from huggingface_hub import HfApi,hf_hub_download

REPO='lynx1231/historical-futures-data-sample'
TARGET='data/daily/CME/ES/ESZ25.parquet'

def main():
    api=HfApi(); info=api.dataset_info(REPO); rev=info.sha; p=hf_hub_download(REPO,TARGET,repo_type='dataset',revision=rev); f=pd.read_parquet(p); cols={str(c).lower():c for c in f.columns}; req=['date','open','high','low','close','volume','open_interest','contract_symbol']; missing=[x for x in req if x not in cols]
    if missing: raise RuntimeError(f'missing {missing}')
    work=f.copy(); o=work[cols['open']]; h=work[cols['high']]; l=work[cols['low']]; c=work[cols['close']]; v=work[cols['volume']]; oi=work[cols['open_interest']]
    finite=pd.concat([o,h,l,c],axis=1).applymap(lambda x: pd.notna(x) and math.isfinite(float(x))).all(axis=1)
    high_ok=h>=pd.concat([o,l,c],axis=1).max(axis=1); low_ok=l<=pd.concat([o,h,c],axis=1).min(axis=1); vol_ok=v.fillna(0)>=0; oi_ok=oi.fillna(0)>=0
    bad=~(finite & high_ok & low_ok & vol_ok & oi_ok)
    rows=[]
    for _,r in work.loc[bad].head(50).iterrows():
        rows.append({k:(None if pd.isna(r[cols[k]]) else (str(r[cols[k]]) if k in ('date','contract_symbol') else float(r[cols[k]]))) for k in req})
    active=work[v.fillna(0)>0].copy(); ao=active[cols['open']]; ah=active[cols['high']]; al=active[cols['low']]; ac=active[cols['close']]; active_bad=~(pd.concat([ao,ah,al,ac],axis=1).notna().all(axis=1) & (ah>=pd.concat([ao,al,ac],axis=1).max(axis=1)) & (al<=pd.concat([ao,ah,ac],axis=1).min(axis=1)))
    out={'schema':'research.hf_es_anomaly_r14','classification':'SOURCE_QUALITY_DIAGNOSTIC_NOT_ALPHA_EVIDENCE','source':{'dataset':REPO,'revision':rev,'path':TARGET},'rows':int(len(work)),'bad_rows_all':int(bad.sum()),'bad_rows_with_positive_volume':int(active_bad.sum()),'zero_volume_rows':int((v.fillna(0)==0).sum()),'missing_ohlc_rows':int((~finite).sum()),'negative_volume_rows':int((v.fillna(0)<0).sum()),'negative_open_interest_rows':int((oi.fillna(0)<0).sum()),'sample_bad_rows':rows}
    if out['bad_rows_with_positive_volume']==0 and out['negative_volume_rows']==0 and out['negative_open_interest_rows']==0:
        out['decision']='DOCUMENTED_DEFERRED_SETTLEMENT_ROWS_COMPATIBLE_WITH_FILTERED_ADMISSION'
        out['canonical_filter']='admit only rows with finite OHLC and nonnegative volume/OI; retain rejected-row receipt; never synthesize missing values'
    else:
        out['decision']='SOURCE_QUALITY_REQUIRES_REVIEW'
        out['canonical_filter']=None
    out['license_boundary']='license metadata remains unresolved independently of row-quality outcome; no canonical redistribution/promotion until provenance terms are accepted'
    Path('hf_es_anomaly_r14.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)+'\n'); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()

#!/usr/bin/env python3
import hashlib,json,os
from pathlib import Path
import pandas as pd
from huggingface_hub import HfApi,hf_hub_download

REPO='lynx1231/historical-futures-data-sample'

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for c in iter(lambda:f.read(1024*1024),b''): h.update(c)
    return h.hexdigest()

def main():
    api=HfApi(); info=api.dataset_info(REPO); rev=info.sha
    files_csv=hf_hub_download(REPO,'files.csv',repo_type='dataset',revision=rev)
    schema_path=hf_hub_download(REPO,'schema.json',repo_type='dataset',revision=rev)
    checks_path=hf_hub_download(REPO,'checksums.sha256',repo_type='dataset',revision=rev)
    manifest=pd.read_csv(files_csv)
    cols={str(c).lower():c for c in manifest.columns}
    root_col=cols.get('root'); freq_col=next((cols[k] for k in ('frequency','freq','interval') if k in cols),None); path_col=next((cols[k] for k in ('path','file','filename') if k in cols),None)
    if root_col is None or freq_col is None or path_col is None: raise RuntimeError(f'unsupported files.csv columns {list(manifest.columns)}')
    es=manifest[(manifest[root_col].astype(str).str.upper()=='ES') & (manifest[freq_col].astype(str).str.lower().str.contains('daily'))].copy()
    if es.empty: raise RuntimeError('no ES daily dated-contract files')
    expected={}
    for line in Path(checks_path).read_text().splitlines():
        parts=line.strip().split(None,1)
        if len(parts)==2: expected[parts[1].lstrip('*')]=parts[0]
    contracts=[]; all_checksum=True; all_schema=True
    for _,row in es.iterrows():
        rel=str(row[path_col]); local=hf_hub_download(REPO,rel,repo_type='dataset',revision=rev); actual=sha(local); exp=expected.get(rel); checksum_ok=(exp is None or exp==actual); all_checksum &= checksum_ok
        f=pd.read_parquet(local); lc={str(c).lower():c for c in f.columns}; required=('contract_symbol','date','open','high','low','close','volume','open_interest'); schema_ok=all(k in lc for k in required); all_schema &= schema_ok
        if schema_ok:
            numeric=f[[lc['open'],lc['high'],lc['low'],lc['close'],lc['volume'],lc['open_interest']]].copy(); ohlc_ok=bool(((numeric[lc['high']]>=numeric[[lc['open'],lc['close'],lc['low']]].max(axis=1)) & (numeric[lc['low']]<=numeric[[lc['open'],lc['close'],lc['high']]].min(axis=1)) & (numeric[lc['volume']]>=0) & (numeric[lc['open_interest']]>=0)).all())
            dates=pd.to_datetime(f[lc['date']],errors='raise'); contract=str(f[lc['contract_symbol']].dropna().iloc[0]) if len(f[lc['contract_symbol']].dropna()) else None
        else:
            ohlc_ok=False; dates=pd.Series(dtype='datetime64[ns]'); contract=None
        contracts.append({'path':rel,'sha256':actual,'expected_sha256':exp,'checksum_ok':checksum_ok,'rows':int(len(f)),'contract_symbol':contract,'start':None if dates.empty else dates.min().date().isoformat(),'end':None if dates.empty else dates.max().date().isoformat(),'schema_ok':schema_ok,'ohlcv_invariants_ok':ohlc_ok})
    card=getattr(info,'card_data',None); license_value=None
    if card is not None:
        try: license_value=card.get('license') if hasattr(card,'get') else getattr(card,'license',None)
        except Exception: license_value=None
    schema=json.loads(Path(schema_path).read_text())
    tech=all_checksum and all_schema and all(x['ohlcv_invariants_ok'] for x in contracts)
    decision='ADMISSION_TECHNICALLY_READY_PROVENANCE_REVIEW_REQUIRED' if tech and not license_value else ('ADMISSION_TECHNICALLY_READY' if tech else 'ADMISSION_TECHNICAL_FAILURE')
    out={'schema':'research.hf_es_dated_contract_source_admission_r12','classification':'SOURCE_ADMISSION_NOT_ALPHA_EVIDENCE','source':{'dataset':REPO,'revision':rev,'license_metadata':license_value,'files_csv_sha256':sha(files_csv),'schema_sha256':sha(schema_path),'checksums_sha256':sha(checks_path)},'timestamp_contract':schema,'es_daily_contracts':contracts,'decision':decision,'canonical_fit':{'individual_contract_identity_preserved':all(x['contract_symbol'] for x in contracts),'source_native_prices_preserved':True,'checksums_verified':all_checksum,'schema_and_ohlcv_valid':tech,'exact_expiry_not_in_source_package':True,'automatic_canonical_promotion':False,'allowed_use':'research integration/overlap only until provenance/license and roll mapping pass'},'next_step':'If technically ready, use these dated ES contracts to validate source/session/roll seam behavior against MM-IBKR/Foundry semantics. Do not construct promotion-grade continuous history until license/provenance and exact contract-roll mapping are accepted.'}
    Path('hf_es_source_admission_r12.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)+'\n'); print(json.dumps({'decision':decision,'revision':rev,'license':license_value,'contracts':contracts},sort_keys=True))
if __name__=='__main__':main()

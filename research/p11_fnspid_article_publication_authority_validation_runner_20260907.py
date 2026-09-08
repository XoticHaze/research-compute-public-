from __future__ import annotations

import json

import p11_fnspid_article_publication_authority_validation_20260907 as batch

CANDIDATES=(
    'sabareesh88/FNSPID_nasdaq',
    'clarencecla/FNSPID',
    'sabareesh88/FNSPID_nasdaq_sorted',
)


def main():
    evidence=[]
    selected=None
    for dataset in CANDIDATES:
        try:
            valid=batch.get_json('/is-valid',{'dataset':dataset},retries=2)
            evidence.append({'dataset':dataset,'filter':valid.get('filter'),'validity':valid})
            if valid.get('filter') is True:
                selected=dataset
                break
        except Exception as exc:
            evidence.append({'dataset':dataset,'error':f'{type(exc).__name__}: {exc}'})
    if selected is None:
        raise RuntimeError('no previously proven/compatible FNSPID indexed mirror currently exposes filter support: '+json.dumps(evidence,sort_keys=True))
    batch.DATASET=selected
    print('P11_SELECTED_INDEXED_MIRROR='+selected)
    print('P11_INDEXED_MIRROR_CHALLENGE='+json.dumps(evidence,sort_keys=True))
    batch.main()

if __name__=='__main__':
    main()

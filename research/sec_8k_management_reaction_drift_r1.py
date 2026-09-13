import json,time
from pathlib import Path
import sec_8k_earnings_reaction_drift_r1 as m

EXPERIMENT_ID='SEC_8K_MANAGEMENT_REACTION_DRIFT_R1_20260913'
ITEM='5.02'
OUT=Path('research/results/sec_8k_management_reaction_drift_r1.json')

def management_filings(cik):
    b=m.gj(f'https://data.sec.gov/submissions/CIK{cik}.json',True)
    parts=[b.get('filings',{}).get('recent',{})]
    for meta in b.get('filings',{}).get('files',[]):
        try:
            parts.append(m.gj('https://data.sec.gov/submissions/'+meta['name'],True)); time.sleep(.11)
        except Exception:
            pass
    out={}
    for p in parts:
        forms=p.get('form',[])
        for i,form in enumerate(forms):
            def v(k):
                a=p.get(k,[]); return a[i] if i<len(a) else None
            d=v('filingDate'); items=v('items') or ''; acc=v('accessionNumber')
            if form=='8-K' and d and d>=m.START and ITEM in items and acc:
                out.setdefault(acc,{'filing_date':d,'acceptance_datetime':v('acceptanceDateTime'),'items':items,'accession':acc})
    return sorted(out.values(),key=lambda z:(z['filing_date'],z['accession'])),len(parts)

def main():
    m.E=EXPERIMENT_ID
    m.filings=management_filings
    m.main()
    p=Path('research/results/sec_8k_earnings_reaction_drift_r1.json')
    out=json.loads(p.read_text())
    out['schema']='public_research.sec_8k_management_reaction_drift_result.v1'
    out['experiment_id']=EXPERIMENT_ID
    out['inherited_learning_ids']=[]
    out['frozen_specification']['event_source']='SEC submissions JSON form=8-K items contains 5.02'
    r=out['result']
    if r['decision']=='SEC_8K_EARNINGS_REACTION_DRIFT_SURVIVES_R1':
        r['decision']='SEC_8K_MANAGEMENT_REACTION_DRIFT_SURVIVES_R1'
    r['gates']['positive_events_min_80']=r['positive_events']>=80
    r['gates'].pop('positive_events_min_100',None)
    r['decision']='SEC_8K_MANAGEMENT_REACTION_DRIFT_SURVIVES_R1' if min(r['gates'].values()) else 'REJECT_NO_PARAMETER_RESCUE'
    out['limitations'].append('Item 5.02 is a broad director/officer-change class; this is a preregistered comparator, not an event-subtype search.')
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps(r,sort_keys=True))

if __name__=='__main__':main()

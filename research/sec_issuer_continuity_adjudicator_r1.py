from __future__ import annotations
import json, urllib.request
from pathlib import Path

UA='XoticHaze market-research source-validation contact@example.com'
CURRENT_CIK='0002115436'
LEGACY_CIK='0000034088'

def get(url):
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'application/json'})
    return json.loads(urllib.request.urlopen(req,timeout=30).read().decode())

def summarize(cik):
    sub=get(f'https://data.sec.gov/submissions/CIK{cik}.json')
    facts=get(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json')
    rec=sub.get('filings',{}).get('recent',{})
    dates=[x for x in rec.get('filingDate',[]) if x]
    forms=rec.get('form',[])
    fact_dates=[]
    for concept in facts.get('facts',{}).get('us-gaap',{}).values():
        for vals in concept.get('units',{}).values():
            for v in vals:
                if v.get('filed'): fact_dates.append(v['filed'])
    return {
      'cik':cik,'submission_name':sub.get('name'),'tickers':sub.get('tickers',[]),'exchanges':sub.get('exchanges',[]),
      'former_names':sub.get('formerNames',[]),'recent_forms':forms[:20],
      'recent_filing_first':dates[0] if dates else None,'recent_filing_last':dates[-1] if dates else None,
      'companyfacts_entity_name':facts.get('entityName'),'companyfacts_first_filed':min(fact_dates) if fact_dates else None,
      'companyfacts_last_filed':max(fact_dates) if fact_dates else None,'companyfacts_filed_count':len(fact_dates)
    }

mapping=get('https://www.sec.gov/files/company_tickers.json')
xom=[v for v in mapping.values() if v.get('ticker','').upper()=='XOM']
current=summarize(CURRENT_CIK); legacy=summarize(LEGACY_CIK)
current_map_ciks=sorted({str(v['cik_str']).zfill(10) for v in xom})
legacy_has_long_history=bool(legacy['companyfacts_first_filed'] and legacy['companyfacts_first_filed']<'2012-01-01' and legacy['companyfacts_last_filed']>='2026-01-01')
new_is_recent=bool(current['companyfacts_first_filed'] and current['companyfacts_first_filed']>='2026-01-01')
both_xom=('XOM' in current['tickers'] and 'XOM' in legacy['tickers'])
continuity_issue=legacy_has_long_history and new_is_recent and both_xom and CURRENT_CIK in current_map_ciks
out={
 'schema':'research.sec_issuer_continuity_adjudicator_r1','workload_id':'SEC_ISSUER_CONTINUITY_ADJUDICATOR_R1','parent_context':'P287',
 'claim':'Determine whether P287 remaining XOM coverage failure is a current ticker-to-CIK corporate-identity continuity problem rather than absent SEC filed-at history, without substituting a hand-picked issuer for alpha evaluation.',
 'company_tickers_xom_rows':xom,'current_mapping_ciks':current_map_ciks,'current_mapped_entity':current,'legacy_long_history_entity':legacy,
 'tests':{'legacy_has_pre2012_through_2026_facts':legacy_has_long_history,'current_mapped_cik_is_2026_recent':new_is_recent,'both_submissions_report_XOM_ticker':both_xom,'current_company_tickers_contains_recent_cik':CURRENT_CIK in current_map_ciks},
 'decision':'SEC_XOM_CIK_CONTINUITY_PROBLEM_CONFIRMED' if continuity_issue else 'SEC_XOM_CIK_CONTINUITY_NOT_CONFIRMED',
 'decision_rule':'Confirm a source-identity continuity problem only if the legacy Exxon issuer CIK has SEC facts from before 2012 through 2026, the current mapped CIK begins only in 2026, both SEC submissions identify ticker XOM, and the current company_tickers mapping contains the recent CIK. Confirmation permits a lineage layer but not hand-selection of CIKs inside an alpha test.',
 'scientific_consequence':'If confirmed, preserve SEC companyfacts as a viable filed-at source but require deterministic corporate-action/issuer-lineage authority before any historical cross-sectional alpha inference. Do not drop XOM, union CIKs ad hoc, or use current ticker mapping as historical membership authority.',
 'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/sec_issuer_continuity_adjudicator_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))

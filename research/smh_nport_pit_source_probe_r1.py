import json
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

C=json.loads(Path('research/smh-nport-pit-source-probe-r1.json').read_text())
UA='XoticHazeResearch/1.0 public-scientific-source-probe'

def get(url):
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept-Encoding':'identity'})
    with urllib.request.urlopen(req,timeout=30) as r:return r.read()

def local(tag):return tag.rsplit('}',1)[-1]

def text_by_local(node,names):
    names=set(names)
    for e in node.iter():
        if local(e.tag) in names and e.text and e.text.strip():return e.text.strip()
    return None

rows=[]
for accession in C['known_accessions']:
    nodash=accession.replace('-','')
    url=f'https://www.sec.gov/Archives/edgar/data/{int(C["cik"])}/{nodash}/primary_doc.xml'
    try:
        raw=get(url); root=ET.fromstring(raw)
        series_ids=[(e.text or '').strip() for e in root.iter() if local(e.tag).lower() in {'seriesid','seriesid'}]
        rep=text_by_local(root,['repPd','reportDate','repPdDate'])
        holdings=[e for e in root.iter() if local(e.tag)=='invstOrSec']
        sample=[]; identified=0
        for h in holdings:
            name=text_by_local(h,['name']); cusip=text_by_local(h,['cusip']); ticker=text_by_local(h,['ticker'])
            if name or cusip or ticker: identified+=1
            if len(sample)<5: sample.append({'name':name,'cusip':cusip,'ticker':ticker})
        rows.append({'accession':accession,'url':url,'report_date':rep,'series_ids':series_ids,'series_match':C['series_id'] in series_ids,'holdings':len(holdings),'identified_holdings':identified,'sample':sample,'ok':True})
    except Exception as e:
        rows.append({'accession':accession,'url':url,'ok':False,'error':type(e).__name__+': '+str(e)[:180]})
    time.sleep(0.15)

success=[r for r in rows if r['ok']]
dates={r['report_date'] for r in success if r.get('report_date')}
series_ok=all(r.get('series_match') for r in success) if success else False
identity_ok=all(r.get('identified_holdings',0)>=C['gates']['min_holdings_per_snapshot'] for r in success) if success else False
holdings_ok=all(r.get('holdings',0)>=C['gates']['min_holdings_per_snapshot'] for r in success) if success else False
g=C['gates']
passed=len(success)>=g['min_successful_snapshots'] and len(dates)>=g['min_distinct_report_dates'] and holdings_ok and (series_ok if g['require_series_identity'] else True) and (identity_ok if g['require_security_identity'] else True)
out={'schema':'smh_nport_pit_source_probe_result.v1','experiment_id':C['experiment_id'],'successful_snapshots':len(success),'distinct_report_dates':len(dates),'series_identity_all_success':series_ok,'security_identity_all_success':identity_ok,'holdings_count_gate_all_success':holdings_ok,'passes_source_gate':passed,'rows':rows,'research_only':True}
Path('smh-nport-pit-source-probe-r1-result.json').write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))

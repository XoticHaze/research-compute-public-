import json,re,time,urllib.request
from pathlib import Path
C=json.loads(Path('research/smh-nport-relay-transport-r1.json').read_text())
UA='Mozilla/5.0 XoticHazeResearch/1.0'
rows=[]
for a in C['known_accessions']:
    url=C['relay'].format(accession=a)
    try:
        req=urllib.request.Request(url,headers={'User-Agent':UA})
        with urllib.request.urlopen(req,timeout=45) as r:text=r.read().decode('utf-8','replace')
        series=C['series_id'] in text
        cusips=re.findall(r'(?i)<cusip[^>]*>\s*([^<\s]{6,12})\s*</cusip>',text)
        tickers=re.findall(r'(?i)<ticker[^>]*>\s*([^<\s]{1,10})\s*</ticker>',text)
        names=re.findall(r'(?i)<name[^>]*>\s*([^<]{2,100})\s*</name>',text)
        rep=(re.findall(r'(?i)<repPd[^>]*>\s*([^<]+)\s*</repPd>',text) or re.findall(r'20\d\d-\d\d-\d\d',text))
        identity_count=max(len(cusips),len(tickers),len(names))
        rows.append({'accession':a,'relay_url':url,'ok':True,'bytes':len(text.encode()),'series_match':series,'report_date':rep[0] if rep else None,'cusip_count':len(cusips),'ticker_count':len(tickers),'name_count':len(names),'identity_count':identity_count,'sample_cusips':cusips[:5],'sample_tickers':tickers[:5]})
    except Exception as e:rows.append({'accession':a,'relay_url':url,'ok':False,'error':type(e).__name__+': '+str(e)[:180]})
    time.sleep(.1)
s=[r for r in rows if r['ok']]; sm=sum(r.get('series_match',False) for r in s); ids=sum(r.get('identity_count',0)>=10 for r in s); g=C['gates']; passed=len(s)>=g['min_successful_snapshots'] and sm>=g['min_series_matches'] and ids>=g['min_snapshots_with_10_security_ids']
out={'schema':'smh_nport_relay_transport_result.v1','experiment_id':C['experiment_id'],'successful_snapshots':len(s),'series_matches':sm,'snapshots_with_10_security_ids':ids,'passes_transport_gate':passed,'rows':rows,'research_only':True}
Path('smh-nport-relay-transport-r1-result.json').write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))

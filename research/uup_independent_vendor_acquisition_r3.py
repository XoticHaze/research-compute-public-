from __future__ import annotations
import json,re
from pathlib import Path
import requests

OUT=Path('research/results/uup_independent_vendor_acquisition_r3.json')
SOURCES={
 'stockinvest':'https://stockinvest.us/stock-price/UUP',
 'wsj':'https://www.wsj.com/market-data/quotes/etf/UUP/historical-prices',
 'totalrealreturns':'https://totalrealreturns.com/n/UUP',
}

def probe(name,url):
    try:
        r=requests.get(url,headers={'User-Agent':'Mozilla/5.0'},timeout=30)
        text=r.text
        years=sorted(set(int(x) for x in re.findall(r'\b(20(?:0[7-9]|1[0-9]|2[0-6]))\b',text)))
        return {'url':url,'status':r.status_code,'bytes':len(r.content),'years_visible':years,
                'has_2012':2012 in years,'has_2026':2026 in years,
                'content_type':r.headers.get('content-type','')}
    except Exception as e:
        return {'url':url,'error':type(e).__name__+': '+str(e)}

def main():
    rows={k:probe(k,v) for k,v in SOURCES.items()}
    usable=[k for k,v in rows.items() if v.get('status')==200 and v.get('has_2012') and v.get('has_2026')]
    result={'experiment':'UUP_INDEPENDENT_VENDOR_ACQUISITION_R3','requirement':'exact UUP history spanning 2012-2026 from non-Yahoo vendor; no proxy substitution','sources':rows,'coverage_candidates':usable,'decision':'INDEPENDENT_VENDOR_COVERAGE_CANDIDATE_FOUND' if usable else 'INDEPENDENT_VENDOR_DAILY_HISTORY_NOT_YET_ACQUIRED'}
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(result,indent=2,sort_keys=True))
    print(json.dumps(result,indent=2,sort_keys=True))
if __name__=='__main__': main()

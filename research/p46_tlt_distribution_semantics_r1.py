from __future__ import annotations
import json,re,hashlib,urllib.request
from html import unescape
from pathlib import Path

PAGE='https://www.ishares.com/us/products/239454/ishares-20-year-treasury-bond-etf'
DOC='https://www.blackrock.com/varnish-api/blk-one01-product-data/product-data/api/v1/get-fund-document?appSubType=ISHARES&appType=PRODUCT_PAGE&component=fundDownload&locale=en_US&portfolioId=239454&targetSite=us-ishares&userType=individual'

def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 CC-Market-Research/1.0','Accept':'text/html,application/xml,*/*'})
    with urllib.request.urlopen(req,timeout=60) as r:
        b=r.read(); return r.status,r.headers.get('Content-Type'),b

def clean(s): return re.sub(r'\s+',' ',unescape(re.sub(r'<[^>]+>',' ',s))).strip()

def main():
    ps,pc,pb=fetch(PAGE); text=pb.decode('utf-8','ignore'); low=text.lower()
    hrefs=[]
    for m in re.finditer(r'href=["\']([^"\']+)["\']',text,re.I):
        h=unescape(m.group(1))
        if any(k in h.lower() for k in ('dist','dividend','income','performance','calendar','yield')): hrefs.append(h)
    snippets=[]
    for term in ('total return','dividends','distributions','calendar year','growth of $10,000','growth of 10,000'):
        pos=0
        while True:
            i=low.find(term,pos)
            if i<0: break
            snippets.append({'term':term,'text':clean(text[max(0,i-350):i+len(term)+450])[:900]}); pos=i+len(term)
            if len([x for x in snippets if x['term']==term])>=8: break
    ds,dc,db=fetch(DOC)
    out={'schema':'research.p46_tlt_distribution_semantics_r1','parent':'P46','purpose':'materialize issuer-native TLT distribution/reinvestment semantics and candidate links before reconstruction','page':{'url':PAGE,'status':ps,'content_type':pc,'bytes':len(pb),'sha256':hashlib.sha256(pb).hexdigest(),'candidate_hrefs':sorted(set(hrefs))[:300],'semantic_snippets':snippets},'fund_document':{'url':DOC,'status':ds,'content_type':dc,'bytes':len(db),'sha256':hashlib.sha256(db).hexdigest()},'decision':'SEMANTIC_SURFACE_PROFILED'}
    Path('results').mkdir(exist_ok=True); Path('results/p46_tlt_distribution_semantics_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True))
    print(json.dumps({'decision':out['decision'],'candidate_href_count':len(set(hrefs)),'snippet_count':len(snippets),'page_status':ps,'document_status':ds},sort_keys=True))
if __name__=='__main__': main()

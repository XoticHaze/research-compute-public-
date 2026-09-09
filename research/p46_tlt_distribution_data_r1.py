from __future__ import annotations
import json,re,urllib.request
from html import unescape
from pathlib import Path

PAGE='https://www.ishares.com/us/products/239454/ishares-20-year-treasury-bond-etf'
TERMS=('exDate','recordDate','payableDate','paymentDate','totalDistribution','distributionAmount','distributionYield','distributionFrequency','distribution')

def fetch():
    req=urllib.request.Request(PAGE,headers={'User-Agent':'Mozilla/5.0 CC-Market-Research/1.0','Accept':'text/html,*/*'})
    with urllib.request.urlopen(req,timeout=60) as r: return r.read().decode('utf-8','ignore')

def norm(s): return re.sub(r'\s+',' ',unescape(s)).replace('\\"','"')

def main():
    text=fetch(); normalized=norm(text); low=normalized.lower(); contexts=[]
    for term in TERMS:
        pos=0; count=0
        while True:
            i=low.find(term.lower(),pos)
            if i<0: break
            contexts.append({'term':term,'context':normalized[max(0,i-500):i+len(term)+1000]})
            pos=i+len(term); count+=1
            if count>=25: break
    urls=sorted(set(unescape(m.group(0)) for m in re.finditer(r'https?://[^"\'<>\\ ]+',normalized) if any(k in m.group(0).lower() for k in ('dist','dividend','income','performance'))))
    out={'schema':'research.p46_tlt_distribution_data_r1','parent':'P46','purpose':'extract issuer-page distribution data/route contexts required for TLT total-return reconstruction','term_contexts':contexts,'candidate_urls':urls[:300],'decision':'TLT_DISTRIBUTION_DATA_CONTEXT_EXTRACTED' if contexts else 'TLT_DISTRIBUTION_DATA_CONTEXT_NOT_FOUND'}
    Path('results').mkdir(exist_ok=True); Path('results/p46_tlt_distribution_data_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True))
    print(json.dumps({'decision':out['decision'],'context_count':len(contexts),'url_count':len(urls)},sort_keys=True))
if __name__=='__main__': main()

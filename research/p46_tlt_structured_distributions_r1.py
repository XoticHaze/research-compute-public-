from __future__ import annotations
import json,re,urllib.request
from html import unescape
from pathlib import Path

PAGE='https://www.ishares.com/us/products/239454/ishares-20-year-treasury-bond-etf'

def fetch():
    req=urllib.request.Request(PAGE,headers={'User-Agent':'Mozilla/5.0 CC-Market-Research/1.0','Accept':'text/html,*/*'})
    with urllib.request.urlopen(req,timeout=60) as r: return r.read().decode('utf-8','ignore')

def decode_html(text):
    s=unescape(text)
    for _ in range(3): s=s.replace('\\"','"').replace('\\u0026','&').replace('\\/','/')
    return s

def parse_value(raw):
    try: return json.loads(raw)
    except Exception: return raw

def main():
    s=decode_html(fetch())
    fields={}
    pat=re.compile(r'"fullName":"performance\.distributions\.table\.([^".]+)".*?"formattedValue":(\[[^\]]*\]|"(?:\\.|[^"])*"|null)',re.S)
    for m in pat.finditer(s):
        name=m.group(1)
        if name not in fields: fields[name]=parse_value(m.group(2))
    perf={}
    p2=re.compile(r'"fullName":"performance\.([^".]+(?:\.[^".]+){0,4})".*?"formattedValue":(\[[^\]]*\]|"(?:\\.|[^"])*"|-?\d+(?:\.\d+)?|null)',re.S)
    for m in p2.finditer(s):
        name=m.group(1)
        if any(k in name.lower() for k in ('calendar','return','annual','discrete','nav')) and name not in perf:
            perf[name]=parse_value(m.group(2))
    out={'schema':'research.p46_tlt_structured_distributions_r1','parent':'P46','distribution_fields':fields,'performance_fields':perf,'decision':'TLT_STRUCTURED_DISTRIBUTIONS_EXTRACTED' if isinstance(fields.get('exDate'),list) and len(fields.get('exDate',[]))>0 else 'TLT_STRUCTURED_DISTRIBUTIONS_NOT_EXTRACTED'}
    Path('results').mkdir(exist_ok=True); Path('results/p46_tlt_structured_distributions_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True))
    print(json.dumps({'decision':out['decision'],'distribution_field_names':sorted(fields),'distribution_lengths':{k:len(v) for k,v in fields.items() if isinstance(v,list)},'performance_field_names':sorted(perf)},sort_keys=True))
if __name__=='__main__': main()

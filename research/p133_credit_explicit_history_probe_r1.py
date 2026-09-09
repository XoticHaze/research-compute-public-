from __future__ import annotations
import io,json,hashlib
from pathlib import Path
import pandas as pd,requests

def inspect(url):
    raw=requests.get(url,timeout=30).content
    x=pd.read_csv(io.BytesIO(raw)); x.columns=['date','oas']; x.date=pd.to_datetime(x.date,errors='coerce'); x.oas=pd.to_numeric(x.oas,errors='coerce'); x=x.dropna().sort_values('date')
    return {'rows':int(len(x)),'start':str(x.date.min().date()) if len(x) else None,'end':str(x.date.max().date()) if len(x) else None,'sha256':hashlib.sha256(raw).hexdigest()}

def main():
    base='https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2'
    explicit=base+'&cosd=1996-12-31&coed=2026-08-31'
    out={'schema':'research.p133_credit_explicit_history_probe_r1','parent':'P133','default':inspect(base),'explicit':inspect(explicit)}
    out['classification']='EXPLICIT_LONG_HISTORY_RECOVERED' if out['explicit']['rows']>3000 and out['explicit']['start'] and out['explicit']['start']<'2005-01-01' else 'EXPLICIT_HISTORY_NOT_RECOVERED'
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p133_credit_explicit_history_probe_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()

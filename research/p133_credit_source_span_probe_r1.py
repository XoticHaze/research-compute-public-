from __future__ import annotations
import io,json,hashlib
from pathlib import Path
import pandas as pd,requests,yfinance as yf

def main():
    url='https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2'
    raw=requests.get(url,timeout=30).content
    f=pd.read_csv(io.BytesIO(raw)); f.columns=['date','oas']; f.date=pd.to_datetime(f.date,errors='coerce'); f.oas=pd.to_numeric(f.oas,errors='coerce'); f=f.dropna().sort_values('date')
    px=yf.download(['SPY','TLT'],start='2002-01-01',auto_adjust=True,progress=False,threads=False)['Close'].dropna(how='all').astype(float)
    panel=px.dropna(subset=['SPY','TLT'])
    out={
      'schema':'research.p133_credit_source_span_probe_r1',
      'parent':'P133',
      'purpose':'Locate the chronology collapse without changing the frozen credit-spread model.',
      'fred':{'rows':int(len(f)),'start':str(f.date.min().date()) if len(f) else None,'end':str(f.date.max().date()) if len(f) else None,'sha256':hashlib.sha256(raw).hexdigest()},
      'prices':{'raw_rows':int(len(px)),'joint_rows':int(len(panel)),'start':str(panel.index.min().date()) if len(panel) else None,'end':str(panel.index.max().date()) if len(panel) else None,'columns':[str(x) for x in px.columns]},
      'monthly':{'joint_months':int(len(panel.resample('ME').last().dropna())),'start':str(panel.resample('ME').last().dropna().index.min().date()) if len(panel) else None,'end':str(panel.resample('ME').last().dropna().index.max().date()) if len(panel) else None}
    }
    out['classification']='LONG_SOURCE_AVAILABLE' if out['fred']['rows']>1000 and out['monthly']['joint_months']>120 else 'SOURCE_SCOPE_COLLAPSE_REPRODUCED'
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p133_credit_source_span_probe_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()

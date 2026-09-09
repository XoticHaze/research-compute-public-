import io,json,urllib.request
from pathlib import Path
import pandas as pd, openpyxl
from lxml import etree
U={'SPY':'https://www.ssga.com/library-content/products/fund-data/etfs/us/navhist-us-en-spy.xlsx','TLT':'https://www.blackrock.com/varnish-api/blk-one01-product-data/product-data/api/v1/get-fund-document?appSubType=ISHARES&appType=PRODUCT_PAGE&component=fundDownload&locale=en_US&portfolioId=239454&targetSite=us-ishares&userType=individual','GLD':'https://api.spdrgoldshares.com/api/v1/historical-archive?exchange=NYSE&lang=en&product=gld','QQQ':'https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/QQQ/navs?idType=ticker&productType=ETF','DBC':'https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/DBC/navs?idType=ticker&productType=ETF'}
def get(u):
 r=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0 CC-Market-Research/1.0'}); return urllib.request.urlopen(r,timeout=60).read()
def clean(d,n):
 x=pd.DataFrame({'date':d,'nav':n}); x.date=pd.to_datetime(x.date,errors='coerce'); x.nav=pd.to_numeric(x.nav,errors='coerce'); return x.dropna().drop_duplicates('date').sort_values('date').set_index('date')
def xrows(b,s):
 w=openpyxl.load_workbook(io.BytesIO(b),read_only=True,data_only=True)[s]; return [list(r) for r in w.iter_rows(values_only=True)]
def spy(b):
 r=xrows(b,'navhist'); i=next(i for i,x in enumerate(r) if x and x[0]=='Date'); h=list(r[i]); return clean([x[0] for x in r[i+1:]],[x[h.index('NAV')] for x in r[i+1:]])
def gld(b):
 r=xrows(b,'US GLD Historical Archive'); h=r[0]; return clean([x[0] for x in r[1:]],[x[h.index('NAV/Share at 10:30am NYT')] for x in r[1:]])
def inv(b):
 r=json.loads(b); return clean([x.get('effectiveDate') for x in r],[x.get('netAssetValue') for x in r])
def tlt(b):
 p=etree.XMLParser(recover=True,huge_tree=True); root=etree.fromstring(b,p); rows=[]
 for row in root.xpath('//*[local-name()="Row"]'):
  v=[]
  for c in row.xpath('./*[local-name()="Cell"]'):
   d=c.xpath('.//*[local-name()="Data"]'); v.append(d[0].text if d else None)
  rows.append(v)
 for i,r in enumerate(rows):
  h=[str(x).strip() if x else '' for x in r]
  if 'Date' in h and any('NAV' in x and 'Change' not in x for x in h):
   di=h.index('Date'); ni=next(j for j,x in enumerate(h) if 'NAV' in x and 'Change' not in x); return clean([x[di] if len(x)>di else None for x in rows[i+1:]],[x[ni] if len(x)>ni else None for x in rows[i+1:]]),{'header':h,'nav_col':h[ni],'recover_errors':len(p.error_log)}
 raise RuntimeError('TLT NAV header not found')
def main():
 b={k:get(v) for k,v in U.items()}; f={'SPY':spy(b['SPY']),'GLD':gld(b['GLD']),'QQQ':inv(b['QQQ']),'DBC':inv(b['DBC'])}; f['TLT'],tm=tlt(b['TLT']); cov={k:{'rows':len(v),'first':str(v.index.min().date()),'last':str(v.index.max().date())} for k,v in f.items()}; common=sorted(set.intersection(*(set(v.index) for v in f.values()))); d=pd.DataFrame(index=common); [d.__setitem__(k,v.reindex(d.index).nav) for k,v in f.items()]; d=d.dropna(); m=d.groupby(d.index.to_period('M')).last(); mr=m.pct_change().dropna(); out={'schema':'research.p46_five_issuer_nav_overlap_r1','parent':'P46','coverage':cov,'common_daily_rows':len(d),'common_first':str(d.index.min().date()),'common_last':str(d.index.max().date()),'monthly_rows':len(m),'monthly_return_rows':len(mr),'monthly_first':str(m.index.min()),'monthly_last':str(m.index.max()),'tlt':tm,'decision':'FIVE_ISSUER_NAV_OVERLAP_MATERIALIZED' if len(mr)>=100 else 'OVERLAP_INSUFFICIENT'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_five_issuer_nav_overlap_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); m.to_csv('artifacts/p46_five_issuer_nav_monthly_r1.csv'); mr.to_csv('artifacts/p46_five_issuer_nav_monthly_returns_r1.csv'); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()

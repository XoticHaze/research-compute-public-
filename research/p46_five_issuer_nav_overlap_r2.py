import io,json,urllib.request
from pathlib import Path
import pandas as pd,openpyxl
from lxml import etree
URL={'SPY':'https://www.ssga.com/library-content/products/fund-data/etfs/us/navhist-us-en-spy.xlsx','TLT':'https://www.blackrock.com/varnish-api/blk-one01-product-data/product-data/api/v1/get-fund-document?appSubType=ISHARES&appType=PRODUCT_PAGE&component=fundDownload&locale=en_US&portfolioId=239454&targetSite=us-ishares&userType=individual','GLD':'https://api.spdrgoldshares.com/api/v1/historical-archive?exchange=NYSE&lang=en&product=gld','QQQ':'https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/QQQ/navs?idType=ticker&productType=ETF','DBC':'https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/DBC/navs?idType=ticker&productType=ETF'}
def dl(u):return urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=60).read()
def frame(d,n):
 x=pd.DataFrame({'d':pd.to_datetime(d,errors='coerce'),'n':pd.to_numeric(n,errors='coerce')}).dropna().drop_duplicates('d');return x.sort_values('d').set_index('d')
def xr(b,s):return [list(x) for x in openpyxl.load_workbook(io.BytesIO(b),read_only=True,data_only=True)[s].iter_rows(values_only=True)]
def wb(b,s,date_col,nav_col,header=0):
 r=xr(b,s);h=list(r[header]);return frame([x[h.index(date_col)] for x in r[header+1:]],[x[h.index(nav_col)] for x in r[header+1:]])
def inv(b):
 r=json.loads(b);return frame([x['effectiveDate'] for x in r],[x['netAssetValue'] for x in r])
def tlt(b):
 p=etree.XMLParser(recover=True,huge_tree=True);root=etree.fromstring(b,p);rows=[]
 for row in root.xpath('//*[local-name()="Row"]'):
  vals=[]
  for c in row.xpath('./*[local-name()="Cell"]'):
   d=c.xpath('.//*[local-name()="Data"]');vals.append(d[0].text if d else None)
  rows.append(vals)
 i=next(i for i,r in enumerate(rows) if 'As Of' in r and 'NAV per Share' in r);h=rows[i];di=h.index('As Of');ni=h.index('NAV per Share');return frame([r[di] if len(r)>di else None for r in rows[i+1:]],[r[ni] if len(r)>ni else None for r in rows[i+1:]]),len(p.error_log)
def main():
 b={k:dl(v) for k,v in URL.items()};s=wb(b['SPY'],'navhist','Date','NAV',3);g=wb(b['GLD'],'US GLD Historical Archive','Date','NAV/Share at 10:30am NYT');q=inv(b['QQQ']);d=inv(b['DBC']);t,e=tlt(b['TLT']);f={'SPY':s,'TLT':t,'GLD':g,'QQQ':q,'DBC':d};idx=sorted(set.intersection(*(set(x.index) for x in f.values())));z=pd.DataFrame(index=idx);[z.__setitem__(k,v.reindex(idx).n) for k,v in f.items()];z=z.dropna();m=z.groupby(z.index.to_period('M')).last();r=m.pct_change().dropna();o={'schema':'research.p46_five_issuer_nav_overlap_r2','coverage':{k:{'rows':len(v),'first':str(v.index.min().date()),'last':str(v.index.max().date())} for k,v in f.items()},'common_daily_rows':len(z),'common_first':str(z.index.min().date()),'common_last':str(z.index.max().date()),'monthly_rows':len(m),'monthly_return_rows':len(r),'tlt_recovery_errors':e,'decision':'FIVE_ISSUER_NAV_OVERLAP_MATERIALIZED' if len(r)>=100 else 'OVERLAP_INSUFFICIENT'};Path('artifacts').mkdir(exist_ok=True);Path('artifacts/p46_five_issuer_nav_overlap_r2.json').write_text(json.dumps(o,indent=2,sort_keys=True));m.to_csv('artifacts/p46_five_issuer_nav_monthly_r2.csv');r.to_csv('artifacts/p46_five_issuer_nav_monthly_returns_r2.csv');print(json.dumps(o,sort_keys=True))
if __name__=='__main__':main()

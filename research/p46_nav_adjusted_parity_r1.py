import io,json,urllib.request
from pathlib import Path
import numpy as np,pandas as pd,openpyxl,yfinance as yf
from lxml import etree
S=('SPY','TLT','GLD','QQQ','DBC')
U={'SPY':'https://www.ssga.com/library-content/products/fund-data/etfs/us/navhist-us-en-spy.xlsx','TLT':'https://www.blackrock.com/varnish-api/blk-one01-product-data/product-data/api/v1/get-fund-document?appSubType=ISHARES&appType=PRODUCT_PAGE&component=fundDownload&locale=en_US&portfolioId=239454&targetSite=us-ishares&userType=individual','GLD':'https://api.spdrgoldshares.com/api/v1/historical-archive?exchange=NYSE&lang=en&product=gld','QQQ':'https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/QQQ/navs?idType=ticker&productType=ETF','DBC':'https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/DBC/navs?idType=ticker&productType=ETF'}
def dl(u):return urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=60).read()
def fr(d,n):
 x=pd.DataFrame({'d':pd.to_datetime(d,errors='coerce'),'n':pd.to_numeric(n,errors='coerce')}).dropna().drop_duplicates('d');return x.sort_values('d').set_index('d')
def xr(b,s):return [list(x) for x in openpyxl.load_workbook(io.BytesIO(b),read_only=True,data_only=True)[s].iter_rows(values_only=True)]
def wb(b,s,dc,nc,h=0):
 r=xr(b,s);z=list(r[h]);return fr([x[z.index(dc)] for x in r[h+1:]],[x[z.index(nc)] for x in r[h+1:]])
def inv(b):
 r=json.loads(b);return fr([x['effectiveDate'] for x in r],[x['netAssetValue'] for x in r])
def tlt(b):
 p=etree.XMLParser(recover=True,huge_tree=True);root=etree.fromstring(b,p);rows=[]
 for row in root.xpath('//*[local-name()="Row"]'):
  v=[]
  for c in row.xpath('./*[local-name()="Cell"]'):
   d=c.xpath('.//*[local-name()="Data"]');v.append(d[0].text if d else None)
  rows.append(v)
 i=next(i for i,r in enumerate(rows) if 'As Of' in r and 'NAV per Share' in r);h=rows[i];di=h.index('As Of');ni=h.index('NAV per Share');return fr([r[di] if len(r)>di else None for r in rows[i+1:]],[r[ni] if len(r)>ni else None for r in rows[i+1:]])
def nav():
 b={k:dl(v) for k,v in U.items()};f={'SPY':wb(b['SPY'],'navhist','Date','NAV',3),'TLT':tlt(b['TLT']),'GLD':wb(b['GLD'],'US GLD Historical Archive','Date','NAV/Share at 10:30am NYT'),'QQQ':inv(b['QQQ']),'DBC':inv(b['DBC'])};idx=sorted(set.intersection(*(set(x.index) for x in f.values())));z=pd.DataFrame(index=idx);[z.__setitem__(k,v.reindex(idx).n) for k,v in f.items()];return z.dropna().groupby(pd.DatetimeIndex(idx).to_period('M')).last().pct_change().dropna()
def main():
 n=nav(); y=yf.download(list(S),start='2016-07-01',auto_adjust=True,progress=False,threads=False)['Close'];y=y.resample('ME').last().pct_change();y.index=y.index.to_period('M');rows={}
 for s in S:
  a=pd.concat([n[s].rename('nav'),y[s].rename('adj')],axis=1).dropna();d=a.adj-a.nav;rows[s]={'months':len(a),'first':str(a.index.min()),'last':str(a.index.max()),'correlation':float(a.nav.corr(a.adj)),'mean_monthly_adj_minus_nav':float(d.mean()),'median_abs_monthly_diff':float(d.abs().median()),'max_abs_monthly_diff':float(d.abs().max()),'annualized_mean_drift':float(d.mean()*12),'nav_cumulative':float((1+a.nav).prod()-1),'adjusted_cumulative':float((1+a.adj).prod()-1),'cumulative_return_gap':float((1+a.adj).prod()-(1+a.nav).prod())}
 out={'schema':'research.p46_nav_adjusted_parity_r1','parent':'P46','contract':{'issuer_representation':'daily NAV resampled month-end','reference_representation':'Yahoo Finance auto_adjust Close','purpose':'measure representation drift before any P46 issuer-source replay','no_parameter_tuning':True},'assets':rows,'decision':'REPRESENTATION_PARITY_PROFILED'};Path('artifacts').mkdir(exist_ok=True);Path('artifacts/p46_nav_adjusted_parity_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True));print(json.dumps(rows,sort_keys=True))
if __name__=='__main__':main()

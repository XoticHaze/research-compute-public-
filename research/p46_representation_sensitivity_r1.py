from __future__ import annotations
import io,json,math,urllib.request
from pathlib import Path
import numpy as np,pandas as pd,openpyxl,yfinance as yf
from lxml import etree
S=('SPY','QQQ','TLT','GLD','DBC')
U={'SPY':'https://www.ssga.com/library-content/products/fund-data/etfs/us/navhist-us-en-spy.xlsx','TLT':'https://www.blackrock.com/varnish-api/blk-one01-product-data/product-data/api/v1/get-fund-document?appSubType=ISHARES&appType=PRODUCT_PAGE&component=fundDownload&locale=en_US&portfolioId=239454&targetSite=us-ishares&userType=individual','GLD':'https://api.spdrgoldshares.com/api/v1/historical-archive?exchange=NYSE&lang=en&product=gld','QQQ':'https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/QQQ/navs?idType=ticker&productType=ETF','DBC':'https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/DBC/navs?idType=ticker&productType=ETF'}
def dl(u):return urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=60).read()
def fr(d,n):
 x=pd.DataFrame({'d':pd.to_datetime(d,errors='coerce'),'v':pd.to_numeric(n,errors='coerce')}).dropna().drop_duplicates('d');return x.sort_values('d').set_index('d')
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
def nav_panel():
 b={k:dl(v) for k,v in U.items()};f={'SPY':wb(b['SPY'],'navhist','Date','NAV',3),'TLT':tlt(b['TLT']),'GLD':wb(b['GLD'],'US GLD Historical Archive','Date','NAV/Share at 10:30am NYT'),'QQQ':inv(b['QQQ']),'DBC':inv(b['DBC'])};idx=sorted(set.intersection(*(set(x.index) for x in f.values())));z=pd.DataFrame(index=idx);[z.__setitem__(k,v.reindex(idx).v) for k,v in f.items()];return z.dropna()[list(S)]
def yahoo_panel(start,end):
 y=yf.download(list(S),start=start,end=end+pd.Timedelta(days=2),auto_adjust=True,progress=False,threads=False)['Close'];return y[list(S)].dropna()
def features(close):
 m=close.resample('ME').last();r=close.pct_change(fill_method=None);maps={'mom6':m.pct_change(6),'trend200':(close/close.rolling(200,min_periods=160).mean()-1).resample('ME').last(),'low_vol6':-(r.rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last(),'drawdown6':(close/close.rolling(126,min_periods=100).max()-1).resample('ME').last()};out={}
 for dt in m.index:
  b=pd.DataFrame({k:v.loc[dt,list(S)] for k,v in maps.items()},index=list(S))
  if not b.isna().any().any():out[dt]=tuple(sorted(b.rank(axis=0,pct=True).mean(axis=1).sort_values(ascending=False).head(2).index))
 return out,m
def evaluate(close,bps):
 sel,m=features(close);prev={s:0 for s in S};recs=[]
 for dt,ch in sel.items():
  loc=m.index.get_loc(dt)
  if not isinstance(loc,(int,np.integer)) or loc+1>=len(m):continue
  nxt=m.index[loc+1];ret=m.loc[nxt,list(S)]/m.loc[dt,list(S)]-1
  if ret.isna().any():continue
  w={s:(.5 if s in ch else 0) for s in S};turn=.5*sum(abs(w[s]-prev[s]) for s in S);gross=sum(w[s]*float(ret[s]) for s in S);recs.append((nxt,gross-turn*bps/10000,float(ret.mean()),ch,turn));prev=w
 f=pd.DataFrame(recs,columns=['date','cand','ew','chosen','turn']).set_index('date');return f
def cagr(r):return float((1+r).prod()**(12/len(r))-1)
def folds(f):
 vals=[]
 for idx in np.array_split(np.arange(len(f)),5):vals.append(cagr(f.cand.iloc[idx])-cagr(f.ew.iloc[idx]))
 return sum(x>0 for x in vals),vals
def main():
 n=nav_panel();y=yahoo_panel(n.index.min(),n.index.max());common=n.index.intersection(y.index);n=n.reindex(common);y=y.reindex(common);out={'schema':'research.p46_representation_sensitivity_r1','parent':'P46','common_daily_rows':len(common),'window':[str(common.min().date()),str(common.max().date())],'selection':{},'costs':{}}
 ns,_=features(n);ys,_=features(y);months=sorted(set(ns)&set(ys));out['selection']={'months':len(months),'exact_match_months':sum(ns[x]==ys[x] for x in months),'exact_match_rate':sum(ns[x]==ys[x] for x in months)/len(months),'mean_set_overlap':float(np.mean([len(set(ns[x])&set(ys[x]))/2 for x in months])),'differing_months':[{'month':str(x.date()),'nav':list(ns[x]),'adjusted':list(ys[x])} for x in months if ns[x]!=ys[x]]}
 for bps in (25,50):
  a=evaluate(n,bps);b=evaluate(y,bps);idx=a.index.intersection(b.index);a=a.loc[idx];b=b.loc[idx];pa,pf=folds(a);pb,bf=folds(b);out['costs'][str(bps)]={'months':len(idx),'nav_excess_cagr':cagr(a.cand)-cagr(a.ew),'adjusted_excess_cagr':cagr(b.cand)-cagr(b.ew),'nav_candidate_cagr':cagr(a.cand),'adjusted_candidate_cagr':cagr(b.cand),'nav_positive_folds':pa,'adjusted_positive_folds':pb,'nav_folds':pf,'adjusted_folds':bf,'candidate_return_correlation':float(a.cand.corr(b.cand))}
 out['decision']='REPRESENTATION_SENSITIVITY_PROFILED';Path('artifacts').mkdir(exist_ok=True);Path('artifacts/p46_representation_sensitivity_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True));print(json.dumps({'selection':out['selection'],'costs':out['costs']},sort_keys=True))
if __name__=='__main__':main()

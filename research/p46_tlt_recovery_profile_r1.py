import json,urllib.request
from pathlib import Path
from lxml import etree
U='https://www.blackrock.com/varnish-api/blk-one01-product-data/product-data/api/v1/get-fund-document?appSubType=ISHARES&appType=PRODUCT_PAGE&component=fundDownload&locale=en_US&portfolioId=239454&targetSite=us-ishares&userType=individual'
def main():
 r=urllib.request.Request(U,headers={'User-Agent':'Mozilla/5.0 CC-Market-Research/1.0'}); b=urllib.request.urlopen(r,timeout=60).read(); p=etree.XMLParser(recover=True,huge_tree=True); root=etree.fromstring(b,p); rows=[]
 for row in root.xpath('//*[local-name()="Row"]'):
  vals=[]
  for c in row.xpath('./*[local-name()="Cell"]'):
   d=c.xpath('.//*[local-name()="Data"]'); vals.append(d[0].text if d else None)
  rows.append(vals)
 cand=[]
 for i,v in enumerate(rows):
  txt=' | '.join(str(x) for x in v if x is not None)
  if any(k in txt.lower() for k in ('date','nav','market price','close','asset value')): cand.append({'row':i,'values':v})
 out={'schema':'research.p46_tlt_recovery_profile_r1','parent':'P46','bytes':len(b),'recovery_error_count':len(p.error_log),'row_count':len(rows),'candidate_rows':cand[:80],'first_rows':rows[:30]}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_tlt_recovery_profile_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps({'bytes':len(b),'rows':len(rows),'errors':len(p.error_log),'candidate_rows':len(cand)},sort_keys=True))
if __name__=='__main__':main()

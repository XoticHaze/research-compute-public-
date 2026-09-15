from __future__ import annotations
import io,json,re
from pathlib import Path
import pandas as pd,requests,pdfplumber
from bs4 import BeautifulSoup
PDF="https://www.tsa.gov/sites/default/files/foia-readingroom/tsa-throughput-data-to-august-30-2026-to-september-5-2026.pdf"
PAGE="https://www.tsa.gov/travel/passenger-volumes"
UA={"User-Agent":"XoticHaze Research xotichaze@users.noreply.github.com"}
def main():
 s=requests.Session(); r=s.get(PDF,headers=UA,timeout=(20,120)); r.raise_for_status(); sums={}; current_date=None; rows=0
 with pdfplumber.open(io.BytesIO(r.content)) as pdf:
  for page in pdf.pages:
   for table in page.extract_tables() or []:
    for row in table:
     cells=[("" if x is None else str(x).replace("\n"," ").strip()) for x in row]
     joined=" | ".join(cells)
     m=re.search(r"\b(\d{1,2}/\d{1,2}/2026)\b",joined)
     if m: current_date=pd.to_datetime(m.group(1)).date().isoformat()
     if not current_date: continue
     nums=[]
     for cell in reversed(cells):
      z=re.sub(r"[^0-9]","",cell)
      if z and len(z)<=9: nums.append(int(z)); break
     if nums:
      # Exclude rows that are obviously headers/date/hour-only by requiring airport/checkpoint text.
      alpha=sum(ch.isalpha() for ch in joined)
      if alpha>=3:
       sums[current_date]=sums.get(current_date,0)+nums[0]; rows+=1
 p=s.get(PAGE,headers=UA,timeout=(15,60)); p.raise_for_status(); soup=BeautifulSoup(p.content,"html.parser"); published={}
 for tr in soup.select("table tbody tr"):
  c=[x.get_text(" ",strip=True) for x in tr.find_all(["td","th"])]
  if len(c)>=2:
   d=pd.to_datetime(c[0],errors="coerce"); n=pd.to_numeric(re.sub(r"[^0-9]","",c[1]),errors="coerce")
   if pd.notna(d) and pd.notna(n): published[pd.Timestamp(d).date().isoformat()]=int(n)
 comp=[]
 for d in sorted(set(sums)&set(published)):
  comp.append({"date":d,"pdf_sum":sums[d],"published":published[d],"diff":sums[d]-published[d]})
 out={"schema":"research.p569_tsa_pdf_daily_parity_r4","parent":"P07","child":"P569_TSA_PHYSICAL_DEMAND","pdf":PDF,"parsed_rows":rows,"pdf_daily":sums,"comparisons":comp,"exact_days":sum(x["diff"]==0 for x in comp),"compared_days":len(comp),"max_abs_diff":max([abs(x["diff"]) for x in comp],default=None),"decision":"PDF_DAILY_PARITY_SUPPORTED" if comp and all(x["diff"]==0 for x in comp) else "PDF_DAILY_PARSER_NOT_YET_ADMITTED","boundaries":{"alpha_claim":False,"portfolio_ranking":False,"allocation_authority":False,"runtime":False,"broker":False,"live_trading":False}}
 Path("artifacts").mkdir(exist_ok=True); Path("artifacts/p569_tsa_pdf_daily_parity_r4.json").write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps({k:out[k] for k in ("parsed_rows","compared_days","exact_days","max_abs_diff","decision")},sort_keys=True))
if __name__=="__main__":main()

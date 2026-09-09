from __future__ import annotations
import json,urllib.request,re
from pathlib import Path
from datetime import datetime,date
from lxml import etree

DOC='https://www.blackrock.com/varnish-api/blk-one01-product-data/product-data/api/v1/get-fund-document?appSubType=ISHARES&appType=PRODUCT_PAGE&component=fundDownload&locale=en_US&portfolioId=239454&targetSite=us-ishares&userType=individual'
TARGETS={2023:2.96,2024:-7.84,2025:4.17}
TOL=0.10

def fetch_doc():
    req=urllib.request.Request(DOC,headers={'User-Agent':'Mozilla/5.0 CC-Market-Research/1.0'})
    with urllib.request.urlopen(req,timeout=60) as r: return r.read()

def xml_rows(b):
    root=etree.fromstring(b,etree.XMLParser(recover=True,huge_tree=True)); out=[]
    for row in root.xpath('//*[local-name()="Row"]'):
        vals=[]
        for c in row.xpath('./*[local-name()="Cell"]'):
            ix=None
            for k,v in c.attrib.items():
                if k=='Index' or k.endswith('}Index'):
                    try: ix=int(v)-1
                    except ValueError: pass
                    break
            if ix is not None:
                while len(vals)<ix: vals.append(None)
            d=c.xpath('.//*[local-name()="Data"]'); vals.append(d[0].text if d else None)
        out.append(vals)
    return out

def parse_date(s):
    if s is None:return None
    s=str(s).strip()
    for f in ('%Y-%m-%dT%H:%M:%S.%f','%Y-%m-%dT%H:%M:%S','%Y-%m-%d','%b %d, %Y','%m/%d/%Y','%m/%d/%y'):
        try:return datetime.strptime(s,f).date()
        except ValueError: pass
    return None

def parse_float(s):
    if s is None:return None
    try:return float(re.sub(r'[^0-9eE+\-.]','',str(s)))
    except ValueError:return None

def load_nav():
    rows=xml_rows(fetch_doc()); best=None
    for i,row in enumerate(rows):
        cells=[str(x or '').strip().lower() for x in row]
        date_ix=[j for j,x in enumerate(cells) if x=='date' or 'as of' in x or x.endswith('date')]
        nav_ix=[j for j,x in enumerate(cells) if x=='nav' or ('nav' in x and ('share' in x or 'asset value' in x))]
        if date_ix and nav_ix:
            score=max((3 if cells[j]=='nav' else 2 if 'share' in cells[j] else 1,j) for j in nav_ix)
            cand=(score[0],i,date_ix[0],score[1],row)
            if best is None or cand[0]>best[0]: best=cand
    if best is None: raise RuntimeError('NAV/date header not found')
    _,hi,di,ni,header=best; nav={}; rejected=[]
    for row in rows[hi+1:]:
        if max(di,ni)>=len(row): continue
        d=parse_date(row[di]); v=parse_float(row[ni])
        if d and v is not None:
            if 20.0 <= v <= 300.0: nav[d]=v
            elif len(rejected)<30: rejected.append({'date':str(d),'raw_nav':row[ni],'parsed_nav':v})
    if len(nav)<500: raise RuntimeError(f'insufficient NAV rows {len(nav)} header={header!r}')
    return nav,{'header_row':hi,'date_col':di,'nav_col':ni,'header':header,'rows':len(nav),'first':str(min(nav)),'last':str(max(nav)),'rejected_implausible_samples':rejected,'sparse_cell_index_honored':True}

def last_on_or_before(nav,d):
    ks=[k for k in nav if k<=d]
    if not ks: raise KeyError(d)
    k=max(ks);return k,nav[k]

def main():
    structured=json.loads(Path('results/p46_tlt_structured_distributions_r1.json').read_text())
    f=structured['distribution_fields']; dates=f['exDate']; amounts=f['totalDistribution']; assert len(dates)==len(amounts)
    dist=[]
    for ds,a in zip(dates,amounts):
        d=parse_date(ds); v=parse_float(a)
        if d and v is not None: dist.append((d,v))
    nav,nav_meta=load_nav(); checks={}
    for y,target in TARGETS.items():
        sd,sv=last_on_or_before(nav,date(y-1,12,31)); ed,ev=last_on_or_before(nav,date(y,12,31)); shares=1.0; used=[]
        for d,amt in sorted((x for x in dist if x[0].year==y),key=lambda z:z[0]):
            nd,nv=last_on_or_before(nav,d); shares*=1.0+amt/nv; used.append({'ex_date':str(d),'nav_date':str(nd),'nav':nv,'distribution_per_share':amt})
        ret=100*(shares*ev/sv-1); err=abs(ret-target)
        checks[str(y)]={'start_nav_date':str(sd),'end_nav_date':str(ed),'start_nav':sv,'end_nav':ev,'distributions_used':used,'reconstructed_nav_total_return_pct':ret,'issuer_calendar_nav_total_return_pct':target,'abs_error_pp':err,'tolerance_pp':TOL,'pass':err<=TOL}
    decision='P46_TLT_ISSUER_TOTAL_RETURN_IDENTITY_VALIDATED' if all(v['pass'] for v in checks.values()) else 'P46_TLT_ISSUER_TOTAL_RETURN_IDENTITY_NOT_VALIDATED'
    out={'schema':'research.p46_tlt_totalreturn_identity_r1','parent':'P46','contract':{'years':sorted(TARGETS),'issuer_targets_from_prior_structured_extraction':TARGETS,'reinvest_total_distribution_on_ex_date_at_last_available_issuer_nav':True,'tolerance_pp':TOL,'no_model_parameter_or_cost_changes':True},'nav_materialization':nav_meta,'distribution_rows':len(dist),'checks':checks,'decision':decision}
    Path('results/p46_tlt_totalreturn_identity_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__':main()

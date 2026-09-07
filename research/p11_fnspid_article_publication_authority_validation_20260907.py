from __future__ import annotations

import json
import math
import re
import statistics
import time
from datetime import timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup
from dateutil import parser as dtparser

DATASET='sabareesh88/FNSPID_nasdaq'
CONFIG='default'
SPLIT='train'
BASE='https://datasets-server.huggingface.co'
SYMBOLS=('NVDA','AMD','AMAT','AVGO','MU','DHI','LEN','PHM','TOL','NVR')
QUANTILES=(0.10,0.50,0.90)
OUT=Path('p11_fnspid_article_publication_authority_validation_20260907.json')
MIN_AUTHORITATIVE_ROWS=12
MIN_AUTHORITATIVE_SYMBOLS=6
EARLY_TOLERANCE_MINUTES=5.0
INTRADAY_MEDIAN_MAX_MINUTES=60.0
INTRADAY_P95_MAX_MINUTES=1440.0


def get_json(path,params,retries=4):
    url=BASE+path+'?'+urlencode(params)
    last=None
    for attempt in range(retries):
        try:
            req=Request(url,headers={'User-Agent':'CommandCenter-P11-publication-validation/1.0'})
            with urlopen(req,timeout=60) as r: return json.loads(r.read())
        except Exception as exc:
            last=exc
            if attempt+1<retries: time.sleep(1.5*(attempt+1))
    raise RuntimeError(f'{path} failed: {type(last).__name__}: {last}')


def filtered(symbol,offset,length=1):
    return get_json('/filter',{'dataset':DATASET,'config':CONFIG,'split':SPLIT,'where':f'"Stock_symbol"=\'{symbol}\'','orderby':'"Date" ASC','offset':offset,'length':length})


def row_payload(node): return (node or {}).get('row',node or {})


def parse_ts(raw):
    if not raw: return None
    try:
        dt=dtparser.parse(str(raw))
    except Exception:
        return None
    if dt.tzinfo is None: return None
    return dt.astimezone(timezone.utc)


def walk_dates(obj,out):
    if isinstance(obj,dict):
        for k,v in obj.items():
            if str(k).lower()=='datepublished' and isinstance(v,(str,int,float)): out.append(('jsonld.datePublished',str(v)))
            else: walk_dates(v,out)
    elif isinstance(obj,list):
        for v in obj: walk_dates(v,out)


def extract_publication_metadata(html):
    soup=BeautifulSoup(html,'html.parser'); candidates=[]
    for meta in soup.find_all('meta'):
        key=(meta.get('property') or meta.get('name') or meta.get('itemprop') or '').strip().lower()
        if key in {'article:published_time','datepublished','pubdate','publishdate','date','parsely-pub-date'}:
            value=(meta.get('content') or '').strip()
            if value: candidates.append((f'meta.{key}',value))
    for script in soup.find_all('script',attrs={'type':re.compile(r'application/ld\+json',re.I)}):
        text=script.string or script.get_text() or ''
        try: obj=json.loads(text)
        except Exception: continue
        walk_dates(obj,candidates)
    parsed=[]
    for authority,raw in candidates:
        ts=parse_ts(raw)
        if ts is not None: parsed.append((authority,raw,ts))
    # Prefer explicit article semantics, then JSON-LD, then generic date metadata.
    priority={'meta.article:published_time':0,'jsonld.datePublished':1,'meta.datepublished':2,'meta.parsely-pub-date':3,'meta.pubdate':4,'meta.publishdate':5,'meta.date':6}
    parsed.sort(key=lambda x:(priority.get(x[0],99),x[2]))
    return parsed


def fetch_article(url,retries=2):
    last=None
    for attempt in range(retries):
        try:
            req=Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; CommandCenterResearch/1.0)','Accept':'text/html,application/xhtml+xml'})
            with urlopen(req,timeout=25) as r:
                ctype=(r.headers.get('content-type') or '').lower()
                if 'html' not in ctype: raise RuntimeError(f'non-html content-type={ctype}')
                raw=r.read(2_000_000)
                charset=r.headers.get_content_charset() or 'utf-8'
                return raw.decode(charset,errors='replace'),r.geturl()
        except Exception as exc:
            last=exc
            if attempt+1<retries: time.sleep(1.0)
    raise RuntimeError(f'{type(last).__name__}: {last}')


def percentile(values,p):
    if not values: return None
    vals=sorted(values); idx=(len(vals)-1)*p; lo=math.floor(idx); hi=math.ceil(idx)
    if lo==hi: return float(vals[lo])
    return float(vals[lo]*(hi-idx)+vals[hi]*(idx-lo))


def main():
    valid=get_json('/is-valid',{'dataset':DATASET})
    if valid.get('filter') is not True: raise RuntimeError('frozen FNSPID mirror no longer exposes indexed filter')
    samples=[]
    for symbol in SYMBOLS:
        first=filtered(symbol,0,1); total=first.get('num_rows_total',first.get('num_rows'))
        if total is None or int(total)<=0: raise RuntimeError(f'{symbol}: no indexed rows')
        n=int(total)
        offsets=[]
        for q in QUANTILES:
            offsets.append(max(0,min(n-1,int(round((n-1)*q)))))
        for q,offset in zip(QUANTILES,offsets):
            payload=filtered(symbol,offset,1); rows=payload.get('rows') or []
            if not rows: raise RuntimeError(f'{symbol}: no row at offset={offset}')
            r=row_payload(rows[0]); samples.append({'symbol':symbol,'quantile':q,'offset':offset,'indexed_rows':n,'fnspid_date_raw':r.get('Date'),'url':r.get('Url'),'publisher':r.get('Publisher'),'title':r.get('Article_title')})

    observations=[]; fetch_failures=[]; no_metadata=[]
    for sample in samples:
        url=(sample.get('url') or '').strip(); fn=parse_ts(sample.get('fnspid_date_raw'))
        base={k:v for k,v in sample.items() if k not in {'title'}}
        if fn is None:
            no_metadata.append({**base,'reason':'fnspid timestamp not offset-aware/parseable'}); continue
        if not url:
            no_metadata.append({**base,'reason':'missing article URL'}); continue
        try:
            html,final_url=fetch_article(url)
        except Exception as exc:
            fetch_failures.append({**base,'error':str(exc)}); continue
        candidates=extract_publication_metadata(html)
        if not candidates:
            no_metadata.append({**base,'final_url':final_url,'reason':'no explicit article publication metadata'}); continue
        authority,raw,publication=candidates[0]
        lag_minutes=(fn-publication).total_seconds()/60.0
        observations.append({**base,'final_url':final_url,'metadata_authority':authority,'publication_raw':raw,'publication_utc':publication.isoformat(),'fnspid_utc':fn.isoformat(),'fnspid_minus_publication_minutes':lag_minutes,'causal_safe_at_fnspid_time':lag_minutes>=-EARLY_TOLERANCE_MINUTES})

    lags=[x['fnspid_minus_publication_minutes'] for x in observations]
    auth_symbols=sorted({x['symbol'] for x in observations})
    unsafe=[x for x in observations if not x['causal_safe_at_fnspid_time']]
    sufficient=len(observations)>=MIN_AUTHORITATIVE_ROWS and len(auth_symbols)>=MIN_AUTHORITATIVE_SYMBOLS
    median=statistics.median(lags) if lags else None; p95=percentile(lags,0.95)
    if sufficient and not unsafe and median is not None and median<=INTRADAY_MEDIAN_MAX_MINUTES and p95 is not None and p95<=INTRADAY_P95_MAX_MINUTES:
        decision='FNSPID_INTRADAY_PUBLICATION_AUTHORITY_SUPPORTED'
        next_boundary='Execute the already-frozen PRICE_STATE_CONTROL / NEWS_ONLY / PRICE_PLUS_NEWS / PERMUTED_NEWS economic ablation using FNSPID Date as conservative availability time.'
    elif sufficient and not unsafe:
        decision='FNSPID_CAUSAL_BUT_INTRADAY_TIMELINESS_NOT_SUPPORTED'
        next_boundary='Retain for daily/descriptive causal research; do not run the frozen intraday ablation without a better publication-time source.'
    else:
        decision='FNSPID_PUBLICATION_AUTHORITY_HOLD_OR_ROTATE'
        next_boundary='Rotate P11 to a source with explicit point-in-time publication metadata, or obtain stronger authoritative article-level coverage before economic testing.'
    out={'schema':'public_research.p11_fnspid_article_publication_authority_validation.v1','research_only':True,'upstream_semantic_parent':'Zdong104/FNSPID_Financial_News_Dataset@4054842ec476953b30ee874d4b7e8eea786a21fa','upstream_pinned_object_sha256':'1a7a3eb8e6b97ec19f286f2cfca3371542bddb272ab1eb8f36e33ad98fa5c4da','indexed_transport_mirror':DATASET,'sample_rule':'For each of the 10 frozen Semiconductor/Homebuilder symbols, take Date-ascending indexed rows at 10%, 50%, and 90% of that symbol history. Rule frozen before article fetches.','sampled_rows':len(samples),'article_fetch_success_or_metadata_attempts':len(observations)+len(no_metadata),'authoritative_metadata_rows':len(observations),'authoritative_symbols':auth_symbols,'fetch_failures':fetch_failures,'no_authoritative_metadata':no_metadata,'observations':observations,'causality_gate':{'minimum_authoritative_rows':MIN_AUTHORITATIVE_ROWS,'minimum_authoritative_symbols':MIN_AUTHORITATIVE_SYMBOLS,'early_tolerance_minutes':EARLY_TOLERANCE_MINUTES,'unsafe_early_rows':len(unsafe),'median_fnspid_minus_publication_minutes':median,'p95_fnspid_minus_publication_minutes':p95,'decision':decision,'next_boundary':next_boundary},'publication_metadata_allowed':['JSON-LD datePublished','meta article:published_time','explicit publication-date meta fields'],'heuristic_page_dates_used':False,'economic_model_executed':False,'strategy_spec_mutation':False,'runtime_mutation':False,'promotion_authority':False,'broker_action':False,'live_trading_change':False}
    OUT.write_text(json.dumps(out,sort_keys=True,indent=2,allow_nan=False)+'\n'); print('P11_FNSPID_ARTICLE_PUBLICATION_AUTHORITY='+json.dumps(out,sort_keys=True,allow_nan=False))

if __name__=='__main__': main()

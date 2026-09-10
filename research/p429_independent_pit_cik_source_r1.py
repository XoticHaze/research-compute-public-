from __future__ import annotations
import csv, json, re, subprocess
from pathlib import Path
from datetime import datetime

SRC='https://github.com/riazarbi/sp500-scraper.git'
PIN='88556c3b823d61377551bcbdd396c509854180d6'
TARGETS=['2015-12-31','2020-12-31','2025-12-31']
MAX_LAG_DAYS=90
ART=Path('research/artifacts'); ART.mkdir(parents=True,exist_ok=True)
OUT=ART/'p429_independent_pit_cik_source_r1.json'
ROOT=Path('/tmp/sp500-scraper-p429')

def run(*a): return subprocess.check_output(a,text=True,stderr=subprocess.STDOUT)
if ROOT.exists(): subprocess.run(['rm','-rf',str(ROOT)],check=True)
subprocess.run(['git','clone','--filter=blob:none','--no-checkout',SRC,str(ROOT)],check=True)
subprocess.run(['git','-C',str(ROOT),'checkout','--detach',PIN],check=True)
observed=run('git','-C',str(ROOT),'rev-parse','HEAD').strip()
if observed!=PIN: raise SystemExit('PIN_MISMATCH')
objs=run('git','-C',str(ROOT),'rev-list','--objects','--all')
paths=[]
for line in objs.splitlines():
    p=line.split(' ',1)[1] if ' ' in line else ''
    m=re.fullmatch(r'wikipedia/sp500/csv/(\d{8})\.csv',p)
    if m: paths.append((datetime.strptime(m.group(1),'%Y%m%d').date(),p))
paths=sorted(set(paths))

def pick(target):
    t=datetime.fromisoformat(target).date(); eligible=[x for x in paths if x[0]<=t]
    if not eligible:return None
    d,p=max(eligible); lag=(t-d).days
    return None if lag>MAX_LAG_DAYS else (d,p,lag)

def load_historical(path):
    commits=run('git','-C',str(ROOT),'log','--all','--diff-filter=A','--format=%H','--',path).splitlines()
    for h in commits:
        try:
            txt=run('git','-C',str(ROOT),'show',f'{h}:{path}')
            if txt.strip(): return h,txt
        except subprocess.CalledProcessError: pass
    # Fallback: find any reachable commit whose tree contains the path.
    commits=run('git','-C',str(ROOT),'rev-list','--all','--',path).splitlines()
    for h in commits:
        try:
            txt=run('git','-C',str(ROOT),'show',f'{h}:{path}')
            if txt.strip(): return h,txt
        except subprocess.CalledProcessError: pass
    return None,None

def analyze(target):
    sel=pick(target)
    if not sel:return {'target':target,'snapshot_found':False}
    d,p,lag=sel; h,txt=load_historical(p)
    if not txt:return {'target':target,'snapshot_found':False,'selected_path':p,'selected_date':str(d),'lag_days':lag,'historical_blob_unreadable':True}
    rows=list(csv.DictReader(txt.splitlines()))
    cols=list(rows[0]) if rows else []
    norm={c:re.sub(r'[^a-z0-9]','',c.lower()) for c in cols}
    cik_cols=[c for c,n in norm.items() if n=='cik' or n.endswith('cik')]
    sym_cols=[c for c,n in norm.items() if n in ('symbol','ticker','tickersymbol')]
    cik_col=cik_cols[0] if cik_cols else None; sym_col=sym_cols[0] if sym_cols else None
    n=len(rows)
    ciks=[str(r.get(cik_col,'')).strip() for r in rows] if cik_col else []
    syms=[str(r.get(sym_col,'')).strip().upper() for r in rows] if sym_col else []
    cik_present=[x for x in ciks if x and x.lower() not in ('na','nan','none')]
    sym_present=[x for x in syms if x and x.lower() not in ('na','nan','none')]
    pair_present=[(s,c) for s,c in zip(syms,ciks) if s and c and c.lower() not in ('na','nan','none')]
    symbol_conflicts=0
    by={}
    for s,c in pair_present: by.setdefault(s,set()).add(c)
    symbol_conflicts=sum(len(v)>1 for v in by.values())
    return {'target':target,'snapshot_found':True,'selected_date':str(d),'lag_days':lag,'selected_path':p,'source_commit_containing_blob':h,'rows':n,'columns':cols,'cik_column':cik_col,'symbol_column':sym_col,'cik_coverage':len(cik_present)/n if n else 0,'symbol_coverage':len(sym_present)/n if n else 0,'symbol_unique_fraction':len(set(sym_present))/len(sym_present) if sym_present else 0,'symbols_with_multiple_ciks_within_snapshot':symbol_conflicts,'cik_values_numeric_fraction':sum(x.isdigit() for x in cik_present)/len(cik_present) if cik_present else 0}

snaps=[analyze(t) for t in TARGETS]
passed=all(s.get('snapshot_found') and 450<=s.get('rows',0)<=550 and s.get('cik_coverage',0)>=.95 and s.get('symbol_coverage',0)>=.99 and s.get('symbol_unique_fraction',0)>=.99 and s.get('symbols_with_multiple_ciks_within_snapshot',1)==0 and s.get('cik_values_numeric_fraction',0)>=.99 for s in snaps)
out={'schema':'research.p429_independent_pit_cik_source_r1.v1','workload_id':'P429_INDEPENDENT_PIT_CIK_SOURCE_R1','parent':'POINT_IN_TIME_FUNDAMENTAL_SELECTION','source':{'repository':SRC,'pinned_commit':PIN,'readme_scope':'Independent historical S&P 500 constituent snapshots; this audit uses only Wikipedia snapshot files reachable from the pin.'},'claim':'A genuinely independent historical constituent source can provide high-coverage symbol-to-CIK identity for a new, explicitly narrower post-2014 causal research scope. This does not rescue or overwrite P408 deeper-history failure.','targets':TARGETS,'snapshot_selection_rule':'For each fixed target, choose the latest reachable wikipedia/sp500/csv YYYYMMDD snapshot on or before the target, with maximum lag 90 calendar days, using filenames before inspecting row data.','snapshots':snaps,'decision_rule':'POST2014_JOIN_SOURCE_READY only if every target has a <=90-day-lag snapshot, 450-550 rows, >=95% CIK coverage, >=99% symbol coverage and uniqueness, zero within-snapshot symbol-to-multiple-CIK conflicts, and >=99% numeric CIK values.','decision':'POST2014_INDEPENDENT_CIK_SOURCE_READY' if passed else 'POST2014_INDEPENDENT_CIK_SOURCE_NOT_READY','scientific_consequence':('The independent source is admissible for a new post-2014 PIT membership/CIK join adjudicator; P408 remains failed for deeper history and no alpha may run until cross-source join coverage passes.' if passed else 'Keep the fundamental alpha chain blocked; this source does not satisfy the new post-2014 identity sufficiency gate. Do not drop unresolved constituents or use current membership to fill gaps.'),'boundaries':{'data_representation_only':True,'alpha_inference':False,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'snapshots':[{'target':s['target'],'date':s.get('selected_date'),'rows':s.get('rows'),'cik_coverage':round(s.get('cik_coverage',0),4),'symbol_coverage':round(s.get('symbol_coverage',0),4),'lag':s.get('lag_days')} for s in snaps]},sort_keys=True))

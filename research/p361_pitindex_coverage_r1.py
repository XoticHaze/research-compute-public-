from __future__ import annotations
import json, subprocess, sys
from pathlib import Path

PIN='2df030e5c9be7c83cf4b28c3d8597d74d274757e'
subprocess.check_call([sys.executable,'-m','pip','install','--disable-pip-version-check',f'git+https://github.com/arielNacamulli/pitindex.git@{PIN}'])
import pitindex

DATES=['2006-01-03','2010-01-04','2015-01-02','2020-01-02','2024-01-02','2026-09-01']
rows=[]
for date in DATES:
    df=pitindex.get_constituents(date,index='sp500')
    n=len(df)
    cik=int(df['cik'].notna().sum()) if 'cik' in df else 0
    sec=int(df['gics_sector'].notna().sum()) if 'gics_sector' in df else 0
    sub=int(df['gics_sub_industry'].notna().sum()) if 'gics_sub_industry' in df else 0
    rows.append({'date':date,'members':n,'cik_coverage':cik,'cik_fraction':cik/n if n else 0,'sector_coverage':sec,'sector_fraction':sec/n if n else 0,'subindustry_coverage':sub,'subindustry_fraction':sub/n if n else 0})

# For a fundamental PIT research universe, CIK coverage is the gating field. Exact sector history is not claimed by this source.
pre2020=[r for r in rows if r['date']<'2020-01-01']
min_cik=min(r['cik_fraction'] for r in rows)
min_old=min(r['cik_fraction'] for r in pre2020)
if min_old>=0.95:
    decision='P361_PIT_MEMBERSHIP_CIK_COVERAGE_SUFFICIENT_FOR_SEC_CORPUS_PILOT'
elif min_old>=0.80:
    decision='P361_PIT_MEMBERSHIP_CIK_COVERAGE_PARTIAL_REQUIRES_EXPLICIT_UNIVERSE_COVERAGE_GATE'
else:
    decision='P361_PIT_MEMBERSHIP_CIK_COVERAGE_INSUFFICIENT_FOR_UNBIASED_SEC_CORPUS'
res={'schema':'research.p361_pitindex_coverage_r1','parent':'CONSTITUENT_LEVEL_CROSS_SECTIONAL_FUNDAMENTALS','source':{'repo':'arielNacamulli/pitindex','commit':PIN,'index':'sp500'},'claim':'Quantify whether a pinned free point-in-time membership source carries enough CIK identity across fixed historical snapshots to support a future SEC filing-date fundamental corpus without silently dropping historical members. This is corpus evidence, not alpha.','snapshots':rows,'min_cik_fraction_all':min_cik,'min_cik_fraction_pre2020':min_old,'decision':decision,'scientific_consequence':'Use the observed CIK coverage as a hard universe-admission bound. Missing CIK rows must be explicit exclusions in any SEC-based factor test; they may not be backfilled with current membership or silently dropped. Sector fields are descriptive only and are not admitted as exact historical classification.','next_executable':'Only if the CIK coverage gate is adequate, materialize a small independently hashed SEC filing-date corpus on fixed PIT snapshots, report per-date statement coverage, and test a predeclared non-sector-neutral profitability/value ranking against PIT equal-weight and SPY controls.','boundaries':{'scientific_authority':True,'alpha_result':False,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True)
Path('research/artifacts/p361_pitindex_coverage_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True))
print(json.dumps(res,sort_keys=True))

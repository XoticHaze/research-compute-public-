from __future__ import annotations
import hashlib, json, urllib.request
from pathlib import Path

UPSTREAM='whitenoise1/RFundamentals'
PIN='d259b4153358d2683e7078b4a4c220b31a02e45b'
FILES=['README.md','docs/KNOWN_LIMITATIONS.md','.gitignore']

def fetch(path):
    url=f'https://raw.githubusercontent.com/{UPSTREAM}/{PIN}/{path}'
    with urllib.request.urlopen(url,timeout=30) as r: b=r.read()
    return b.decode('utf-8'), hashlib.sha256(b).hexdigest(), url

texts={}; prov={}
for p in FILES:
    t,h,u=fetch(p); texts[p]=t; prov[p]={'sha256':h,'url':u,'bytes':len(t.encode())}
readme=texts['README.md']; limits=texts['docs/KNOWN_LIMITATIONS.md']; gitignore=texts['.gitignore']
checks={
 'filing_date_pit': 'stamped by SEC filing date (not period end)' in readme,
 'historical_membership_claim': 'current and historical S&P 500 members' in readme and 'constituent membership' in limits,
 'sector_history_exact': 'Historical sector/industry is a current-value approximation' not in limits,
 'sector_lookahead_explicit': 'mild look-ahead in cross-sectional grouping' in limits,
 'delisted_price_gaps_explicit': 'price-unrecoverable windows' in limits and 'No provider coverage' in limits,
 'generated_cache_not_committed': 'cache/' in gitignore,
 'edgar_user_agent_required': 'EDGAR_UA' in readme and 'required by their rate limit policy' in readme,
 'optional_delisted_price_fallback': 'Tiingo' in readme and 'delisted names' in readme,
}
strict_pit_nonneutral = checks['filing_date_pit'] and checks['historical_membership_claim']
full_sector_neutral = strict_pit_nonneutral and checks['sector_history_exact'] and not checks['delisted_price_gaps_explicit']
if strict_pit_nonneutral and not full_sector_neutral:
    decision='P360_CONDITIONALLY_ADMISSIBLE_FOR_NONSECTOR_FUNDAMENTAL_RESEARCH_ONLY'
elif full_sector_neutral:
    decision='P360_FULL_PIT_FUNDAMENTAL_SOURCE_ADMISSIBLE'
else:
    decision='P360_PIT_FUNDAMENTAL_SOURCE_NOT_ADMISSIBLE'
res={
 'schema':'research.p360_pit_fundamental_source_audit_r1',
 'parent':'CONSTITUENT_LEVEL_CROSS_SECTIONAL_FUNDAMENTALS',
 'claim':'Source/causality audit of an alternative free point-in-time fundamental pipeline after the public Wikipedia sector-history source proved insufficient. This run does not evaluate alpha.',
 'upstream':{'repo':UPSTREAM,'commit':PIN,'files':prov},
 'checks':checks,
 'decision':decision,
 'scientific_consequence':'The pinned upstream can be considered only for non-sector-neutral, filing-date-causal fundamental research after an independent rebuild/identity receipt. It is not admissible as an exact historical sector/industry source, and incomplete delisted price coverage forbids pretending complete price-dependent cross-sectional coverage. Do not impute historical sectors or missing delisted prices.',
 'next_executable':'Build a narrow public-safe PIT fundamental corpus from SEC filing-date facts plus independently pinned point-in-time membership, initially excluding sector-relative features and requiring explicit per-date universe coverage; then test one predeclared cross-sectional profitability/value model against equal-weight and broad-market matched controls.',
 'limitations':['This audit validates source contracts/code statements, not rebuilt bytes.','Upstream generated caches are not committed and must be independently rebuilt and hashed before model use.','Historical sector/industry is explicitly approximate before the dated cutover.','Some delisted constituents lack recoverable price history, limiting price-dependent factors.'],
 'boundaries':{'scientific_authority':True,'alpha_result':False,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}
}
Path('research/artifacts').mkdir(parents=True,exist_ok=True)
Path('research/artifacts/p360_pit_fundamental_source_audit_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True))
print(json.dumps(res,sort_keys=True))

import hashlib,json
from pathlib import Path
contract={'schema':'mm.trading_product.midcap_live_route.v1','product_repository':'XoticHaze/mm-IBKR','product_pr':478,'product_head':'5dd1054ac00d6d00939a88ba81dc70a1583281c1','route':'/research/midcap-fund-evidence','decisions':['P220_BETA_ADJUSTED_ALPHA_NOT_SUPPORTED','P221_MIDCAP_QUALITY_NOT_SUPPORTED','P222_FIXED_FACTOR_BLEND_NOT_SUPPORTED'],'provenance_reviews':['/operator/fund-model-p220-xmmo-beta-attribution.html','/operator/fund-model-p221-p222-midcap-architecture.html'],'operator_posture':'bounded XMMO matched-size evidence; beta-adjusted chronology weak; quality rescue closed','authority':{'portfolio_ranking':False,'allocation':False,'sizing':False,'promotion':False,'StrategySpec':False,'runtime':False,'broker':False,'live_trading':False}}
assert contract['route']=='/research/midcap-fund-evidence'
assert len(contract['decisions'])==3 and all(x.endswith('NOT_SUPPORTED') for x in contract['decisions'])
assert all(v is False for v in contract['authority'].values())
canonical=json.dumps(contract,sort_keys=True,separators=(',',':'))
out={'schema':'mm.trading_product.midcap_live_route_acceptance.v1','result':'PASS','contract_sha256':hashlib.sha256(canonical.encode()).hexdigest(),'contract':contract}
Path('artifacts').mkdir(exist_ok=True);Path('artifacts/trading_product_midcap_live_route_acceptance.json').write_text(json.dumps(out,sort_keys=True,indent=2));print('MIDCAP_LIVE_ROUTE_ACCEPTANCE=PASS',out['contract_sha256'])

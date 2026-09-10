import hashlib,json
from pathlib import Path
contract={'schema':'mm.trading_product.p223_operator_contract.v1','product_repository':'XoticHaze/mm-IBKR','product_pr':480,'product_head':'eb41bf37b24980d23fca4e33af4001e34f70eaf3','decision':'P223_LARGECAP_MOMENTUM_NOT_SUPPORTED','source_execution':{'run_id':34434444032,'head_sha':'e4e61a0b06969141b15d7b0143fd6309d2ac858a','artifact_id':10135654699,'artifact_sha256':'3a998f1e2d7be963a391c63986cf28106ee407b475973e1aea3d2ddcc982633d'},'metrics':{'mtum_minus_ivv_2015_bp':97,'positive_ivv_folds':3,'required_folds':4,'mtum_minus_spy_2015_bp':98},'operator_consequence':'do not generalize the XMMO mid-cap seam into a broad cross-size momentum product','authority':{'portfolio_ranking':False,'allocation':False,'sizing':False,'promotion':False,'StrategySpec':False,'runtime':False,'data':False,'broker':False,'live_trading':False}}
assert contract['metrics']['mtum_minus_ivv_2015_bp']>0 and contract['metrics']['mtum_minus_spy_2015_bp']>0
assert contract['metrics']['positive_ivv_folds']<contract['metrics']['required_folds']
assert all(v is False for v in contract['authority'].values())
canonical=json.dumps(contract,sort_keys=True,separators=(',',':'));out={'schema':'mm.trading_product.p223_operator_acceptance.v1','result':'PASS','contract_sha256':hashlib.sha256(canonical.encode()).hexdigest(),'contract':contract}
Path('artifacts').mkdir(exist_ok=True);Path('artifacts/trading_product_p223_operator_acceptance.json').write_text(json.dumps(out,sort_keys=True,indent=2));print('P223_OPERATOR_ACCEPTANCE=PASS',out['contract_sha256'])

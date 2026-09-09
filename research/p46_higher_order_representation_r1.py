from __future__ import annotations
import itertools, json
from pathlib import Path
import p46_single_sleeve_representation_r1 as one

ORIGINAL = one.ORIGINAL
SUBS = one.SUBS
ANCHOR = ('TLT', 'DBC')
THIRDS = tuple(s for s in ORIGINAL if s not in ANCHOR)
BP = 50


def main():
    tests = {}
    for third in THIRDS:
        replaced = set(ANCHOR + (third,))
        symbols = [SUBS[s] if s in replaced else s for s in ORIGINAL]
        name = '__'.join(f'{s}_to_{SUBS[s]}' for s in ANCHOR + (third,))
        tests[name] = one.evaluate(symbols)
    supported = {k: (v['excess_cagr'] > 0 and v['positive_folds'] >= 3) for k, v in tests.items()}
    out = {
        'schema': 'research.p46_higher_order_representation_r1',
        'parent': 'P46',
        'hypothesis': 'The localized TLT->IEF plus DBC->PDBC pairwise failure may be a specific bond/commodity interaction. Test the smallest higher-order extensions by adding exactly one predeclared third proxy substitution at a time, without choosing survivors ex post.',
        'scientific_contract': {
            'original_representation': list(ORIGINAL),
            'substitutions': SUBS,
            'fixed_failed_pair': list(ANCHOR),
            'predeclared_third_substitutions': list(THIRDS),
            'cost_bps': BP,
            'top_k': 2,
            'factors': ['mom6', 'trend200', 'low_vol6', 'drawdown6'],
            'matched_control': 'same-universe equal weight over identical months for each triple',
            'chronological_folds': 5,
            'support_per_triple': 'positive excess CAGR and >=3/5 positive chronological folds',
            'no_proxy_selection_or_parameter_tuning': True,
        },
        'tests': tests,
        'supported_triples': supported,
        'supported_triple_count': int(sum(supported.values())),
        'decision': 'P46_BOND_COMMODITY_INTERACTION_LOCALIZED' if sum(supported.values()) >= 2 else 'P46_HIGHER_ORDER_REPRESENTATION_FRAGILE',
        'interpretation_rule': 'This adjudicates interaction structure only. Preserve prior original-representation evidence regardless of outcome and do not select a preferred triple ex post.'
    }
    Path('artifacts').mkdir(exist_ok=True)
    Path('artifacts/p46_higher_order_representation_r1.json').write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False))
    print(json.dumps(out, sort_keys=True))


if __name__ == '__main__':
    main()

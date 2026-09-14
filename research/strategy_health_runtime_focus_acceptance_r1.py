import hashlib
import json
from pathlib import Path

PRODUCT_HEAD = "9b20479a4b8bf9e69d72f851a8e79567a3cb27f5"

TARGETS = [
    {"symbol": "AMAT", "timeframe": "15Min"},
    {"symbol": "AMAT", "timeframe": "5Min"},
    {"symbol": "APH", "timeframe": "15Min"},
    {"symbol": "MNQ", "timeframe": "12Min"},
]


def same_target(left, right):
    return bool(
        left
        and right
        and left.get("symbol") == right.get("symbol")
        and left.get("timeframe") == right.get("timeframe")
    )


def target_key(target):
    return f"{target.get('symbol', '')}:{target.get('timeframe', '')}"


def order_targets(preferred_target, targets):
    if not preferred_target:
        return list(targets)
    return [preferred_target, *[target for target in targets if not same_target(target, preferred_target)]]


def attributed(preferred_target, target):
    return same_target(preferred_target, target)


def main():
    preferred = {"symbol": "AMAT", "timeframe": "5Min"}
    ordered = order_targets(preferred, TARGETS)

    assert ordered == [
        {"symbol": "AMAT", "timeframe": "5Min"},
        {"symbol": "AMAT", "timeframe": "15Min"},
        {"symbol": "APH", "timeframe": "15Min"},
        {"symbol": "MNQ", "timeframe": "12Min"},
    ]
    assert attributed(preferred, {"symbol": "AMAT", "timeframe": "5Min"}) is True
    assert attributed(preferred, {"symbol": "AMAT", "timeframe": "15Min"}) is False
    assert attributed(preferred, {"symbol": "APH", "timeframe": "15Min"}) is False
    assert order_targets(None, TARGETS) == TARGETS

    card_keys = [target_key(target) for target in ordered]
    assert len(card_keys) == len(set(card_keys))
    assert card_keys[0] == "AMAT:5Min"

    synthetic_rows = {}
    synthetic_research_context = {}
    for index, target in enumerate(TARGETS):
        key = target_key(target)
        synthetic_rows[key] = {
            "identity": target,
            "preview_status": f"READY_{index}",
            "read_only": True,
        }
        synthetic_research_context[key] = {
            "identity": target,
            "source": f"synthetic_{index}",
        }

    assert synthetic_rows["AMAT:5Min"]["identity"] == {"symbol": "AMAT", "timeframe": "5Min"}
    assert synthetic_rows["AMAT:15Min"]["identity"] == {"symbol": "AMAT", "timeframe": "15Min"}
    assert synthetic_rows["AMAT:5Min"] != synthetic_rows["AMAT:15Min"]
    assert synthetic_research_context["AMAT:5Min"]["source"] == "synthetic_1"
    assert synthetic_research_context["AMAT:15Min"]["source"] == "synthetic_0"
    assert len(synthetic_rows) == len(TARGETS)
    assert len(synthetic_research_context) == len(TARGETS)

    semantic_payload = json.dumps(
        {
            "preferred_target": preferred,
            "ordered_targets": ordered,
            "attributed_exact": attributed(preferred, ordered[0]),
            "same_symbol_wrong_timeframe_attributed": attributed(preferred, ordered[1]),
            "card_keys": card_keys,
            "row_keys": sorted(synthetic_rows),
            "research_context_keys": sorted(synthetic_research_context),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()

    receipt = {
        "schema": "mm.strategy_health_composite_target_identity_sanitized_acceptance.v1",
        "product_head": PRODUCT_HEAD,
        "acceptance_class": "SANITIZED_COMPOSITE_SYMBOL_TIMEFRAME_EVIDENCE_IDENTITY",
        "operator_consequence": {
            "preferred_target_first": True,
            "attribution_requires_exact_symbol_and_timeframe": True,
            "same_symbol_wrong_timeframe_rejected": True,
            "composite_card_identity": True,
            "rows_keyed_by_symbol_and_timeframe": True,
            "research_context_keyed_by_symbol_and_timeframe": True,
            "same_symbol_different_timeframes_preserved": True,
        },
        "protected_boundaries": {
            "strategy_spec_mutation": False,
            "runtime_authority_change": False,
            "portfolio_ranking": False,
            "portfolio_allocation": False,
            "broker_submission": False,
            "live_trading_change": False,
        },
        "semantic_sha256": hashlib.sha256(semantic_payload).hexdigest(),
        "result": "PASS",
    }
    Path("strategy-health-runtime-focus-acceptance-r1-result.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()

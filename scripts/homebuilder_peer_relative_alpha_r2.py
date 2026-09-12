from __future__ import annotations

"""Source-admissible continuation of the frozen Homebuilder peer-relative test.

TMHC is classified source-blocked before any economic result because the fixed
Yahoo route returned only 40 daily sessions (2026-07-17 through 2026-09-11),
while every other predeclared symbol returned 1,934 sessions. No replacement
security is introduced. The economic holdout is therefore the remaining original
predeclared set GRBK/CVCO/SKY, and all 3/3 must pass the per-symbol gate.
"""

import contextlib
import io
import json

import homebuilder_peer_relative_alpha_r1 as base

SOURCE_PREFLIGHT = {
    "commit": "0feb563b52f66fd3734f6c2bcc22c636e835233c",
    "run": 34683577153,
    "job": 103526498663,
    "economic_results_observed_before_classification": False,
    "common_sessions_without_tmhc": 1934,
    "tmhc_sessions": 40,
    "tmhc_first": "2026-07-17",
    "tmhc_last": "2026-09-11",
}
SOURCE_BLOCKED_EXTERNAL = {
    "TMHC": "fixed Yahoo historical route exposes only 40 daily sessions from 2026-07-17 through 2026-09-11; source-blocked and unscored before economics"
}

# Preserve the original predeclared holdout family without outcome-selected
# replacement. Only the source-valid original names enter the economic test.
base.EXTERNAL = ("GRBK", "CVCO", "SKY")
base.ALL = (*base.DEV, *base.EXTERNAL, *base.CONTEXT)


def main() -> None:
    # Suppress the R1 full-payload print. The durable JSON remains authoritative;
    # this wrapper emits a compact terminal receipt after adding source lineage.
    with contextlib.redirect_stdout(io.StringIO()):
        base.main()

    payload = json.loads(base.OUTPUT.read_text(encoding="utf-8"))
    payload["schema"] = "public_research.homebuilder_peer_relative_alpha_r2"
    payload["source_preflight"] = SOURCE_PREFLIGHT
    payload["source_blocked_external"] = SOURCE_BLOCKED_EXTERNAL
    payload["contract"]["original_predeclared_external_symbols"] = ["TMHC", "GRBK", "CVCO", "SKY"]
    payload["contract"]["source_valid_external_symbols"] = list(base.EXTERNAL)
    payload["contract"]["source_blocked_external_symbols"] = ["TMHC"]
    payload["acceptance_gate"]["external_symbols_passing_required"] = 3
    payload["acceptance_gate"]["external_symbols_available"] = 3
    payload["acceptance_gate"]["external_symbol_rule"] = "all 3/3 source-valid original holdouts must pass; no replacement ticker permitted"

    base.OUTPUT.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    receipt = {
        "schema": payload["schema"],
        "decision": payload["decision"],
        "metrics": payload["metrics"],
        "folds": payload["folds"],
        "external_symbols": payload["external_symbols"],
        "source": {
            "common_first": payload["source"]["common_first"],
            "common_last": payload["source"]["common_last"],
            "common_sessions": payload["source"]["common_sessions"],
        },
        "source_preflight": SOURCE_PREFLIGHT,
        "source_blocked_external": SOURCE_BLOCKED_EXTERNAL,
    }
    print("HOMEBUILDER_PEER_RELATIVE_ALPHA_RECEIPT=" + json.dumps(receipt, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()

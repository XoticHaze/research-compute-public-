from __future__ import annotations

"""Monotonic publish guard for the coherent forward-current bundle.

Concurrent workflow runs may finish out of order. This guard prevents an older
scoreboard/observer artifact from overwriting fresher current state and prevents
prospective registration timestamps from moving forward for the same frozen signal.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

BLOCK_EXIT = 10


def _read(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _dt(value: Any) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _date_text(value: Any) -> str | None:
    return None if value in (None, "") else str(value)[:10]


def decide(
    incoming_score: dict[str, Any],
    incoming_largecap: dict[str, Any],
    current_score: dict[str, Any] | None,
    current_largecap: dict[str, Any] | None,
) -> dict[str, Any]:
    reasons: list[str] = []

    if current_score:
        inc_gen = _dt(incoming_score.get("generated_at"))
        cur_gen = _dt(current_score.get("generated_at"))
        if inc_gen and cur_gen and inc_gen < cur_gen:
            reasons.append("STALE_SCOREBOARD_GENERATED_AT")

        inc_ledger = ((incoming_score.get("coverage") or {}).get("prospective_ledger") or {})
        cur_ledger = ((current_score.get("coverage") or {}).get("prospective_ledger") or {})
        inc_asof = _date_text(inc_ledger.get("market_data_asof"))
        cur_asof = _date_text(cur_ledger.get("market_data_asof"))
        if inc_asof and cur_asof and inc_asof < cur_asof:
            reasons.append("STALE_PROSPECTIVE_LEDGER_MARKET_ASOF")

    if current_largecap:
        inc_asof = _date_text(incoming_largecap.get("market_data_asof"))
        cur_asof = _date_text(current_largecap.get("market_data_asof"))
        if inc_asof and cur_asof and inc_asof < cur_asof:
            reasons.append("STALE_LARGECAP_MARKET_ASOF")

        same_signal = (
            incoming_largecap.get("program_id") == current_largecap.get("program_id")
            and incoming_largecap.get("signal_date") == current_largecap.get("signal_date")
        )
        if same_signal:
            inc_first = _dt(incoming_largecap.get("first_registered_at"))
            cur_first = _dt(current_largecap.get("first_registered_at"))
            if inc_first and cur_first and inc_first > cur_first:
                reasons.append("LARGECAP_FIRST_REGISTRATION_REGRESSION")

    return {
        "publish_allowed": not reasons,
        "reasons": reasons,
        "incoming_scoreboard_generated_at": incoming_score.get("generated_at"),
        "current_scoreboard_generated_at": None if current_score is None else current_score.get("generated_at"),
        "incoming_largecap_asof": incoming_largecap.get("market_data_asof"),
        "current_largecap_asof": None if current_largecap is None else current_largecap.get("market_data_asof"),
        "incoming_largecap_first_registered_at": incoming_largecap.get("first_registered_at"),
        "current_largecap_first_registered_at": None if current_largecap is None else current_largecap.get("first_registered_at"),
    }


def self_test() -> None:
    score_old = {
        "generated_at": "2026-09-18T05:00:00+00:00",
        "coverage": {"prospective_ledger": {"market_data_asof": "2026-09-17"}},
    }
    score_new = {
        "generated_at": "2026-09-18T06:00:00+00:00",
        "coverage": {"prospective_ledger": {"market_data_asof": "2026-09-18"}},
    }
    large_old = {
        "program_id": "GENERALIZED_LARGECAP_RIDGE",
        "signal_date": "2026-09-11",
        "market_data_asof": "2026-09-17",
        "first_registered_at": "2026-09-18T05:03:20+00:00",
    }
    large_regressed = {
        **large_old,
        "first_registered_at": "2026-09-18T05:06:45+00:00",
    }
    blocked = decide(score_old, large_regressed, score_new, large_old)
    assert blocked["publish_allowed"] is False
    assert "STALE_SCOREBOARD_GENERATED_AT" in blocked["reasons"]
    assert "STALE_PROSPECTIVE_LEDGER_MARKET_ASOF" in blocked["reasons"]
    assert "LARGECAP_FIRST_REGISTRATION_REGRESSION" in blocked["reasons"]

    allowed = decide(score_new, large_old, score_old, large_old)
    assert allowed["publish_allowed"] is True
    print("FORWARD_BUNDLE_PUBLISH_GUARD_SELF_TEST=PASS")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--incoming-scoreboard")
    p.add_argument("--incoming-largecap")
    p.add_argument("--current-scoreboard")
    p.add_argument("--current-largecap")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()

    if args.self_test:
        self_test()
        return
    if not args.incoming_scoreboard or not args.incoming_largecap:
        p.error("--incoming-scoreboard and --incoming-largecap are required unless --self-test")

    decision = decide(
        _read(Path(args.incoming_scoreboard)) or {},
        _read(Path(args.incoming_largecap)) or {},
        _read(Path(args.current_scoreboard)) if args.current_scoreboard else None,
        _read(Path(args.current_largecap)) if args.current_largecap else None,
    )
    print(json.dumps(decision, sort_keys=True))
    if not decision["publish_allowed"]:
        raise SystemExit(BLOCK_EXIT)


if __name__ == "__main__":
    main()

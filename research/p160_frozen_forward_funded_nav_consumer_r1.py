"""Read-only P160 frozen forward NAV consumer; owner selects source/issuer.

No data acquisition, broker operation, order, StrategySpec, or promotion. Intended
for integration with the existing P160 observer and existing P46 normalized panel.
The owner must independently authenticate input data rights, issuer and fill basis.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, timezone
from typing import Any, Mapping, Sequence

P160_PROGRAM_ID = "P160_FIXED_P46_P47_COMBINATION"
UNIVERSE = ("SPY", "QQQ", "TLT", "GLD", "DBC", "SMH", "XBI", "ITB", "KRE", "ITA", "IGV", "IWM", "XRT")
FROZEN_SOURCE_BLOB_SHA = "89d8e4c004536310e588623203e8e23e8aac15d9"
FIRST_SCIENTIFIC_SIGNAL = date(2026, 9, 30)
EXPLORATORY_COST_BPS = 50.0


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp requires explicit UTC offset")
    return parsed.astimezone(timezone.utc)


def _weights(weights: Mapping[str, Any], label: str) -> dict[str, float]:
    if not weights or set(weights) - set(UNIVERSE):
        raise ValueError(f"{label} unknown or empty symbol")
    w = {str(k): float(v) for k, v in weights.items()}
    if any(not math.isfinite(v) or v < 0 for v in w.values()):
        raise ValueError(f"{label} invalid weights")
    if abs(sum(w.values()) - 1.0) > 1e-9:
        raise ValueError(f"{label} not fully funded")
    return w


def score_frozen_p160(
    *,
    frozen_signal: Mapping[str, Any],
    completed_bars: Sequence[Mapping[str, Any]],
    observed_at_utc: str,
    price_basis: str,
    source_provider: str,
    source_issuer_authenticated: bool = False,
    expected_common_session_dates: Sequence[str],
    expected_entry_day: str,
    entry_mode: str = "open",
) -> dict[str, Any]:
    """Score fixed signal against matched controls using supplied completed daily bars.

    Each row must have date, symbol, open, close, session_open_utc,
    session_close_utc, completed=true. The first complete common session after
    the frozen signal date is the only permissible entry session. For the
    conservative close-entry sensitivity, the entry is the *next* session's
    close, not the same signal close. Both are research-only until owning issuer.
    """
    if frozen_signal.get("program_id") != P160_PROGRAM_ID:
        raise ValueError("P160 program identity mismatch")
    identity = frozen_signal.get("frozen_identity", {})
    if identity.get("source_blob_sha") != FROZEN_SOURCE_BLOB_SHA:
        raise ValueError("frozen source identity mismatch")
    if float(identity.get("primary_cost_bps", -1)) != EXPLORATORY_COST_BPS:
        raise ValueError("frozen cost mismatch")
    if frozen_signal.get("timing", {}).get("same_close_execution_prohibited") is not True:
        raise ValueError("same-close prohibition missing")
    signal_day = date.fromisoformat(frozen_signal["signal_month_end"])
    if signal_day < FIRST_SCIENTIFIC_SIGNAL:
        raise ValueError("prestart signal has no prospective score")
    signal_created = _parse_utc(frozen_signal["generated_at"])
    observed = _parse_utc(observed_at_utc)
    if observed <= signal_created:
        raise ValueError("observation not after signal")
    if entry_mode not in ("open", "close"):
        raise ValueError("entry mode must be open or close")
    if price_basis not in ("raw_sip", "adjusted_owner_issued"):
        raise ValueError("unrecognized price basis")
    if not source_provider:
        raise ValueError("missing provider")
    actions = frozen_signal.get("paper_action", {})
    target = _weights(actions.get("target_weights", {}), "target")
    matched = _weights(actions.get("matched_control_weights", {}), "matched")
    if set(matched) != set(UNIVERSE):
        raise ValueError("matched source universe incomplete")
    if set(target) != set(("IGV", "IWM", "QQQ", "SPY", "XBI")):
        raise ValueError("frozen target membership changed")
    arms = {"target": target, "matched": matched, "SPY": {"SPY": 1.0}, "QQQ": {"QQQ": 1.0}}
    sessions: dict[date, dict[str, Mapping[str, Any]]] = {}
    for bar in completed_bars:
        day = date.fromisoformat(str(bar["date"]))
        if day <= signal_day:
            continue
        sym = str(bar["symbol"])
        if sym not in UNIVERSE:
            raise ValueError(f"unexpected symbol {sym}")
        if bar.get("completed") is not True:
            raise ValueError(f"incomplete session {day} {sym}")
        opening = _parse_utc(str(bar["session_open_utc"]))
        closing = _parse_utc(str(bar["session_close_utc"]))
        if not (opening < closing < observed):
            raise ValueError(f"unclosed or noncausal session {day} {sym}")
        if day != opening.date() or day != closing.date():
            raise ValueError(f"date mismatch {day} {sym}")
        for key in ("open", "close"):
            price = float(bar[key])
            if not math.isfinite(price) or price <= 0:
                raise ValueError(f"bad {key} {day} {sym}")
        bucket = sessions.setdefault(day, {})
        if sym in bucket:
            raise ValueError(f"duplicate bar {day} {sym}")
        bucket[sym] = bar
    if not sessions:
        raise ValueError("no completed forward sessions")
    days = sorted(sessions)
    # A truncated panel cannot redefine the original entry or elapsed sessions.
    expected_days = [date.fromisoformat(x) for x in expected_common_session_dates]
    if not expected_days or expected_days != sorted(set(expected_days)):
        raise ValueError("invalid independent common-session calendar")
    if days != expected_days:
        raise ValueError("missing or extra expected common-session date")
    if days[0] != date.fromisoformat(expected_entry_day):
        raise ValueError("entry day differs from frozen expected next session")
    for day in days:
        if set(sessions[day]) != set(UNIVERSE):
            raise ValueError(f"missing common session member {day}")
    entry_day = days[0]
    entry_ts = _parse_utc(str(sessions[entry_day]["SPY"]["session_open_utc" if entry_mode == "open" else "session_close_utc"]))
    if not (entry_day > signal_day and entry_ts > signal_created):
        raise ValueError("signal issued after first entry or same-close execution")
    entry_prices = {s: float(sessions[entry_day][s][entry_mode]) for s in UNIVERSE}
    curves: dict[str, list[float]] = {arm: [] for arm in arms}
    for day in days:
        for arm, weights in arms.items():
            nav = 1.0 - EXPLORATORY_COST_BPS / 10000.0 + sum(
                weight * (float(sessions[day][sym]["close"]) / entry_prices[sym] - 1.0)
                for sym, weight in weights.items()
            )
            if not math.isfinite(nav) or nav <= 0:
                raise ValueError(f"invalid funded NAV {arm} {day}")
            curves[arm].append(nav)
    summary = {}
    for arm, values in curves.items():
        peak = 1.0
        worst_dd = 0.0
        for value in values:
            peak = max(peak, value)
            worst_dd = min(worst_dd, value / peak - 1.0)
        summary[arm] = {
            "net_return_bps": (values[-1] - 1.0) * 10000.0,
            "max_drawdown_pct": worst_dd * 100.0,
            "daily_nav": values,
        }
    result = {
        "schema": "research.p160_frozen_funded_nav_source_consumer_r1",
        "program_id": P160_PROGRAM_ID,
        "source": {"provider": source_provider, "price_basis": price_basis,
                   "issuer_authenticated": bool(source_issuer_authenticated),
                   "source_rows": len(completed_bars),
                   "rows_sha256": hashlib.sha256(json.dumps(list(completed_bars), sort_keys=True, separators=(",", ":")).encode()).hexdigest()},
        "signal": {"month_end": signal_day.isoformat(), "issued_at_utc": signal_created.isoformat(),
                   "frozen_blob_sha": FROZEN_SOURCE_BLOB_SHA},
        "forward": {"entry_day": entry_day.isoformat(), "entry_mode": entry_mode,
                    "last_completed_day": days[-1].isoformat(), "completed_sessions": len(days),
                    "expected_common_session_dates": [d.isoformat() for d in expected_days],
                    "same_close_execution": False, "cost_bps": EXPLORATORY_COST_BPS},
        "economics": summary,
        "relative_bps": {
            "target_minus_matched": summary["target"]["net_return_bps"] - summary["matched"]["net_return_bps"],
            "target_minus_SPY": summary["target"]["net_return_bps"] - summary["SPY"]["net_return_bps"],
            "target_minus_QQQ": summary["target"]["net_return_bps"] - summary["QQQ"]["net_return_bps"],
        },
        "stage": "OWNER_ISSUER_SOURCE_SUPPORT_ONLY__NO_SCIENTIFIC_PROMOTION",
        "authority": {"research_only": True, "allocation": False, "broker": False, "live": False,
                      "model_promotion": False, "protected_holdout_access": False},
    }
    return result
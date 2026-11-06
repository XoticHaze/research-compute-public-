#!/usr/bin/env python3
"""Audit/reconstruct frozen-model forward decisions without fabricating prospective credit.

Date-indexed adapter source, already-admitted ledger, and a *caller supplied* official
exchange-session calendar are separate authorities. This module does not generate
predictions, infer paper approval, or change canonical cohort state. Missing
predictions stay MISSING; point-in-time replayed predictions stay HISTORICAL_REPLAY.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any

SCHEMA = "research.forward_decision_continuity_r1"
MANIFEST_SCHEMA = "research.forward_decision_continuity_manifest_r1"
ADAPTER_SCHEMA = "foundry.forward_program_adapter.v1"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _date(x: Any) -> str:
    if not isinstance(x, str) or not DATE_RE.fullmatch(x):
        raise ValueError(f"invalid ISO date: {x!r}")
    if date.fromisoformat(x).isoformat() != x:
        raise ValueError(f"invalid ISO date: {x!r}")
    return x


def _utc(x: str) -> datetime:
    if not isinstance(x, str):
        raise ValueError("timestamp must be an ISO8601 string with timezone")
    dt = datetime.fromisoformat(x.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timestamp requires UTC offset")
    return dt.astimezone(timezone.utc)


def _load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object: {path}")
    return data


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _session_index(calendar: list[str]) -> dict[str, int]:
    if not isinstance(calendar, list) or not calendar:
        raise ValueError("non-empty official market_sessions required")
    clean = [_date(x) for x in calendar]
    if clean != sorted(set(clean)):
        raise ValueError("market_sessions must be unique and ascending")
    return {d: i for i, d in enumerate(clean)}


def _validate_models(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError("manifest schema mismatch")
    models = {}
    for model in manifest.get("models", []):
        program = model.get("program_id")
        if not isinstance(program, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{1,79}", program):
            raise ValueError("invalid program_id")
        if program in models:
            raise ValueError("duplicate program_id")
        if model.get("cadence") != "DAILY_CLOSE":
            raise ValueError(f"unsupported cadence for {program}; use a distinct model-specific calendar")
        if not isinstance(model.get("frozen_model_ref"), str) or not model["frozen_model_ref"]:
            raise ValueError("frozen model identity required")
        _date(model.get("first_eligible_decision_date"))
        for field in ("execution_delay_sessions", "holding_horizon_sessions"):
            v = model.get(field)
            if type(v) is not int or v < 1:
                raise ValueError(f"invalid {field} for {program}")
        if model.get("qualifier") not in ("SEMICONDUCTOR_POSITIVE_VALUE", "HOMEBUILDERS_ADMITTED", "OBSERVATION_ONLY"):
            raise ValueError(f"frozen qualifier required for {program}")
        models[program] = model
    if not models:
        raise ValueError("manifest has no models")
    return models


def _read_indexed_adapters(root: Path, models: dict[str, dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    """Accept only immutable dated paths <root>/<PROGRAM>/<YYYY-MM-DD>.json.

    Never interpret latest.json as historical evidence. Fail closed on duplicate
    identities, mismatched file/adapter dates, and unfrozen model lineage.
    """
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for program, model in models.items():
        directory = root / program
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            if not DATE_RE.fullmatch(path.stem):
                continue
            day = _date(path.stem)
            adapter = _load(path)
            if adapter.get("schema") != ADAPTER_SCHEMA or adapter.get("program_id") != program:
                raise ValueError(f"adapter identity/schema mismatch: {path}")
            if _date(adapter.get("signal_date")) != day:
                raise ValueError(f"signal_date/file mismatch: {path}")
            # One model/source identity must be stable across recovered dates;
            # never map a changed model to the old model's cohort history.
            source = model.get("source_ref")
            if source is not None and adapter.get("source_ref") not in (None, source):
                raise ValueError(f"model source_ref changed: {path}")
            bounds = adapter.get("boundaries") or {}
            for key in ("broker_action", "live_trading_change", "promotion_authority", "runtime_mutation"):
                if bounds.get(key) is not False:
                    raise ValueError(f"unsafe adapter boundary {key}: {path}")
            provenance_file = directory / (day + ".provenance.json")
            if provenance_file.is_file():
                prov = _load(provenance_file)
                if prov.get("adapter_sha256") != _hash(path):
                    raise ValueError(f"provenance hash mismatch: {provenance_file}")
                if prov.get("evidence_class") not in ("ORIGINAL_TIMESTAMPED", "REPLAYED_ASOF"):
                    raise ValueError(f"invalid provenance evidence_class: {provenance_file}")
                observed = prov.get("original_observed_at") if prov["evidence_class"] == "ORIGINAL_TIMESTAMPED" else prov.get("replayed_at")
                _utc(observed)
                if prov.get("frozen_model_ref") != model["frozen_model_ref"]:
                    raise ValueError(f"model identity mismatch: {provenance_file}")
            else:
                prov = None
            key = (program, day)
            if key in result:
                raise ValueError(f"conflicting dated decision {key}")
            result[key] = {"adapter": adapter, "adapter_sha256": _hash(path), "provenance": prov}
    return result


def _qualify(adapter: dict[str, Any], model: dict[str, Any]) -> tuple[str, list[str], str]:
    qualifier = model["qualifier"]
    if qualifier == "OBSERVATION_ONLY":
        return "OBSERVATION_ONLY", [], "observer has no frozen funded entry rule"
    signal = adapter.get("signal") or {}
    if qualifier == "HOMEBUILDERS_ADMITTED":
        names = signal.get("admitted_symbols") or []
        if not isinstance(names, list) or not all(isinstance(s, str) and s for s in names):
            raise ValueError("invalid homebuilders admitted symbols")
        horizons = signal.get("duration_horizon_sessions_by_symbol") or {}
        if any(type(horizons.get(s)) is not int for s in names):
            raise ValueError("homebuilders frozen symbol horizon missing")
        return ("QUALIFY" if names else "NO_ENTRY"), sorted(set(names)), "frozen homebuilders admission"
    if adapter.get("validation", {}).get("scientific_forward_credit") is not True:
        return "NO_ENTRY", [], "forward eligibility false for observation"
    values = signal.get("predicted_fixed20_net_value_bps") or {}
    if not isinstance(values, dict) or not values:
        raise ValueError("Shared Ridge missing model prediction vector")
    positive = set(signal.get("positive_symbols") or [])
    if not all(type(v) in (float, int) and math.isfinite(float(v)) for v in values.values()):
        raise ValueError("invalid model prediction magnitude")
    calculated = {symbol for symbol, value in values.items() if float(value) > 0}
    if positive != calculated:
        raise ValueError("frozen Shared Ridge positive mask differs from predictions")
    if not positive:
        return "NO_ENTRY", [], "no frozen positive value predictions"
    book = (adapter.get("paper_action") or {}).get("ticker_book") or {}
    weights = book.get("cohort_target_weights_nav")
    if book.get("status") != "PAPER_COHORT_READY" or not isinstance(weights, dict) or set(weights) != positive:
        return "ADMISSION_INCOMPLETE", sorted(positive), "frozen paper book missing or incomplete"
    if not all(type(v) in (int, float) and math.isfinite(float(v)) and v > 0 for v in weights.values()):
        raise ValueError("invalid frozen paper weights")
    return "QUALIFY", sorted(positive), "positive frozen model predictions and complete paper book"


def _evidence(prov: dict[str, Any] | None, entry_date: str | None) -> str:
    if prov is None:
        return "UNDOCUMENTED_DATED_ADAPTER_NO_CREDIT"
    if prov["evidence_class"] == "REPLAYED_ASOF":
        return "HISTORICAL_REPLAY_NO_PROSPECTIVE_CREDIT"
    observed = _utc(prov["original_observed_at"])
    if entry_date is not None:
        entry_open = datetime.combine(date.fromisoformat(entry_date), datetime.min.time().replace(hour=9, minute=30)).replace(tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)
        if observed >= entry_open:
            return "LATE_ORIGINAL_RECEIPT_NO_PROSPECTIVE_CREDIT"
    # Filename/hash and a claimed timestamp alone cannot authenticate a private
    # scientific issuer. Independent owning-side verification remains necessary.
    return "ORIGINAL_RECEIPT_NEEDS_ISSUER_VERIFICATION"


def build(manifest: dict[str, Any], adapter_root: Path, prior_ledger: dict[str, Any] | None = None) -> dict[str, Any]:
    models = _validate_models(manifest)
    calendar = [_date(x) for x in manifest["market_sessions"]]
    positions = _session_index(calendar)
    asof = _date(manifest["asof"])
    if not any(day <= asof for day in calendar):
        raise ValueError("market calendar contains no session on or before asof")
    last_observed_session = max(day for day in calendar if day <= asof)
    existing = {}
    for cohort in (prior_ledger or {}).get("cohorts", []):
        program, signal_day = cohort.get("program_id"), cohort.get("signal_date")
        if program in models and signal_day:
            key = (program, _date(signal_day))
            if key in existing:
                raise ValueError(f"duplicate previously admitted ledger cohort {key}")
            existing[key] = cohort
    indexed = _read_indexed_adapters(adapter_root, models)
    rows = []
    summaries = {}
    for program, model in sorted(models.items()):
        first = model["first_eligible_decision_date"]
        last = _date(model.get("last_eligible_decision_date", asof))
        if last > asof:
            last = asof
        if first not in positions:
            raise ValueError(f"first eligible {first} is not in supplied exchange calendar for {program}")
        eligible = [d for d in calendar if first <= d <= last]
        if not eligible:
            raise ValueError(f"no eligible exchange sessions for {program}")
        counts: Counter[str] = Counter()
        for day in eligible:
            key = (program, day)
            archived = indexed.get(key)
            prior = existing.get(key)
            decision = "MISSING_PREDICTION"
            selected: list[str] = []
            reason = "no immutable date-indexed adapter or canonical admitted cohort"
            if archived:
                decision, selected, reason = _qualify(archived["adapter"], model)
            elif prior:
                decision = "PRIOR_ADMITTED_COHORT"
                selected = sorted(prior.get("symbols") or [])
                reason = "already admitted canonical cohort; original signal adapter not in dated store"
            idx = positions[day]
            entry_idx = idx + model["execution_delay_sessions"]
            if entry_idx < len(calendar):
                entry = calendar[entry_idx]
            else:
                entry = None
            exit_idx = entry_idx + model["holding_horizon_sessions"]
            exit_day = calendar[exit_idx] if exit_idx < len(calendar) else None
            elapsed = max(0, min(model["holding_horizon_sessions"], positions[last_observed_session] - entry_idx)) if entry else 0
            evidence = (
                "CANONICAL_ORIGINAL_COHORT_LEDGER_PRESERVED"
                if prior is not None else _evidence(archived["provenance"] if archived else None, entry)
            )
            # We do not authenticate original first-seen time here. The owning
            # verifier must approve a dated receipt before retrospective credit.
            if prior is not None and prior.get("status") == "LATE_REGISTRATION_REJECTED":
                evidence = "CANONICAL_REJECTED_NO_PROSPECTIVE_CREDIT"
            row = {
                "program_id": program, "signal_date": day,
                "decision": decision, "decision_reason": reason,
                "symbols": selected,
                "entry_date": entry if decision in ("QUALIFY", "PRIOR_ADMITTED_COHORT") else None,
                "horizon_end_date": exit_day if decision in ("QUALIFY", "PRIOR_ADMITTED_COHORT") else None,
                "holding_sessions_elapsed_asof": elapsed if decision in ("QUALIFY", "PRIOR_ADMITTED_COHORT") else None,
                "source_adapter_sha256": archived["adapter_sha256"] if archived else prior.get("source_adapter_sha256") if prior else None,
                "frozen_model_ref": model["frozen_model_ref"],
                "evidence_class": evidence,
                "scientific_forward_credit_granted_by_this_tool": False,
                "paper_trade_executed": False,
                "source_receipt": archived["provenance"] if archived else None,
                "canonical_cohort_id": prior.get("cohort_id") if prior else None,
            }
            rows.append(row)
            counts[decision] += 1
        summaries[program] = {
            "first_eligible_decision_date": first,
            "last_audited_decision_date": eligible[-1],
            "expected_decisions": len(eligible),
            "recorded_source_or_ledger_decisions": sum(1 for r in rows if r["program_id"] == program and r["source_adapter_sha256"]),
            "missing_predictions": counts["MISSING_PREDICTION"],
            "qualifying_recovered_decisions": counts["QUALIFY"],
            "canonical_admitted_without_dated_adapter": counts["PRIOR_ADMITTED_COHORT"],
            "recorded_no_entry": counts["NO_ENTRY"],
            "observation_only": counts["OBSERVATION_ONLY"],
            "admission_incomplete": counts["ADMISSION_INCOMPLETE"],
        }
    return {
        "schema": SCHEMA,
        "asof": asof,
        "latest_completed_market_session": last_observed_session,
        "manifest_sha256": hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "summary": summaries,
        "decisions": rows,
        "boundaries": {
            "no_generated_prediction_from_future_outcomes": True,
            "no_prospective_credit_from_replay": True,
            "no_promotion_or_broker_authority": True,
            "canonical_ledger_unchanged": True,
        },
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, required=True, help="Frozen owner-confirmed model eligibility and official calendar")
    p.add_argument("--dated-adapters", type=Path, required=True, help="<program>/<YYYY-MM-DD>.json and .provenance.json")
    p.add_argument("--prior-ledger", type=Path, help="Existing immutable prospective ledger, not writable")
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    result = build(_load(args.manifest), args.dated_adapters, _load(args.prior_ledger) if args.prior_ledger else None)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"summary": result["summary"], "output": str(args.out)}, sort_keys=True))


if __name__ == "__main__":
    main()
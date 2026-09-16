#!/usr/bin/env python3
"""Classify the IBKR login boundary without conflating controller state with 2FA.

The controller's internal TWO_FA state is only an implementation phase. A real
second-factor challenge is authoritative only when a concrete dialog/initiation
or IB Key mobile-approval signal is present in controller/launcher logs.

Pre-challenge blockers are deliberately stricter: CCP lockout/backoff is true
only when a single log line contains both a CCP/auth context and an explicit
lockout/backoff condition. This avoids combining unrelated words that happen to
occur elsewhere in a long launcher log.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def _text(path: str | None) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.exists():
        return ""
    return p.read_text(errors="replace")


def _has(text: str, *needles: str) -> bool:
    hay = text.casefold()
    return any(needle.casefold() in hay for needle in needles)


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _ccp_lockout_line(line: str) -> bool:
    hay = line.casefold()
    context = any(token in hay for token in ("ccp", "authentication", "authenticate", "login"))
    blocker = any(
        token in hay
        for token in (
            "lockout",
            "locked out",
            "temporarily locked",
            "too many login attempts",
            "too many attempts",
            "backoff",
            "retry later",
            "try again later",
        )
    )
    return context and blocker


def _redact(line: str) -> str:
    # Keep evidence operator-useful while preventing credentials/account identity
    # from being emitted into public Actions logs or artifacts.
    line = re.sub(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "<redacted-email>", line, flags=re.I)
    line = re.sub(r"\b(?:DU|U)\d{4,}\b", "<redacted-account>", line, flags=re.I)
    line = re.sub(
        r"(?i)\b(username|user|password|passwd|token|secret|api[_-]?key)\s*[:=]\s*[^\s,;]+",
        lambda match: f"{match.group(1)}=<redacted>",
        line,
    )
    return line[:320]


def _evidence_excerpt(controller: str, launcher: str, limit: int = 16) -> list[str]:
    markers = (
        "ccp",
        "lockout",
        "locked",
        "backoff",
        "too many",
        "retry later",
        "try again later",
        "authenticat",
        "ns_auth_start",
        "postauthenticate",
        "second factor",
        "2fa",
        "ib key",
        "security code",
        "passkey",
        "maintenance",
        "reset window",
        "server reset",
    )
    selected: list[str] = []
    seen: set[str] = set()
    for source, text in (("controller", controller), ("launcher", launcher)):
        for raw in _lines(text):
            folded = raw.casefold()
            if not any(marker in folded for marker in markers):
                continue
            item = f"{source}: {_redact(raw)}"
            if item in seen:
                continue
            seen.add(item)
            selected.append(item)
            if len(selected) >= limit:
                return selected
    return selected


def classify(controller: str, launcher: str) -> dict[str, object]:
    combined = controller + "\n" + launcher
    all_lines = _lines(combined)

    controller_internal_twofa_phase = _has(
        controller,
        "[state: two_fa]",
        "state_two_fa",
        "state: two_fa",
    )
    ibkey_dialog_detected = _has(combined, "ib key 2fa dialog detected")
    ibkey_mobile_approval_wait_signal = _has(combined, "waiting for ib key mobile approval")
    twofa_initiated_signal = _has(
        combined,
        "second factor authentication initiated",
        "two-factor authentication initiated",
        "2fa initiated",
    )
    generic_twofa_dialog_detected = _has(
        combined,
        "2fa dialog detected",
        "two-factor dialog detected",
        "second factor dialog detected",
    )
    security_code_dialog_observed = _has(
        combined,
        "security code dialog",
        "enter security code",
        "authentication code",
    )
    device_selection_observed = _has(
        combined,
        "second factor device",
        "select a device",
        "select device",
        "device selection",
    )
    passkey_prompt_observed = _has(combined, "passkey", "security key")
    credential_rejection_observed = _has(
        combined,
        "invalid username",
        "invalid password",
        "incorrect username",
        "incorrect password",
        "login failed",
        "authentication failed",
    )
    ccp_lockout_observed = any(_ccp_lockout_line(line) for line in all_lines)
    maintenance_observed = _has(
        combined,
        "maintenance",
        "reset window",
        "server reset",
        "daily reset",
    )
    ns_auth_start_observed = _has(launcher, "ns_auth_start")
    post_authenticate_observed = _has(launcher, "postauthenticate")
    api_ready_observed = _has(
        combined,
        "api port open",
        "api ready",
        "api_ready",
        "session preserved",
    )

    # Authoritative boundary: raw controller TWO_FA state is deliberately
    # excluded. It identifies an internal phase only; it is not proof that IBKR
    # emitted a second-factor challenge or that a phone notification exists.
    second_factor_challenge_observed = any(
        (
            ibkey_dialog_detected,
            ibkey_mobile_approval_wait_signal,
            twofa_initiated_signal,
            generic_twofa_dialog_detected,
            security_code_dialog_observed,
            device_selection_observed,
            passkey_prompt_observed,
        )
    )

    terminal_prechallenge_blocker = (
        not second_factor_challenge_observed
        and not api_ready_observed
        and (credential_rejection_observed or ccp_lockout_observed)
    )

    if api_ready_observed:
        stage = "api_ready"
    elif ibkey_mobile_approval_wait_signal:
        stage = "ibkey_mobile_approval_wait"
    elif second_factor_challenge_observed:
        stage = "second_factor_challenge_observed"
    elif credential_rejection_observed:
        stage = "credential_rejected"
    elif ccp_lockout_observed:
        stage = "ccp_auth_lockout_backoff"
    elif maintenance_observed:
        stage = "maintenance_or_reset_signal"
    elif post_authenticate_observed:
        stage = "post_authenticate_before_second_factor"
    elif ns_auth_start_observed:
        stage = "ns_auth_before_second_factor"
    elif controller_internal_twofa_phase:
        stage = "controller_internal_twofa_phase_only"
    elif _has(combined, "authenticating", "connecting to server"):
        stage = "authentication_before_second_factor"
    else:
        stage = "pre_auth_or_unknown"

    return {
        "schema": "mmibkr-ibkr-auth-boundary-v2",
        "stage": stage,
        "controller_internal_twofa_phase": controller_internal_twofa_phase,
        "second_factor_challenge_observed": second_factor_challenge_observed,
        "ibkey_dialog_detected": ibkey_dialog_detected,
        "ibkey_mobile_approval_wait_signal": ibkey_mobile_approval_wait_signal,
        "twofa_initiated_signal": twofa_initiated_signal,
        "generic_twofa_dialog_detected": generic_twofa_dialog_detected,
        "security_code_dialog_observed": security_code_dialog_observed,
        "device_selection_observed": device_selection_observed,
        "passkey_prompt_observed": passkey_prompt_observed,
        "credential_rejection_observed": credential_rejection_observed,
        "ccp_lockout_observed": ccp_lockout_observed,
        "maintenance_observed": maintenance_observed,
        "terminal_prechallenge_blocker": terminal_prechallenge_blocker,
        "ns_auth_start_observed": ns_auth_start_observed,
        "post_authenticate_observed": post_authenticate_observed,
        "api_ready_observed": api_ready_observed,
        "evidence_excerpt": _evidence_excerpt(controller, launcher),
        "controller_log_bytes": len(controller.encode(errors="replace")),
        "launcher_log_bytes": len(launcher.encode(errors="replace")),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--controller-log-file")
    ap.add_argument("--launcher-log-file")
    ap.add_argument("--output")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    result = classify(_text(args.controller_log_file), _text(args.launcher_log_file))
    payload = json.dumps(result, sort_keys=True)
    if not args.quiet:
        print("IBKR_AUTH_BOUNDARY=" + payload)
    if args.output:
        Path(args.output).write_text(payload + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

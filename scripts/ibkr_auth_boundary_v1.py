#!/usr/bin/env python3
"""Classify the IBKR login boundary without conflating controller state with 2FA.

The controller's internal TWO_FA state is only an implementation phase.  A real
second-factor challenge is authoritative only when a concrete dialog/initiation
or IB Key mobile-approval signal is present in controller/launcher logs.
"""

from __future__ import annotations

import argparse
import json
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


def classify(controller: str, launcher: str) -> dict[str, object]:
    combined = controller + "\n" + launcher

    controller_internal_twofa_phase = _has(
        controller,
        "[state: two_fa]",
        "state_two_fa",
        "state: two_fa",
    )
    ibkey_dialog_detected = _has(
        combined,
        "ib key 2fa dialog detected",
    )
    ibkey_mobile_approval_wait_signal = _has(
        combined,
        "waiting for ib key mobile approval",
    )
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
        "select.*device",
        "device selection",
    )
    passkey_prompt_observed = _has(
        combined,
        "passkey",
        "security key",
    )
    credential_rejection_observed = _has(
        combined,
        "invalid username",
        "invalid password",
        "incorrect username",
        "incorrect password",
        "login failed",
        "authentication failed",
    )
    ccp_lockout_observed = _has(
        combined,
        "ccp",
        "lockout",
        "too many login attempts",
        "temporarily locked",
    ) and _has(
        combined,
        "lock",
        "backoff",
        "maintenance",
        "temporarily",
        "authentication",
    )
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

    # The authoritative boundary: internal TWO_FA state alone is deliberately
    # excluded.  It only says which controller branch is active.
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

    if api_ready_observed:
        stage = "api_ready"
    elif ibkey_mobile_approval_wait_signal:
        stage = "ibkey_mobile_approval_wait"
    elif second_factor_challenge_observed:
        stage = "second_factor_challenge_observed"
    elif credential_rejection_observed:
        stage = "credential_rejected"
    elif ccp_lockout_observed or maintenance_observed:
        stage = "ccp_auth_lockout_backoff"
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
        "schema": "mmibkr-ibkr-auth-boundary-v1",
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
        "ns_auth_start_observed": ns_auth_start_observed,
        "post_authenticate_observed": post_authenticate_observed,
        "api_ready_observed": api_ready_observed,
        "controller_log_bytes": len(controller.encode(errors="replace")),
        "launcher_log_bytes": len(launcher.encode(errors="replace")),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--controller-log-file")
    ap.add_argument("--launcher-log-file")
    ap.add_argument("--output")
    args = ap.parse_args()

    result = classify(_text(args.controller_log_file), _text(args.launcher_log_file))
    payload = json.dumps(result, sort_keys=True)
    print("IBKR_AUTH_BOUNDARY=" + payload)
    if args.output:
        Path(args.output).write_text(payload + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

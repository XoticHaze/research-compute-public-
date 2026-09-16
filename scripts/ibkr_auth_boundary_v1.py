#!/usr/bin/env python3
"""Classify the IBKR login boundary from concrete launcher/controller evidence.

The controller's internal TWO_FA state is only an implementation phase. A real
second-factor challenge is authoritative only when a concrete dialog/initiation
or IB Key mobile-approval signal is present.

For the pre-2FA boundary, mirror IB Gateway's launcher protocol directly:
Authenticating -> NS_AUTH_START -> PostAuthenticate. A CCP Timeout before
NS_AUTH_START is terminal. DISCONNECT_AUTHORIZATION_FAILED is intentionally held
open for a short diagnostic window because Gateway can paint a human-readable
credential rejection modal a few seconds after the wire-level disconnect. Only
that concrete UI/controller evidence is classified as bad credentials.
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
    line = re.sub(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "<redacted-email>", line, flags=re.I)
    line = re.sub(r"\b(?:DU|U)\d{4,}\b", "<redacted-account>", line, flags=re.I)
    line = re.sub(
        r"(?i)\b(username|user|password|passwd|token|secret|api[_-]?key)\s*[:=]\s*[^\s,;]+",
        lambda match: f"{match.group(1)}=<redacted>",
        line,
    )
    return line[:360]


def _launcher_auth_transcript(launcher: str, limit: int = 28) -> list[str]:
    markers = (
        "connecting ",
        "connected to ",
        "authenticating",
        "ns_auth_start",
        "postauthenticate",
        "authtimeoutmonitor-ccp",
        "disconnect_authorization_failed",
        "sslhandshakeexception",
        "remote host terminated",
        "not known here",
        "user is not known",
        "unknown user",
        "login failed",
        "authentication failed",
    )
    selected: list[str] = []
    for raw in _lines(launcher):
        folded = raw.casefold()
        if any(marker in folded for marker in markers):
            selected.append(_redact(raw))
            if len(selected) >= limit:
                break
    return selected


def _evidence_excerpt(controller: str, launcher: str, limit: int = 24) -> list[str]:
    selected = [f"launcher: {line}" for line in _launcher_auth_transcript(launcher, limit=limit)]
    seen = set(selected)
    markers = (
        "alert_login_failed",
        "bad-credentials",
        "invalid username",
        "invalid password",
        "authentication failed",
        "login failed",
        "ccp lockout",
        "ccp backoff",
        "second factor",
        "2fa dialog",
        "2fa wait",
        "ib key",
        "security code",
        "passkey",
        "inside ibkr maintenance window",
        "maintenance recovery delay",
        "reset guard",
    )
    for raw in _lines(controller):
        folded = raw.casefold()
        if not any(marker in folded for marker in markers):
            continue
        item = f"controller: {_redact(raw)}"
        if item not in seen:
            selected.append(item)
            seen.add(item)
        if len(selected) >= limit:
            break
    return selected


def _connected_host(launcher: str) -> str | None:
    for pattern in (
        r"\bConnecting\s+([A-Za-z0-9._-]+):\d+",
        r"\bConnected\s+to\s+([A-Za-z0-9._-]+):\d+",
    ):
        match = re.search(pattern, launcher, flags=re.I)
        if match:
            return match.group(1).lower()
    return None


def classify(controller: str, launcher: str) -> dict[str, object]:
    combined = controller + "\n" + launcher
    all_lines = _lines(combined)

    controller_internal_twofa_phase = _has(controller, "[state: two_fa]", "state_two_fa", "state: two_fa")
    ibkey_dialog_detected = _has(combined, "ib key 2fa dialog detected")
    ibkey_mobile_approval_wait_signal = _has(combined, "waiting for ib key mobile approval")
    twofa_initiated_signal = _has(combined, "second factor authentication initiated", "two-factor authentication initiated", "2fa initiated")
    generic_twofa_dialog_detected = _has(combined, "2fa dialog detected", "two-factor dialog detected", "second factor dialog detected")
    security_code_dialog_observed = _has(combined, "security code dialog", "enter security code", "authentication code")
    device_selection_observed = _has(combined, "second factor device", "select a device", "select device", "device selection")
    passkey_prompt_observed = _has(combined, "passkey", "security key")

    credential_rejection_observed = _has(
        combined,
        'ALERT_LOGIN_FAILED mode=',
        'reason="bad-credentials"',
        "invalid username or password",
        "invalid username",
        "invalid password",
        "incorrect username",
        "incorrect password",
        "authentication failed",
        "login failed",
    )
    explicit_ccp_lockout_observed = any(_ccp_lockout_line(line) for line in all_lines)
    ccp_timeout_observed = "AuthTimeoutMonitor-CCP: Timeout!" in launcher
    ns_auth_start_observed = "NS_AUTH_START" in launcher
    post_authenticate_observed = "PostAuthenticate" in launcher
    authenticating_observed = "Authenticating" in launcher
    authorization_rejected_before_ns_auth = (
        _has(launcher, "DISCONNECT_AUTHORIZATION_FAILED")
        and authenticating_observed
        and not ns_auth_start_observed
    )
    ssl_handshake_failure_observed = _has(launcher, "SSLHandshakeException", "Remote host terminated the handshake")
    wrong_server_rejection_observed = _has(
        launcher,
        "this user is not known here",
        "user is not known here",
        "unknown user at this server",
        "not known on this server",
    )
    ccp_silent_timeout_before_ns_auth = ccp_timeout_observed and authenticating_observed and not ns_auth_start_observed

    pre_ns_auth_stall_observed = (
        authenticating_observed
        and not ns_auth_start_observed
        and _has(
            controller,
            "2fa wait t+60s: still waiting",
            "2fa wait t+70s: still waiting",
            "2fa wait t+80s: still waiting",
            "2fa wait t+90s: still waiting",
            "2fa wait t+100s: still waiting",
            "2fa wait t+110s: still waiting",
            "2fa wait t+120s: still waiting",
        )
    )

    maintenance_observed = _has(
        controller,
        "cold start inside ibkr maintenance window",
        "maintenance recovery delay",
        "north_america_daily_reset_guard",
    )

    api_ready_observed = _has(combined, "api port open", "api ready", "api_ready", "session preserved")

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

    authorization_rejection_diagnostic_pending = (
        authorization_rejected_before_ns_auth
        and not credential_rejection_observed
        and not explicit_ccp_lockout_observed
        and not pre_ns_auth_stall_observed
        and not ccp_silent_timeout_before_ns_auth
    )

    terminal_prechallenge_blocker = (
        not second_factor_challenge_observed
        and not api_ready_observed
        and any(
            (
                credential_rejection_observed,
                explicit_ccp_lockout_observed,
                ccp_silent_timeout_before_ns_auth,
                pre_ns_auth_stall_observed,
                ssl_handshake_failure_observed,
                wrong_server_rejection_observed,
            )
        )
    )

    if api_ready_observed:
        stage = "api_ready"
    elif ibkey_mobile_approval_wait_signal:
        stage = "ibkey_mobile_approval_wait"
    elif second_factor_challenge_observed:
        stage = "second_factor_challenge_observed"
    elif ssl_handshake_failure_observed:
        stage = "ssl_or_regional_server_handshake_failure"
    elif wrong_server_rejection_observed:
        stage = "regional_server_rejected_user"
    elif credential_rejection_observed:
        stage = "credential_rejected"
    elif ccp_silent_timeout_before_ns_auth:
        stage = "ccp_silent_timeout_before_ns_auth"
    elif pre_ns_auth_stall_observed and authorization_rejected_before_ns_auth:
        stage = "authorization_rejected_no_ui_diagnosis"
    elif pre_ns_auth_stall_observed:
        stage = "authentication_stalled_before_ns_auth"
    elif explicit_ccp_lockout_observed:
        stage = "ccp_auth_lockout_backoff"
    elif authorization_rejection_diagnostic_pending:
        stage = "authorization_rejected_observing_ui"
    elif authorization_rejected_before_ns_auth:
        stage = "authorization_rejected_before_ns_auth"
    elif post_authenticate_observed:
        stage = "post_authenticate_before_second_factor"
    elif ns_auth_start_observed:
        stage = "ns_auth_before_second_factor"
    elif maintenance_observed:
        stage = "active_maintenance_or_reset_guard"
    elif controller_internal_twofa_phase:
        stage = "controller_internal_twofa_phase_only"
    elif authenticating_observed or _has(combined, "connecting to server"):
        stage = "authentication_before_second_factor"
    else:
        stage = "pre_auth_or_unknown"

    transcript = _launcher_auth_transcript(launcher)
    return {
        "schema": "mmibkr-ibkr-auth-boundary-v5",
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
        "authorization_rejected_before_ns_auth": authorization_rejected_before_ns_auth,
        "authorization_rejection_diagnostic_pending": authorization_rejection_diagnostic_pending,
        "ccp_lockout_observed": explicit_ccp_lockout_observed,
        "ccp_timeout_observed": ccp_timeout_observed,
        "ccp_silent_timeout_before_ns_auth": ccp_silent_timeout_before_ns_auth,
        "pre_ns_auth_stall_observed": pre_ns_auth_stall_observed,
        "ssl_handshake_failure_observed": ssl_handshake_failure_observed,
        "wrong_server_rejection_observed": wrong_server_rejection_observed,
        "maintenance_observed": maintenance_observed,
        "terminal_prechallenge_blocker": terminal_prechallenge_blocker,
        "authenticating_observed": authenticating_observed,
        "ns_auth_start_observed": ns_auth_start_observed,
        "post_authenticate_observed": post_authenticate_observed,
        "api_ready_observed": api_ready_observed,
        "launcher_connected_host": _connected_host(launcher),
        "launcher_auth_transcript": transcript,
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

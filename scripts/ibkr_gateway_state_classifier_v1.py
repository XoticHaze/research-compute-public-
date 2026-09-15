from __future__ import annotations

"""Sanitize IB Gateway controller logs into fixed login-state booleans/counts.

Supports both legacy IBC and the post-IBC ibg-controller path. This classifier
never emits source log lines, account identifiers, credentials, server names,
or arbitrary matched text. It exists only to distinguish deterministic startup
states while keeping public Actions logs safe.
"""

import json
import sys


def present(text: str, *needles: str) -> bool:
    return any(needle in text for needle in needles)


def count(text: str, needle: str) -> int:
    return text.count(needle)


def main() -> None:
    raw = sys.stdin.read()
    text = raw.lower()

    login_completed = present(
        text,
        "ibc: login has completed",
        "login has completed",
        "login completed",
    )
    configuration_completed = present(
        text,
        "ibc: configuration tasks completed",
        "configuration tasks completed",
        "post-login config applied",
        "post-login configuration applied",
    )
    twofa_initiated = present(
        text,
        "ibc: second factor authentication initiated",
        "second factor authentication initiated",
        "2fa dialog detected",
        "second factor dialog detected",
    )
    twofa_dialog = present(
        text,
        "detected dialog entitled: second factor authentication",
        "2fa dialog detected",
        "second factor dialog detected",
    )
    device_selection = present(
        text,
        "could not find second factor device",
        "select second factor device",
        "multiple second-factor",
        "multiple second factor",
    )

    controller_started = present(
        text,
        "starting gateway controller",
        "ibg-controller",
        "gateway controller",
    )
    controller_input_agent_up = present(text, "input agent is up", "input-agent is up")
    controller_app_registered = present(text, "app registered:", "gateway app registered")
    controller_login_dialog = present(text, "login dialog detected")
    controller_username_set = present(
        text,
        "set_text on text 'username': ok",
        'set_text on text "username": ok',
        "username field set",
    )
    controller_paper_login_clicked = present(
        text,
        "click on push button:'paper log in': ok",
        'click on push button:"paper log in": ok',
        "paper log in': ok",
    )
    controller_api_ready = present(
        text,
        "api port 4002 accepting connections",
        "api port accepting connections",
        "gateway api ready",
        "ready file written",
    )
    ccp_lockout = present(
        text,
        "ccp lockout detected",
        "authtimeoutmonitor-ccp: timeout",
    )
    ccp_backoff = present(text, "ccp backoff:", "ccp backoff")
    stuck_connecting = present(
        text,
        "stuck in 'connecting to server'",
        'stuck in "connecting to server"',
        "connecting to server (trying for another",
    )
    wrong_region_or_server = present(
        text,
        "user is not known here",
        "this user is not known here",
    )
    ssl_handshake_failure = present(
        text,
        "sslhandshakeexception",
        "remote host terminated the handshake",
    )
    passkey_prompt = present(text, "passkey prompt", "passkey authentication", "webauthn")

    result = {
        "schema": "mmibkr-ibkr-gateway-state-v3",
        "controller_started": controller_started,
        "controller_input_agent_up": controller_input_agent_up,
        "controller_app_registered": controller_app_registered,
        "controller_login_dialog_detected": controller_login_dialog,
        "controller_username_set": controller_username_set,
        "controller_paper_login_clicked": controller_paper_login_clicked,
        "controller_api_ready": controller_api_ready,
        "login_dialog_opened": present(text, "login dialog window_opened") or controller_login_dialog,
        "paper_login_clicked": present(text, "click button: paper log in") or controller_paper_login_clicked,
        "read_only_login_initiated": present(text, "initiating read-only login"),
        "loading_window_observed": present(text, "detected frame entitled: loading"),
        "authenticating_window_observed": present(text, "detected frame entitled: authenticating", "authenticating..."),
        "connecting_to_server_observed": present(text, "detected frame entitled: connecting to server", "connecting to server"),
        "starting_application_observed": present(text, "detected frame entitled: starting application"),
        "login_completed": login_completed,
        "configuration_completed": configuration_completed,
        "paper_warning_observed": present(text, "detected dialog entitled: warning"),
        "paper_warning_accepted": present(text, "click button: i understand and accept"),
        "twofa_initiated": twofa_initiated,
        "twofa_dialog_observed": twofa_dialog,
        "security_code_dialog_observed": present(text, "detected dialog entitled: enter security code", "enter security code"),
        "second_factor_device_selection_signal": device_selection,
        "passkey_prompt_signal": passkey_prompt,
        "credential_rejection_signal": present(
            text,
            "invalid username",
            "invalid password",
            "authentication failed",
            "login failed",
            "failed to authenticate",
            "incorrect username",
            "incorrect password",
        ),
        "password_change_signal": present(text, "password expired", "change your password", "password must be changed"),
        "existing_session_signal": present(text, "existing session", "already logged in"),
        "connection_problem_signal": present(
            text,
            "connection failed",
            "unable to connect",
            "server unavailable",
            "server is unavailable",
            "could not connect",
        ),
        "wrong_region_or_server_signal": wrong_region_or_server,
        "ssl_handshake_failure_signal": ssl_handshake_failure,
        "ccp_lockout_signal": ccp_lockout,
        "ccp_backoff_signal": ccp_backoff,
        "stuck_connecting_signal": stuck_connecting,
        "maintenance_signal": present(text, "maintenance", "system is currently unavailable"),
        "api_readonly_setting_observed": present(text, "setting readonlyapi", "read-only api checkbox", "read_only_api"),
        "socat_internal_refused": present(text, "socat") and present(text, "connection refused"),
        "api_connection_reset_count": count(text, "connection reset by peer"),
        "login_attempt_count": count(text, "ibc: login attempt:") + count(text, "login attempt"),
        "container_log_bytes": len(raw.encode("utf-8", errors="replace")),
    }

    if controller_api_ready:
        stage = "api_ready"
    elif login_completed and configuration_completed:
        stage = "gateway_configured"
    elif login_completed:
        stage = "login_completed_configuration_pending"
    elif ccp_lockout or ccp_backoff:
        stage = "ccp_auth_lockout_backoff"
    elif wrong_region_or_server:
        stage = "regional_server_rejected"
    elif ssl_handshake_failure:
        stage = "regional_server_tls_failure"
    elif stuck_connecting:
        stage = "connecting_to_server_stalled"
    elif passkey_prompt:
        stage = "passkey_prompt"
    elif twofa_initiated or twofa_dialog or result["security_code_dialog_observed"]:
        stage = "twofa_in_progress"
    elif result["starting_application_observed"]:
        stage = "starting_application"
    elif result["connecting_to_server_observed"]:
        stage = "connecting_to_server"
    elif result["authenticating_window_observed"]:
        stage = "authenticating"
    elif result["paper_login_clicked"] and result["loading_window_observed"]:
        stage = "paper_login_submitted_loading"
    elif controller_paper_login_clicked:
        stage = "controller_paper_login_submitted"
    elif result["paper_login_clicked"]:
        stage = "paper_login_submitted"
    elif controller_username_set:
        stage = "controller_credentials_entered"
    elif controller_login_dialog:
        stage = "controller_login_dialog_ready"
    elif controller_app_registered or controller_input_agent_up:
        stage = "controller_gateway_registered"
    elif result["login_dialog_opened"]:
        stage = "login_dialog_ready"
    else:
        stage = "startup_before_login_dialog"
    result["stage"] = stage

    print("IBKR_GATEWAY_STATE=" + json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

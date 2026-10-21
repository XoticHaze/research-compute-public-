from __future__ import annotations

"""Fail-closed Cloudflare Access SSH transport for a broker-read-only Gateway.

Cloudflare carries SSH, and SSH carries a *single* local TCP forward.
No IBKR credentials, strategy changes, orders, or live-mutation permissions.
Never print private keys or Access service tokens.
"""

import argparse
import base64
import os
import ipaddress
from pathlib import Path
import re
import stat


HOST_RE = re.compile(r"^(?=.{5,253}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
SSH_PUB_RE = re.compile(r"^ssh-ed25519 [A-Za-z0-9+/=]+(?: [^\r\n]*)?$")


def hostname(value: str) -> str:
    if not isinstance(value, str) or not HOST_RE.fullmatch(value):
        raise ValueError("cf_gateway_exact_hostname_required")
    if value.count(".") < 2 or ".." in value or value.endswith(".workers.dev"):
        raise ValueError("cf_gateway_zone_hostname_required")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        pass
    else:
        raise ValueError("cf_gateway_host_must_be_managed_zone_dns")
    return value


def ed25519_pubkey(value: str) -> str:
    if not isinstance(value, str) or not SSH_PUB_RE.fullmatch(value.strip()):
        raise ValueError("cf_gateway_valid_ssh_ed25519_public_key_required")
    return " ".join(value.strip().split()[:2])


def _decode_env(name: str) -> bytes:
    value = os.getenv(name, "")
    if not value:
        raise ValueError(f"{name}_required")
    try:
        result = base64.b64decode(value, validate=True)
    except ValueError as exc:
        raise ValueError(f"{name}_invalid_base64") from exc
    if len(result) > 16384 or not result:
        raise ValueError(f"{name}_length_rejected")
    return result


def _write_private(path: Path, data: bytes) -> None:
    path.write_bytes(data)
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def setup_gateway(state_dir: Path, *, login_user: str = "runner") -> Path:
    if login_user != "runner":
        raise ValueError("cf_gateway_unrecognized_ssh_user")
    if not os.getenv("MMIBKR_CF_GATEWAY_TUNNEL_TOKEN"):
        raise ValueError("cf_gateway_named_tunnel_token_missing")
    hostname(os.getenv("MMIBKR_CF_SSH_HOSTNAME", ""))
    priv = _decode_env("MMIBKR_CF_GATEWAY_SSH_HOST_KEY_B64")
    if b"BEGIN OPENSSH PRIVATE KEY" not in priv or b"END OPENSSH PRIVATE KEY" not in priv:
        raise ValueError("cf_gateway_host_key_not_openssh")
    authorized = ed25519_pubkey(os.getenv("MMIBKR_CF_READER_SSH_PUBKEY", ""))
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    state_dir.chmod(0o700)
    key = state_dir / "ssh_host_ed25519_key"
    auth = state_dir / "authorized_keys"
    cfg = state_dir / "sshd_config"
    _write_private(key, priv)
    _write_private(auth, (authorized + "\n").encode())
    cfg.write_text(
        "Port 2222\nListenAddress 127.0.0.1\n"
        f"HostKey {key}\nAuthorizedKeysFile {auth}\n"
        f"PidFile {state_dir / 'sshd.pid'}\n"
        "PubkeyAuthentication yes\nPasswordAuthentication no\n"
        "KbdInteractiveAuthentication no\nPermitRootLogin no\n"
        "AllowUsers runner\nUsePAM no\nPermitUserEnvironment no\n"
        "AllowTcpForwarding local\nPermitOpen 127.0.0.1:4001\n"
        "PermitTTY no\nAllowAgentForwarding no\n"
        "X11Forwarding no\nGatewayPorts no\n"
        "ForceCommand /bin/false\n"
        "PrintMotd no\nLogLevel ERROR\n", encoding="utf-8"
    )
    cfg.chmod(0o600)
    return cfg


def setup_reader(state_dir: Path) -> Path:
    name = hostname(os.getenv("MMIBKR_CF_SSH_HOSTNAME", ""))
    if not os.getenv("TUNNEL_SERVICE_TOKEN_ID") or not os.getenv("TUNNEL_SERVICE_TOKEN_SECRET"):
        raise ValueError("cf_access_service_token_pair_missing")
    priv = _decode_env("MMIBKR_CF_READER_SSH_PRIVKEY_B64")
    if b"BEGIN OPENSSH PRIVATE KEY" not in priv or b"END OPENSSH PRIVATE KEY" not in priv:
        raise ValueError("cf_reader_key_not_openssh")
    public = ed25519_pubkey(os.getenv("MMIBKR_CF_GATEWAY_SSH_HOST_PUBKEY", ""))
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    state_dir.chmod(0o700)
    key = state_dir / "reader_ed25519"
    kh = state_dir / "known_hosts"
    cfg = state_dir / "ssh_config"
    _write_private(key, priv)
    _write_private(kh, (name + " " + public + "\n").encode())
    cfg.write_text(
        f"Host {name}\n"
        f"  HostName {name}\n  User runner\n"
        f"  IdentityFile {key}\n"
        f"  UserKnownHostsFile {kh}\n"
        "  StrictHostKeyChecking yes\n"
        "  BatchMode yes\n"
        "  IdentitiesOnly yes\n"
        "  ExitOnForwardFailure yes\n"
        "  ServerAliveInterval 30\n"
        "  ServerAliveCountMax 3\n"
        "  ConnectTimeout 20\n"
        "  ProxyCommand cloudflared access ssh --hostname %h\n",
        encoding="utf-8"
    )
    cfg.chmod(0o600)
    return cfg


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=("gateway", "reader"))
    p.add_argument("--state-dir", required=True)
    a = p.parse_args()
    if a.mode == "gateway":
        cfg = setup_gateway(Path(a.state_dir))
    else:
        cfg = setup_reader(Path(a.state_dir))
    # Public output is the *path*, never secret content.
    print("MMIBKR_CF_SSH_CONFIG_PATH=" + str(cfg))
    print("MMIBKR_CF_SSH_BROKER_PORT_FENCE=127.0.0.1:4001")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

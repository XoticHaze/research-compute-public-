from __future__ import annotations

import base64
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from scripts.mmibkr_cf_ssh_transport_v1 import (
    hostname, ed25519_pubkey, setup_gateway, setup_reader,
)

DUMMY_PRIVATE = base64.b64encode(
    b"-----BEGIN OPENSSH PRIVATE KEY-----\nTEST_FIXTURE_ONLY\n-----END OPENSSH PRIVATE KEY-----\n"
).decode()
DUMMY_PUBLIC = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"

class CloudflareSSHSafetyTests(unittest.TestCase):
    def test_exact_zone_hostname_no_workers_dev_or_shell_injection(self):
        self.assertEqual(hostname("gw.example.net"), "gw.example.net")
        for bad in ("", "127.0.0.1", "gw", "gw.example.com;true", "gw.example.com\n",
                    "gw.workers.dev", "gw..example.com", "https://gw.example.com"):
            with self.assertRaises(ValueError, msg=bad):
                hostname(bad)

    def test_public_key_rejects_non_ed25519_and_injection(self):
        self.assertEqual(ed25519_pubkey(DUMMY_PUBLIC), DUMMY_PUBLIC)
        for bad in ("ssh-rsa AAA", "ssh-ed25519", DUMMY_PUBLIC+"\nCommand /bin/sh"):
            with self.assertRaises(ValueError):
                ed25519_pubkey(bad)

    def test_gateway_only_loopback_ssh_and_exact_port_forward(self):
        cfg_env={
            "MMIBKR_CF_SSH_HOSTNAME":"gw.example.net",
            "MMIBKR_CF_GATEWAY_TUNNEL_TOKEN":"fixture-only",
            "MMIBKR_CF_GATEWAY_SSH_HOST_KEY_B64":DUMMY_PRIVATE,
            "MMIBKR_CF_READER_SSH_PUBKEY":DUMMY_PUBLIC,
        }
        with patch.dict(os.environ,cfg_env,clear=True), tempfile.TemporaryDirectory() as td:
            cfg=setup_gateway(Path(td)/"state")
            text=cfg.read_text()
            self.assertIn("ListenAddress 127.0.0.1",text)
            self.assertIn("AllowTcpForwarding local",text)
            self.assertIn("PermitOpen 127.0.0.1:4001",text)
            self.assertIn("PasswordAuthentication no",text)
            self.assertIn("KbdInteractiveAuthentication no",text)
            self.assertIn("UsePAM yes",text)
            self.assertIn("AuthenticationMethods publickey",text)
            self.assertIn("AllowAgentForwarding no",text)
            self.assertIn("ForceCommand /bin/false",text)
            self.assertNotIn("0.0.0.0",text)
            self.assertEqual(cfg.stat().st_mode & 0o777,0o600)
            self.assertEqual((cfg.parent/"ssh_host_ed25519_key").stat().st_mode & 0o777,0o600)
            self.assertNotIn("fixture-only",text)
            self.assertNotIn("BEGIN OPENSSH PRIVATE KEY",text)

    def test_gateway_requires_explicit_named_tunnel_before_ssh(self):
        with patch.dict(os.environ,{"MMIBKR_CF_SSH_HOSTNAME":"gw.example.net"},clear=True), tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,"named_tunnel_token_missing"):
                setup_gateway(Path(td)/"state")

    def test_reader_uses_pinned_hostkey_and_service_token_not_tofu(self):
        cfg_env={
            "MMIBKR_CF_SSH_HOSTNAME":"gw.example.net",
            "MMIBKR_CF_READER_SSH_PRIVKEY_B64":DUMMY_PRIVATE,
            "MMIBKR_CF_GATEWAY_SSH_HOST_PUBKEY":DUMMY_PUBLIC,
            "TUNNEL_SERVICE_TOKEN_ID":"mock-id",
            "TUNNEL_SERVICE_TOKEN_SECRET":"mock-secret",
        }
        with patch.dict(os.environ,cfg_env,clear=True), tempfile.TemporaryDirectory() as td:
            cfg=setup_reader(Path(td)/"state")
            contents=cfg.read_text()
            self.assertIn("StrictHostKeyChecking yes",contents)
            self.assertIn("BatchMode yes",contents)
            self.assertIn("ProxyCommand cloudflared access ssh --hostname %h",contents)
            self.assertIn("ServerAliveInterval 30",contents)
            self.assertNotIn("StrictHostKeyChecking no",contents)
            self.assertNotIn("mock-secret",contents)
            self.assertEqual((cfg.parent/"known_hosts").read_text(), "gw.example.net "+DUMMY_PUBLIC+"\n")
            self.assertEqual((cfg.parent/"reader_ed25519").stat().st_mode & 0o777,0o600)

    def test_reader_requires_service_token_pair(self):
        with patch.dict(os.environ,{"MMIBKR_CF_SSH_HOSTNAME":"gw.example.net"},clear=True),tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,"service_token_pair_missing"):
                setup_reader(Path(td)/"state")

    def test_manual_broker_login_is_after_cloudflare_transport_preflight(self):
        root=Path(__file__).resolve().parents[1]
        owner=(root/".github/workflows/mmibkr-selected-runtime-live-owner-r1.yml").read_text()
        self.assertIn("pool_transport:",owner)
        self.assertIn("cloudflare_access_ssh",owner)
        self.assertIn("MMIBKR_CF_GATEWAY_BROKER_LOGIN_NOT_YET_REQUESTED=1",owner)
        self.assertLess(owner.index("Establish Cloudflare Access SSH tunnel before any IBKR credential"),
                        owner.index("Materialize canonical exact private source through existing encrypted Fleet vault"))
        self.assertIn('read_only_api=yes', owner)
        self.assertIn("MMIBKR_GATEWAY_ONLY_POOL_READY=1",owner)

    def test_two_independent_reader_modes_use_exact_ssh_forward(self):
        root=Path(__file__).resolve().parents[1]
        readers=(root/".github/workflows/mmibkr-gh-independent-readers-r1.yml").read_text()
        self.assertIn("scripts/mmibkr_cf_reader_start_v1.sh",readers)
        self.assertIn("MMIBKR_CF_SSH_FORWARD_ATTESTED=1",readers)
        self.assertIn("PORT=14001",readers)
        self.assertIn("handoff_ab",readers)
        self.assertIn("single_read",readers)
        self.assertIn("tailscale",readers)

    def test_no_broker_in_network_rehearsal(self):
        root=Path(__file__).resolve().parents[1]
        workflow=(root/".github/workflows/mmibkr-cf-ssh-network-rehearsal-r1.yml").read_text()
        self.assertIn("NETWORK_ONLY_SYNTHETIC_TCP_ECHO_READY=1", workflow)
        self.assertNotIn("fleet_authority_envelope_consumer_v1.py",workflow)
        self.assertNotIn("mmibkr-live-gateway",workflow)
        self.assertNotIn("placeOrder(",workflow)


if __name__=="__main__":
    unittest.main()

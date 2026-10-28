# MM-IBKR Pi Gateway: one-time Cloudflare-sealed credential handoff

Status: reviewed-source candidate; brokerless synthetic tests only. No login or live orders.

## Security and placement

Cloudflare Fleet Authority already holds IBKR_LIVE_USERNAME/PASSWORD/ACCOUNT.
The existing /v1/authorities/ibkr-live-bot/seal endpoint accepts only the
OIDC-authenticated canonical live-owner GitHub workflow. Do not create
a Pi-specific public Cloudflare secret endpoint or store broker passwords
in GitHub/ChatGPT.

The manual-only pi_credentials job in the EXISTING owner workflow does not
start Gateway or bot. It obtains the existing live seal through the original
GitHub OIDC policy, clamps settings to READ_ONLY_API=yes and
ENABLE_LIVE_TRADING=0, encrypts to the registered Pi X25519 public key and
uploads ciphertext only with one-day artifact retention. Normal owner mode
remains unchanged. Pi-local root alone decrypts and atomically installs
an owner-only environment.

Caveat: a GitHub account able to alter main workflow/registered public-key
variable is powerful. This is not a second independently approved human
security domain, and the current Cloudflare policy checks workflow_ref
but does not pin immutable workflow SHA.

## Pi setup (from trusted Mac)

Pi already has /var/lib/mmibkr-gateway/compose.yaml. Use a reviewed exact
source revision for the script. Ensure Pi /usr/bin/python3 can import
cryptography (Debian python3-cryptography package where absent).

    scp scripts/mmibkr_pi_credential_handoff_v1.py cc-pi4:~/mmibkr_pi_credential_handoff_v1.py
    ssh -tt cc-pi4 '
      set -e
      sudo install -d -m 0700 /var/lib/mmibkr-gateway/secrets
      sudo install -m 0755 ~/mmibkr_pi_credential_handoff_v1.py /usr/local/libexec/mmibkr_pi_credential_handoff_v1.py
      rm ~/mmibkr_pi_credential_handoff_v1.py
      sudo /usr/bin/python3 -I /usr/local/libexec/mmibkr_pi_credential_handoff_v1.py init-recipient \
        --private-key /var/lib/mmibkr-gateway/secrets/pi-recipient.key \
        --public-key /var/lib/mmibkr-gateway/pi-recipient.pub.b64
    '

The private key must be root-only 0600. Never upload it or regenerate
while a handoff is in flight. The .pub.b64 key is public.

## Register recipient and dispatch (after review/merge)

    PI_PUB="$(ssh cc-pi4 cat /var/lib/mmibkr-gateway/pi-recipient.pub.b64)"
    gh variable set MMIBKR_PI_RECIPIENT_PUBLIC_B64 \
      -R XoticHaze/research-compute-public- -b "$PI_PUB"
    gh workflow run mmibkr-selected-runtime-live-owner-r1.yml \
      -R XoticHaze/research-compute-public- \
      -f admission_only=true -f warm_handoff_mode=legacy \
      -f pi_credential_handoff=true

The pi_credentials job obtains the Fleet envelope and uploads artifact
mmibkr-pi-encrypted-gateway-<run_id>. No brokerage login is initiated.

With its exact successful workflow RUN_ID:

    gh run download "$RUN_ID" -R XoticHaze/research-compute-public- \
      -n "mmibkr-pi-encrypted-gateway-$RUN_ID" -D ./pi-capsule
    scp ./pi-capsule/mmibkr-pi-credential-envelope.json cc-pi4:~/
    ssh -tt cc-pi4 '
      set -e
      sudo /usr/bin/python3 -I /usr/local/libexec/mmibkr_pi_credential_handoff_v1.py install \
        --private-key /var/lib/mmibkr-gateway/secrets/pi-recipient.key \
        --envelope ~/mmibkr-pi-credential-envelope.json \
        --destination /var/lib/mmibkr-gateway/secrets/live-gateway.env
      rm ~/mmibkr-pi-credential-envelope.json
      sudo stat -c "%U:%G %a %n" /var/lib/mmibkr-gateway/secrets/live-gateway.env
    '

Installer rejects overwriting nonempty credentials, recipient mismatch,
altered ciphertext, paper accounts, and writable API environment.
Do not print, paste or commit secrets.

## Initial Pi Gateway

Verify no competing active brokerage-login-owning Gateway, then:

    ssh -tt cc-pi4 '
      cd /var/lib/mmibkr-gateway
      sudo env MMIBKR_GATEWAY_PRIVATE_BIND_IP=127.0.0.1 \
        docker compose --profile activated-gateway config -q
      sudo env MMIBKR_GATEWAY_PRIVATE_BIND_IP=127.0.0.1 \
        docker compose --profile activated-gateway up -d
      sudo docker ps --filter name=mmibkr-split-live-gateway \
        --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    '

Attend one IB Key prompt if indicated. Docker up is not proof of login.
Require broker managed accounts, positions, all-open-orders and executions
read on the exact expected account before declaring authenticated.

For remote bot compute, create an authenticated private WireGuard or
Cloudflare Access+restricted SSH path; never publish raw TCP/4001.
The Pi has 4 cores and ~3.8GiB RAM: start with the persistent Gateway,
measure Java usage, and place only a lightweight existing canonical bot
there if memory and fencing allow. Keep heavy research/ML remote.
No new order pathway or live-submit permission is added in this change.

## Source checks

Run: python -m unittest tests.test_mmibkr_pi_credential_handoff_v1 -v
Confirm that owner job never runs in handoff mode, pi_credentials cannot
start Gateway, ciphertext never contains plaintext, and temporary files
are deleted on job exit.

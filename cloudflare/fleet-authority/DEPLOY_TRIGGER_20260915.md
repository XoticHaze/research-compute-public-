# Fleet authority deployment contract

Cloudflare Workers deployment is repository-connected from the production branch. A merge that changes `cloudflare/fleet-authority/` is the deployment trigger; there is no recurring operator SHA-pinning step.

## Stable authorization boundary

The Worker authorizes the IBKR paper read-only seal request from the canonical GitHub workload identity:

- GitHub OIDC JWT signature is valid
- issuer is `https://token.actions.githubusercontent.com`
- audience is `mmibkr-fleet-authority`
- repository is `XoticHaze/research-compute-public-`
- ref is `refs/heads/ibkr-b1-authority-v1`
- workflow ref is `XoticHaze/research-compute-public-/.github/workflows/ibkr-cloudflare-readonly-b1-r1.yml@refs/heads/ibkr-b1-authority-v1`
- OIDC `run_id` matches the seal request run id

The moving workflow commit SHA is provenance only. It is **not** an authorization gate and must not require Cloudflare configuration changes after ordinary commits.

The sealed one-run X25519/HKDF/AES-GCM credential envelope remains the credential transport boundary. `/healthz` is liveness only and must not expose mutable authorization configuration or credential-binding detail.

## Steady-state operator expectation

Normal workflow changes on the admitted authority branch do not require a Cloudflare dashboard edit, Wrangler variable update, health-contract update, or one-time phrase. A Cloudflare change is needed only if the stable workload identity itself changes, such as repository, authority branch, workflow path, or OIDC audience.

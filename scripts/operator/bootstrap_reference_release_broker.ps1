# RETIRED original-account direct-deploy bootstrap. It used obsolete endpoint
# and overwrite-prone legacy keygen. It must never perform a real neutral seal.
# See cloudflare/reference-release-broker/INITIAL_SEAL_HANDOFF.md.
param([string]$KeyDir = "")
$ErrorActionPreference = "Stop"
throw "RETIRED_UNSAFE_BOOTSTRAP: no key generation or Cloudflare action. Read the neutral initial-seal handoff and obtain independent administrator approval."

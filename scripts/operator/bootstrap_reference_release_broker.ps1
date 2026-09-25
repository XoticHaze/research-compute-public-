param(
  [string]$KeyDir = (Join-Path $env:USERPROFILE ".secure-compute-reference-v1")
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Wrangler = Join-Path $RepoRoot "cloudflare\reference-release-broker\wrangler.jsonc"
$Keygen = Join-Path $RepoRoot "scripts\operator\reference_broker_keygen.mjs"
$BrokerUrl = "https://reference-release-broker-v1.slenderiq.workers.dev"

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
  throw "Node.js 22+ is required."
}
if (-not (Get-Command npx -ErrorAction SilentlyContinue)) {
  throw "npx is required."
}

New-Item -ItemType Directory -Path $KeyDir -Force | Out-Null
if ((Get-ChildItem -LiteralPath $KeyDir -Force -ErrorAction SilentlyContinue | Measure-Object).Count -gt 0) {
  throw "KeyDir is not empty: $KeyDir. Use a new empty directory for this bootstrap."
}

Write-Host "Generating independent P-256 authority and broker keys locally..."
node $Keygen $KeyDir
if ($LASTEXITCODE -ne 0) { throw "key generation failed" }

$AuthorityPrivate = Join-Path $KeyDir "authority-private.jwk.json"
$AuthorityProtected = Join-Path $KeyDir "authority-private.dpapi"
$BrokerPrivate = Join-Path $KeyDir "broker-private.jwk.json"
$AuthorityPublic = Join-Path $KeyDir "authority-public.b64"
$SignedIntent = Join-Path $KeyDir "signed-intent.json"
$PublicSummary = Join-Path $KeyDir "bootstrap-public.txt"

# Protect the long-lived authority private key with Windows DPAPI, then remove plaintext.
$plain = [System.IO.File]::ReadAllBytes($AuthorityPrivate)
$protected = [System.Security.Cryptography.ProtectedData]::Protect(
  $plain, $null, [System.Security.Cryptography.DataProtectionScope]::CurrentUser
)
[System.IO.File]::WriteAllBytes($AuthorityProtected, $protected)
Remove-Item -LiteralPath $AuthorityPrivate -Force
[Array]::Clear($plain, 0, $plain.Length)

Write-Host ""
Write-Host "Cloudflare login will open a browser. This is the independent admin path; do not export this login/token to GitHub."
npx --yes wrangler@4.135.0 login
if ($LASTEXITCODE -ne 0) { throw "Cloudflare login failed" }

Write-Host "Deploying the generic broker..."
npx --yes wrangler@4.135.0 deploy --config $Wrangler
if ($LASTEXITCODE -ne 0) { throw "broker deployment failed" }

Write-Host "Binding broker private signing key..."
Get-Content -LiteralPath $BrokerPrivate -Raw |
  npx --yes wrangler@4.135.0 secret put BROKER_SIGNING_PRIVATE_JWK --config $Wrangler
if ($LASTEXITCODE -ne 0) { throw "broker signing-key binding failed" }

Write-Host "Binding authority public verification key..."
Get-Content -LiteralPath $AuthorityPublic -Raw |
  npx --yes wrangler@4.135.0 secret put AUTHORITY_PUBLIC_B64 --config $Wrangler
if ($LASTEXITCODE -ne 0) { throw "authority public-key binding failed" }

Write-Host "Binding one-time offline-signed intent..."
Get-Content -LiteralPath $SignedIntent -Raw |
  npx --yes wrangler@4.135.0 secret put BOOTSTRAP_SIGNED_INTENT_JSON --config $Wrangler
if ($LASTEXITCODE -ne 0) { throw "signed-intent binding failed" }

$health = Invoke-RestMethod -Method Get -Uri "$BrokerUrl/healthz"
if ($health.ok -ne $true) { throw "broker health proof failed" }

$remoteKey = Invoke-RestMethod -Method Get -Uri "$BrokerUrl/v1/public-key"
$summary = @{}
Get-Content -LiteralPath $PublicSummary | ForEach-Object {
  if ($_ -match '^([^=]+)=(.*)$') { $summary[$matches[1]] = $matches[2] }
}
if ($remoteKey.key_id -ne $summary["BROKER_KEY_ID"]) {
  throw "broker public-key proof mismatch"
}

# Cloudflare now holds the broker signing key; remove the local plaintext copy.
Remove-Item -LiteralPath $BrokerPrivate -Force

Write-Host ""
Write-Host "REFERENCE_BROKER_BOOTSTRAP_PASS=1"
Write-Host "BROKER_URL=$BrokerUrl"
Write-Host "GRANT_ID=$($summary['GRANT_ID'])"
Write-Host "BROKER_KEY_ID=$($summary['BROKER_KEY_ID'])"
Write-Host "HARNESS_SHA=$($summary['HARNESS_SHA'])"
Write-Host "SIGNED_INTENT_FILE=$SignedIntent"
Write-Host "PUBLIC_SUMMARY_FILE=$PublicSummary"
Write-Host "AUTHORITY_PRIVATE_LOCAL=$AuthorityProtected"
Write-Host ""
Write-Host "Keep the DPAPI authority file private. Do NOT upload the KeyDir or paste any private JWK."
Write-Host "It is safe to paste signed-intent.json and bootstrap-public.txt back into the private project chat."

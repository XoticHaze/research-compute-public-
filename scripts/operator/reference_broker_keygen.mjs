// RETIRED: this original-account synthetic bootstrap minted outdated harness
// authority and broker identities, and silently overwrote local key material.
// It must not be invoked for an initial neutral release-broker seal.
// Current protected procedure: cloudflare/reference-release-broker/INITIAL_SEAL_HANDOFF.md
// Current create-once helper: scripts/operator/reference_release_keygen.mjs
throw new Error('RETIRED_UNSAFE_KEYGEN: use independently approved create-once reference_release_keygen.mjs; no key material generated');

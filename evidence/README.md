# Evidence inputs

SentinelX accepts only immutable HTTPS raw-GitHub commit resources (or a later equally strong representation). Branches, mutable refs, path aliases, malformed commits, and publisher mismatches are rejected.

This directory intentionally contains no fabricated CI, security, or transaction evidence. Use `scripts/build_evidence.py` to build an envelope from real published facts.

Every envelope binds `schema`, `kind`, `evidence_id`, `issuer`, `target`,
`parent_sha256`, `candidate_sha256`, `policy_fingerprint`, `published_at`, and
`expires_at`. CI envelopes additionally contain the seven required boolean
gates; security envelopes contain `verdict` and `independent_review`.

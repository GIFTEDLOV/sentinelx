# SentinelX

SentinelX is a semantic release-security and governance layer for multiple GenLayer Intelligent Contracts. A protected target can only install a candidate after exact source binding, authenticated CI evidence, proposal-bound evidence capture, deterministic envelope validation, independent semantic review, finalized authorization, and exact post-install reconciliation. External security attestation is an explicit target policy: `OPTIONAL` or `REQUIRED_INDEPENDENT`.

Phase 1 targets GenLayer Studio-dev and Consensus v0.6 RC. Phase 2A adds
fee-profile preparation, fail-closed deployment/lifecycle tooling, persistent
transaction journaling, a public CI evidence workflow, and an independent
security-review packet generator. Phase 2B also includes a disposable,
non-canonical Studio-dev profiling run; canonical SentinelX deployment and
security registration remain untouched. Phase 2F introduces the pre-canonical
SentinelX V2 snapshot architecture; V1 remains historical at commit
`7e3b552c8b0471db0411206fdbc743dd12ef4e80`.

## Network and toolchain

| Component | Pinned version / value |
| --- | --- |
| Network | `studio-dev` |
| RPC | `https://studio-dev.genlayer.com/api` |
| Chain ID | `61997` |
| GenLayer CLI | `0.40.0-rc.3` |
| GenLayerJS | `2.0.0-rc.1` |
| GenLayerPY | `0.19.0rc2` |
| GLTest | `0.30.0rc2` |
| GenVM linter | `0.11.0` |

The matching release-candidate components are pinned in `requirements.txt`. No Bradbury or stable Studionet component is used.

## Commands

```powershell
python -m pytest tests/direct -q
python scripts/preflight.py
python scripts/build_v2_source_manifest.py --check
python scripts/studio_dev_v2_deploy.py
python scripts/studio_dev_lifecycle.py plan
```

The preflight script is fail-closed and only writes
`artifacts/preflight-pass.json` after every deterministic gate succeeds. The
The historical V1 disposable profile is preserved under `artifacts/v1/` and is
not authoritative for V2. V2 deployment tooling defaults to a read-only source
manifest gate; no chain write is performed by the source freeze.

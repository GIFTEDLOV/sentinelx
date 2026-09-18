# SentinelX

SentinelX is a semantic release-security and governance layer for multiple GenLayer Intelligent Contracts. A protected target can only install a candidate after exact source binding, authenticated CI evidence, proposal-bound evidence capture, deterministic envelope validation, independent semantic review, finalized authorization, and exact post-install reconciliation. External security attestation is an explicit target policy: `OPTIONAL` or `REQUIRED_INDEPENDENT`.

Historical Studio-dev/V2, V2.1, and V2.2 qualification work remains in Git
history, including the provider/liveness investigation. The first authorized
canonical release is SentinelX V2.3 on Studionet. Disposable qualification
addresses remain historical evidence and are never used as production
configuration.

## Network and toolchain

| Component | Pinned version / value |
| --- | --- |
| Network | `Studionet` |
| RPC | `https://studio.genlayer.com/api` |
| Chain ID | `61999` |
| GenLayerJS | `1.1.8` |
| GenLayerPY | `0.18.0` |
| GLTest | `0.29.2` |
| GenVM linter | `0.11.0` |
| GenVM runner | `v0.2.12` |

The stable compatibility components are pinned in `requirements.txt` and the
Studionet source manifest. No new qualification writes target Studio-dev.

## Canonical release

Canonical governor: `0xb28b8E7F8930b4bd7Ed8572dA7e51AA4ca9D7cA8`  
Canonical protected target: `0xaF9ABA4DD9869d5F92EeA92c700E5f09A6978e21`  
Safe candidate: `1073b34f141b9dc5ba689ef3d98293fd628e30695dbd9092a9c6ecaba3d8c27d`  
Final state: proposal `1` `VERIFIED`, with persistent state and upgrade
authority preserved. The semantic review was `14/14 TRUE`, `APPROVE`, and used
zero review-time web fetches. Compact capture output was 827 bytes.

The qualified unsafe candidate was rejected in a disposable profile and was
not installed. OPTIONAL security mode does not claim an external audit.
Canonical provenance and transaction evidence are in
[`deployments/studionet/v2.3/CANONICAL_DEPLOYMENT.json`](deployments/studionet/v2.3/CANONICAL_DEPLOYMENT.json)
and [`docs/FINAL_SUBMISSION.md`](docs/FINAL_SUBMISSION.md).

## Commands

```powershell
python -m pytest tests/direct -q
python scripts/studionet_preflight.py
python scripts/validate_studionet_v23_semantics.py
python scripts/v2_mutation_runner.py
```

The stable preflight is fail-closed and targets Studionet 61999. The historical
V1 and disposable profile artifacts remain preserved and are not authoritative
for the canonical release.

# SentinelX toolchain

SentinelX is pinned to the Studio-dev/v0.6 RC family. The selected published
versions are:

| Tool | Version |
| --- | --- |
| GenLayer CLI | `0.40.0-rc.3` |
| GenLayerJS | `2.0.0-rc.1` (selected for Phase 2; frontend intentionally deferred) |
| GenLayerPY | `0.19.0rc2` |
| GLTest | `0.30.0rc2` |
| GenVM static linter | `0.11.0` |
| GenVM semantic linter | `0.11.1rc2` |
| Semantic runner | `v0.6.0-rc5` |

The canonical network is Studio-dev, RPC `https://studio-dev.genlayer.com/api`,
chain ID `61997`. Studionet and other networks are out of scope.

The version family was selected from the official [v0.6 migration
guide](https://docs.genlayer.com/developers/consensus-v06-migration) and the
[network configuration](https://docs.genlayer.com/developers/networks). The
selected SDK/CLI versions are recorded in `requirements.txt` and
`gltest.config.yaml`; JavaScript installation is deferred with the frontend.

The v0.6 write standard is represented in `scripts/fee_aware_transaction.py`:
future callers must use a complete SDK estimate and carry its `distribution`
and `feeValue` values unchanged. They broadcast exactly once, persist that
transaction hash immediately, and prove finalized lifecycle, successful
execution, and expected contract state before taking the next action. The
static AST gate and semantic GenVM gate are intentionally separate; the exact
semantic pairing is exercised by the V2 CI workflow.

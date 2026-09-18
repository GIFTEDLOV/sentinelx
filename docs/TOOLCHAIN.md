# SentinelX stable toolchain

The canonical SentinelX V2.3 release uses the pinned stable compatibility
family below:

| Tool | Version |
| --- | --- |
| GenLayerJS | `1.1.8` |
| GenLayerPY | `0.18.0` |
| GLTest | `0.29.2` |
| GenVM static linter | `0.11.0` |
| GenVM runner | `v0.2.12` |
| py-genlayer runner | `1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6` |
| stdlib | `11rhn002yfajawsz7fai6mykznbxkxs6l91iskj5cm82c92qhy3v` |

The canonical network is Studionet, RPC `https://studio.genlayer.com/api`,
chain ID `61999`. Studio-dev 61997 is historical qualification evidence only.

The selected SDK versions are recorded in `requirements.txt`,
`gltest.config.yaml`, and `deployments/studionet/v2.3/SOURCE_MANIFEST.json`.

Canonical writes use the stable SDK-native fee model, current network policy,
single-broadcast journaling, immediate hash persistence, and same-hash
reconciliation. Every parent and internal child must reach `FINALIZED` plus
`FINISHED_WITH_RETURN`. The static and semantic gates remain separate; the
exact qualified results are recorded in the Studionet readiness manifest.

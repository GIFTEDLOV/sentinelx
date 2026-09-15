# SentinelX V2 console

The Phase 2B console is a Next.js App Router application for semantic release
security on GenLayer Intelligent Contracts. It uses GenLayerJS `2.0.0-rc.1`
against Studio-dev (`61997`) and keeps the fee-aware, single-broadcast,
same-hash reconciliation standard documented in `../docs/TOOLCHAIN.md`.

## Local development

```powershell
npm install
npm run dev
```

The production console never substitutes fixtures for unavailable chain data.
For isolated visual development only, set
`NEXT_PUBLIC_SENTINELX_PREVIEW=true` in a development environment. Preview
content is labelled and is not used by write adapters.

Optional runtime configuration:

```text
NEXT_PUBLIC_GENLAYER_RPC_URL=https://studio-dev.genlayer.com/api
NEXT_PUBLIC_SENTINELX_GOVERNOR_ADDRESS=
NEXT_PUBLIC_SENTINELX_CANONICAL_TARGET_ADDRESS=
```

The address fields are intentionally empty until a real deployment exists.
Write quoting does not require a fee profile. A matching measured entry is
preferred; otherwise genlayer-js uses the live network-default quote, and an
explicit development flag can select the concrete write simulation estimator.
Gasless behavior is taken from the returned estimate, never inferred from the
network name. Production policy may still require measured coverage for
high-consequence operations.

The historical V1 fee profile is preserved in `../artifacts/v1/` and is not
served or used as a V2 production profile. A future V2 measured profile may be
configured only after fresh V2 profiling.

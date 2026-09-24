# SentinelX V2 console

The SentinelX console is a Next.js App Router application for semantic release
security on GenLayer Intelligent Contracts. The canonical production app uses
GenLayerJS `1.1.8` against Studionet (`61999`) and reads the verified
canonical governor/target from production environment configuration.

## Local development

```powershell
npm install
npm run dev
```

The production console never substitutes fixtures for unavailable chain data.
For isolated visual development only, set
`NEXT_PUBLIC_SENTINELX_PREVIEW=true` in a development environment. Preview
content is labelled and is not used by write adapters.

Runtime configuration:

```text
NEXT_PUBLIC_GENLAYER_RPC_URL=https://studio.genlayer.com/api
NEXT_PUBLIC_SENTINELX_GOVERNOR_ADDRESS=0xb28b8E7F8930b4bd7Ed8572dA7e51AA4ca9D7cA8
NEXT_PUBLIC_SENTINELX_CANONICAL_TARGET_ADDRESS=0xaF9ABA4DD9869d5F92EeA92c700E5f09A6978e21
NEXT_PUBLIC_SENTINELX_PREVIEW=false
NEXT_PUBLIC_SENTINELX_FEE_PROFILE_URL=<immutable raw GitHub URL>
```

The production deployment uses the canonical addresses above; disposable
profile addresses are never substituted. Stable Studionet is gasless, so the
console presents no charged protocol fee. `eth_estimateGas`, when retained for
write preflight, is labeled as a native network-resource observation only;
application value remains a separate concept. Write quoting does not require a
fee profile, but the immutable qualified Studionet profile is configured for
operator visibility.

The historical V1 and disposable profile data are not served as production
fixtures.

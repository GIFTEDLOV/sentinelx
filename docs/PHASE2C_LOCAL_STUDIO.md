# Phase 2C Local Studio Audit — historical context

Phase 2C did not cross the canonical deployment boundary. No Studio-dev
transaction, local profiling transaction, or fee profile was created.

## Tooling and network observations

- GenLayer CLI: `0.40.0-rc.3`
- Docker Desktop: `4.74.0 (227015)`
- Docker Engine: `29.4.3`, Linux/amd64
- Official hosted release preview: `studio-dev`, RPC
  `https://studio-dev.genlayer.com/api`, chain `61997`
- Official Localnet endpoint: `http://localhost:4000/api`, expected chain
  `61127`

The installed CLI lists `studio-dev` and selected it correctly for hosted
configuration. It also reports Localnet support beginning at `v0.65.0`.

## Attempts and findings

1. The existing `v0.123.0-rc.6` JSON-RPC container failed readiness with
   `missing field extra_tld`, and its RPC closed requests. The matching
   `yeagerai/simulator-hardhat:v0.123.0-rc.6` image was not available from the
   configured Docker registry, so this was not a complete Local Studio.
2. The official CLI flow was reset in its GenLayer-local scope and started with
   the explicitly supported `v0.65.0` image set. JSON-RPC, Hardhat, WebDriver,
   Postgres, and Studio UI became healthy, but an RPC `eth_chainId` read
   returned `0xf22f` (`61999`). This is not the required Localnet chain and
   was not used for profiling.
3. GLSim remains excluded because its fee configuration is disabled/zero
   priced and it does not provide the required finalized receipt accounting.

The historical investigation suggested obtaining a coherent v0.6 RC Local
Studio image set that reports chain `61127`. That is no longer a V2 blocker:
Studio-dev itself is the allowed fee-reporting environment, and SDK estimates
are valid during development/profiling without a completed profile. No local
Docker investigation is required for the V2 source freeze.

References:

- https://docs.genlayer.com/developers/networks
- https://docs.genlayer.com/developers/intelligent-contracts/tooling-setup
- https://pypi.org/project/genlayer-test/0.30.0rc2/

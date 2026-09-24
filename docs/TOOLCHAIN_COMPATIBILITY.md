# Stable toolchain compatibility

Audit date: **2026-09-24**

The current official stable guidance still identifies Studionet as the hosted
stable environment at `https://studio.genlayer.com/api`, chain `61999`.
Studio-dev `61997` and the v0.6 fee machinery are release-candidate tooling and
are not part of SentinelX V2.3.

Official sources consulted:

- [Builders / developer resources](https://docs.genlayer.com/developers)
- [Full documentation](https://docs.genlayer.com/full-documentation.txt)
- [GenLayer Skills repository](https://github.com/genlayerlabs/skills), audited at commit `195deb417c2ac4a90dd23429a0c3940bde80389a`
- `genlayer-dev/write-contract`
- `genlayer-dev/genvm-lint`
- `genlayer-dev/direct-tests`
- `genlayer-dev/integration-tests`
- `genlayer-dev/genlayer-cli`
- [GenLayerJS API reference](https://docs.genlayer.com/api-references/genlayer-js)

## Decision

No naturally compatible replacement pair is published in the stable family as
of the audit date. PyPI still publishes `genlayer-py==0.18.0` as the latest
stable SDK and `genlayer-test==0.29.2` as the latest stable test suite, while
`genlayer-test==0.29.2` declares the incompatible metadata range
`genlayer-py>=0.13,<0.17`.

SentinelX therefore preserves the proven stable pairing and records the
metadata exception explicitly rather than downgrading the deployed release
family or moving to the RC stack:

| Component | Exact version |
| --- | --- |
| `genlayer-py` | `0.18.0` |
| `genlayer-test` / `gltest` | `0.29.2` |
| `genvm-linter` | `0.11.0` |
| GenVM runner bundle | `v0.2.12` |
| `genlayer-js` | `1.1.8` |
| `py-genlayer` runner | `1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6` |
| `py-lib-genlayer-std` | `11rhn002yfajawsz7fai6mykznbxkxs6l91iskj5cm82c92qhy3v` |

## Deterministic installation

Use Python 3.12 and install in this exact order:

```powershell
python -m pip install --upgrade pip
python -m pip install --requirement requirements-release.txt --constraint constraints-release.txt
python -m pip install --no-deps --constraint constraints-release.txt genlayer-test==0.29.2
```

The second command is the only metadata exception. All of the test suite's
declared runtime dependencies are already installed and pinned by the first
command and the constraints file. `scripts/verify_toolchain_compatibility.py`
then imports `genlayer_py` and `gltest`, verifies the Direct Mode fixtures and
`VMContext` cheatcodes SentinelX relies on, checks the loader signatures, and
confirms the frozen contract runner header.

`DEPENDENCY_METADATA_EXCEPTION_USED=YES` is intentional and must remain
visible in release reports until upstream publishes a compatible stable pair.

The proof is an API/import compatibility assertion only; it does not deploy,
write to Studionet, or invoke a chain transaction. Direct tests, linter checks,
schema extraction, typechecks, and the semantic AST gate remain separate CI
requirements.

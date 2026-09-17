# SentinelX V2.1 deployment candidate

V2.1 is the corrected first-canonical candidate after disposable V2 profiles
exposed an asynchronous state-machine defect, an OPTIONAL empty-string GenVM
v0.6 wire mismatch, and unsupported nested dynamic-array storage. The failed
V2.1 registration attempts are preserved as pre-canonical evidence; they are
not production environments.

The source manifest binds the exact four contract byte hashes to Studio-dev
chain `61997`. The V2 profile and readiness files are preserved under
`deployments/v2/historical/`; neither the failed V2 profile nor this V2.1
profile is canonical.

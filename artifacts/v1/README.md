# SentinelX V1 profile evidence — historical only

The files in this directory were measured against the pre-canonical
SentinelX V1 contracts on Studio-dev chain 61997. They are preserved to keep
the profiling provenance auditable, but they are not authoritative for V2 and
must not be configured as a V2 production fee profile.

The successful profile observations were the V1 governor deployment, V1
`protected_app_v1` deployment, and `set_protected_value`. The target deployment
had one finalized `FINISHED_WITH_ERROR` attempt followed by one corrected
finalized `FINISHED_WITH_RETURN` attempt; the failed attempt is negative
evidence and was not rebroadcast.

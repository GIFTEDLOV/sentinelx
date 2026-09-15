# Generated artifacts

This directory contains generated local artifacts. The fail-closed preflight
script writes `preflight-pass.json` only after deterministic gates pass.

`artifacts/v1/` contains the historical SentinelX V1 Studio-dev fee profile
and its coverage record. It is preserved for provenance only and must not be
used as a V2 production profile.

Future V2 deployment journals are explicitly separate from the historical
profile evidence. No canonical SentinelX deployment is implied by any file
in this directory.

# Generated artifacts

This directory contains generated local artifacts. The fail-closed preflight
script writes `preflight-pass.json` only after all deterministic gates pass.
The disposable Studio-dev profiling runner writes its transaction journal here;
the journal contains only the explicitly labeled `NON_CANONICAL_PROFILE_ONLY`
run and is not canonical deployment evidence.

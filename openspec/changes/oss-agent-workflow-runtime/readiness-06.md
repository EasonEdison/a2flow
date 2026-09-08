# AF06-D1/D2 readiness

Status: NO READY. Partial DeepSeek source plus reproducible fixed SDK blockers.

- Closed trusted configuration, lazy SDK factory, native content view:12 core/config
  tests PASS0.003s (before installation, no source change since those tests).
- AF06-D2 exact dependency install:69 unique, only approved5 added, original64
  unchanged; full wheel hashes, pip check and import paths PASS. main-brain accepted.
- Actual SDK synthetic HTTP ingress/SSE/native serialization:5 characterization
  tests PASS1.034s, including2 known-gap tests that reproduce blocking loss.
- BLOCKER: unknown HTTP message/choice/response fields and SSE delta extension lost
  before native messages. No verified raw-payload retention seam implemented.
- BLOCKER: tools-enabled next SDK request omits reasoning_content from BOTH prior
  assistant turns (one no-tool, one tool-call), despite successful native round trip.
- Actual DeepSeek harness matching/admission/Finalizer/stop: next bounded test;
  existing production assembly unchanged.
- Public seam fix: requires main-brain review, not implemented.
- Real provider/credentials, PG, UI, listeners and deployment: NOT RUN / out of scope.

Characterization PASS is not compatibility acceptance. Worker-only fixed source is
for main-brain review; no main/GitHub integration or automatic provider fallback.

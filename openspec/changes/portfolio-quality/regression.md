# Regression

Validated on 2026-10-20 against the combined candidate. The owner excluded full unit suites; no existing business workflow was replayed.

| Check | Observed result / scope |
| --- | --- |
| Repository checker | 344 tracked/unignored Python sources parsed; 87 current entry-document local links resolved; direct Runtime-to-product imports rejected; current frontend manifests valid |
| Compose | Current Java, Python execution and combined management override all passed `config --quiet` with temporary synthetic configuration; no service started |
| Management frontend | Fresh `npm ci`, TypeScript check and Vite build passed |
| Business frontend | Fresh public-registry `npm ci`, TypeScript check and Vite build passed; final fixture copy also rebuilt after clarity fix |
| Java | JDK 17 / Maven compile passed, 604 Java source files; existing deprecation/unchecked warnings remain |
| Authentication probe | Candidate functions in an isolated ASGI app: eight malformed-token cases rejected; all three auth write handlers synchronous; 200ms synthetic password work did not block a 26ms event-loop heartbeat; existing framework worker capacity 40 |
| Lifecycle probe | Real Runner/Lifecycle with in-memory adapters: setup failure and execution failure end FAILED; late errors preserve STOPPED/SUCCEEDED without a contradictory failure event; repeated control ID causes one factory call and no business operation |
| Browser | Documented local fixture URL opened; simulation label visible; required choice enables submission; selection transitions to fixture completion; refresh resets to waiting; final UI explicitly states that it is local and does not persist/call services |
| Workflow YAML | Both workflow definitions parsed; full-SHA official actions and read-only token permissions inspected |

The auth and lifecycle probes do not access real accounts, databases, models or business services. They are not public-runtime or database-failover proof. A fresh full-stack installation and event/state atomicity remain unresolved.

The B build reports an existing large-chunk warning (main bundle about 860 kB minified / 259 kB gzip). Compilation succeeds; no page-load or throughput benchmark is inferred. Dependencies were installed in independent source-export directories, not reused from the deployed build.

GitHub workflows now express the source gates. Local equivalent checks are recorded here; current hosted CI status is available in the repository Actions page and must be checked separately. This change does not claim that adding a workflow alone means its hosted run succeeded.

# Personal workflow planning quality

The B-side planner receives each Skill's currently published instructions and declaredDependencies. Dependencies describe available capabilities, not guaranteed execution. Plan the fewest nodes necessary for the user's goal and reuse prior results for the same goal, inputs and time. Different inputs, different times and explicit repeat requests remain valid.

Published Skill behavior is not changed by displayName or nodePrompt. A lookup Skill cannot become summary-only by renaming it. Ordinary summaries of existing fields belong in the built-in summaryPrompt, not an additional business node. For a browse-and-lookup goal, a lookup Skill and a direct lookup capability are alternative implementations unless the requirement actually needs both.

There is no runtime deduplication, automatic plan deletion, save retry or mutation of previously saved immutable workflows.

## Evidence

The initial dependency-enrichment and reuse guidance at 3474c44 did not resolve the live case: a fresh identical request in Chat48 selected a direct lookup followed by a lookup Skill renamed summary. This failed comparison is retained; it was saved but never run.

The follow-up at b61d4f1 explicitly clarified Skill semantics and built-in summaries. The exact original request, without user-message hints about deduplication, produced Chat49 with two business nodes: browse Skill, lookup Skill, followed by the built-in summary. The previous accepted workflow had three business nodes including a redundant direct lookup. Existing definitions were unchanged.

The real AssetReader/native tool dependency projection probe and thirteen scoped offline checks passed, as did static checks and exact outgoing secret scans. Unit tests were waived. B alone was deployed at b61d4f1; the workflow execution service and frontend were unchanged.

Live run a71a9dc6a6f348679abb913dc9113846 completed all three nodes after one accepted temporary-input submission. Actual returned business calls were list once and resolve once, for demo-person-003 (fictional person, age 24). The built-in summary had zero business tool calls. Before/after full refresh execution evidence was identical (fingerprint c43eeaa62b2aebfa3d7c1e3c62699b128dfeb4d9938aac59b7456d1baf295e38); no added query or submission occurred. This guidance improves model planning; it is not a deterministic guarantee that every future generated workflow is optimal.

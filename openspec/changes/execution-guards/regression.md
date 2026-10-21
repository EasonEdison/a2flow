# Execution guards regression

## Verified build and CI

Integrated candidate `dd73ce8a60493ab6030fcf75f1073e390e375b47` passed the real GitHub core probes, project checks and Python quality workflows. Local combined verification passed account concurrency (32 processes, 7 admitted and 25 rate-limited), outbox (15), actual Python executor/PostgreSQL (70), Chat (227), native Workflow (41), A2UI preflight (38), Java approval/PostgreSQL (41), and archive restoration (107).

Initial deployment exposed two integration gaps: Java's explicit Spring configuration did not import the new approval components, and installed Python protobuf modules took precedence over the source overlay. Management was restored to its previous deployment while the explicit import was repaired; B/Runtime mounts now replace the complete generated protocol package. No approval bypass or automatic business retry was introduced.

The Java fix was integrated as `ac776416302c01477c281bd2bc1bc949e4f7f2c3`. A new probe first reproduced the old missing-bean failure, then started the real production Spring configuration with PostgreSQL and gRPC lifecycle (8 checks). JDK 17 compiled 611 Java sources; 574 build inputs matched the committed source. [GitHub core probes](https://github.com/EasonEdison/a2flow/actions/runs/39419978104) and [project checks](https://github.com/EasonEdison/a2flow/actions/runs/39419978087) passed. Python quality was path-filtered for this Java/probe-only follow-up, not rerun.

## Deployment

Explicit additive migration V003 created durable approval consumption. The actual execution reader has only SELECT/INSERT on this table, not UPDATE/DELETE; other reads retain their read-only connection policy. Management runs the repaired build; execution/B/Runtime run the preceding candidate with identical relevant production code. Each launch preserves the actual previous image, secrets, resource budgets and rollback manifest. Management's repaired process is running with restart count zero; public HTTPS management and employee pages return 200.

## Public acceptance so far

- Workflow missing input was submitted after a full-page refresh. It then waited on a separate host-authored write-confirmation card. At that point both consumption and the new business project count were zero.
- The confirmation card survived another refresh. One explicit approval caused one `content.project.create`, one consumed receipt, successful summary and completion notification. Both continuation controls completed; three notification events and two resume outbox entries completed. No test schedule was enabled.
- Chat's actual host confirmation caused one project creation and exactly one continuation message pair. The assistant automatically summarized the saved business result. The model initially rendered an unnecessary ordinary confirmation form; that form did not authorize the actual write. Tool guidance now delegates approval to the host and forbids extra model-generated approval forms.
- An independent minimal Skill was restored through the normal registered PRT Build source. The UI confirmed restored files/bindings; its single file and digest were unchanged. Existing assets were not reset. Malformed archive and arbitrary URL rejection remain isolated-probe evidence, not public attack attempts.
- The previous 37 runtime records have the same ordered-document checksum immediately before/after the new acceptance run; five existing schedules remain disabled. The earlier baseline SHA256 serialization was not recovered, so no equality to that different digest is asserted.

The remaining A2UI public check was completed on 2026-10-21; see final acceptance below.

## Boundaries

Receipt consumption is durable dispatch admission, not an exactly-once guarantee for an external business service. Unknown outcomes remain non-retryable automatically. Normal missing-input submissions and model-created forms are not write authorization. A changed publication or arguments after confirmation is rejected, not silently substituted. Trusted host identity and existing RPC authentication remain part of the boundary.


## Final source and serving state (2026-10-21)

Final application revision: `2811b40757c5be560a4a49245821c8e46517bc1f`. The frozen RPC mapping fix uses the existing JSON conversion; real PreparedAction/nested frozen values are covered by 243 targeted checks. Actual GitHub runs all passed: [core probes](https://github.com/EasonEdison/a2flow/actions/runs/39421312347), [project checks](https://github.com/EasonEdison/a2flow/actions/runs/39421312870), [Python quality](https://github.com/EasonEdison/a2flow/actions/runs/39421312430).

B/Runtime serve 2811b40; management serves ac77641; execution serves dd73ce8. Later changes do not modify management/execution production inputs. All four processes are running, with zero restarts and no OOM. M/B HTTPS return 200. Five schedules remain disabled.

READ compatibility is confirmed by the real content.project.get tool success without an approval card; the next write requested its own host confirmation. The original A2UI card remains WAITING_ACTION with no active request. Final same-card submission, approval, continuation and refresh-dedup still require public acceptance. The browser session expired overnight; normal account-owner login is required. No session forgery, credential reset, or database mutation substitutes for this check.


## Final A2UI public acceptance (2026-10-21): PASS

After normal owner login, the original reading-selection card was submitted once with two selected points. The same card displayed host-authored approval for the actual reading-confirmation arguments. One explicit confirmation produced one saved business confirmation and one consumed approval receipt. The card returned to its original Java RPC protocol and COMPLETED state, with inputs disabled.

The assistant automatically continued from that saved result. A full page reload preserved the completed card, the single business confirmation and consumed receipt, and exactly one user/assistant continuation pair. The next proposed topic-plan write remained unconfirmed and was not dispatched; it is outside this acceptance scope. No account or database bypass was used.

Together with the earlier Workflow, Chat, READ, package-restore and CI evidence, all scoped acceptance gates are now PASS. This documentation-only closure does not require a new deployment.

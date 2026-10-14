# Regression evidence

Date: 2026-10-14. Scoped PRT acceptance passed using registered read-only synthetic demonstration APIs. All public assets were created through normal management UI or conversation tools; no database fixtures substituted for these gates.

## Publication

- Manual capability-only workflow `wf_a2baaefeef55438da0dcdb0b1c41d1a3`: fixed capability followed by summary. Published PRT v1 as `build_31be03ae1e60487e87a3fe02b920bf4b`, deployment `deployment_1e169baedf93472fa121e058174325f6`.
- Conversational mixed workflow `wf_8c92c0f2b7f94803af1314a344117f08`: browse Skill, fixed capability, summary. Normal conversation completed 17 tools including create/save/preview/publish/readback. Published PRT v1 as `build_87199e77005c49308cb9bd953e5feffb`, deployment `deployment_4b36e1ffdb474cfc9f59016b2a84214b`.
- Publication and effective runtime materials were independently read back. Existing dependency version timestamps precede these workflow publications; no dependency republishing was required. No ONLINE publication.

## Public execution

| Gate | Run | Evidence |
| --- | --- | --- |
| Missing input, one submission, automatic continuation | `5552ce61efd447d9a2c018d5e7e16672` | 1 temporary card, 1 successful action, 1 fixed capability call. Two nodes SUCCEEDED; 4 MODEL + 1 ACTION + 1 TOOL + 2 NODE + 1 FINALIZER = 9 RETURNED facts. Two submitted synthetic identifiers produced two real results and the matching final summary, without another chat message. |
| Context-complete mixed workflow | `36d6035a509e4fa5a06a20a69956c266` | Three nodes SUCCEEDED; 6 MODEL + 5 TOOL + 3 NODE + 2 FINALIZER = 16 RETURNED facts. Browse and fixed resolve each called once, using the same five identifiers. A2UI and final summary visibly matched. No input action. |
| Existing Skill-only compatibility | `0623b006181041c0ae0b56264fe56c1e` | Three nodes SUCCEEDED; 8 MODEL + 6 TOOL + 3 NODE + 3 FINALIZER = 20 RETURNED facts. Two real capability calls, display-only A2UI and matching summary. |

Missing-input terminal snapshots before refresh, after refresh and after reopening the same detail were identical: fingerprint `ffd05041ef4e4a202f5f0f6d6017bb398c5b9ea36fd71b5ff42c745483d44b5a`. Mixed before/after snapshots were identical: `c2bfd9633b6698374ce92f5acebf79e6120129a651322d3e2952a6776b5c79cc`. No new model or business execution was created by history reads. Completed cards are read-only. Waiting-state refresh also preserved identical execution facts on the original diagnostic run.

Empty required submission was explicitly rejected with a visible validation hint; input remained editable and no action/business operation was admitted. Repeated delivery and saved-result reuse were additionally checked offline, not by replaying a public business request. The mixed display card declared paging actions; no paging action was executed in this acceptance.

## Corrections found during acceptance

- `0179713`: an ONLINE dependency failure must appear as that environment's failed release gate, without breaking the overview of an already successful PRT publication. Missing and ambiguous dependencies remain release blockers.
- `c84e80e`, `b5c5e7b`: preserve temporary input validation errors through HTTP/B; rolled-back nonexistent action cleanup must not replace the original validation error.
- `bb97f86`: latest real submissions supersede earlier missing-input descriptions. The initial diagnostic run repeated a question despite persisted input; its evidence was retained and it later completed through a second normal submission. A separate malformed single-line input correctly triggered clarification and also completed. Neither two-card run is counted as the one-submission gate. No automatic model retry, hidden fallback or historical database edit was introduced.

## Builds and coverage boundaries

Java full JDK 17 build and publication/compiler contract probes passed. Both frontends passed type checks and full builds. Nineteen native SDK offline probes passed, covering missing input/resume, partial arguments, the 16-card precreation limit with saved-card recovery, unknown outcomes without replay, saved results and legacy definitions. Focused validation-error and rollback probes passed. Unit tests were waived and not run.

The current registered API catalog has no genuinely zero-business-argument API. The closed-empty-object fast path passed native graph offline verification (zero argument-model calls, one execution probe), not public business execution. Optional business fields were not removed to manufacture that case. Schema/environment/reference boundaries have contract evidence; this is not a claim of exhaustive public adversarial coverage.

Runtime/B shared source deployed at `bb97f86`; B's error-mapping module at `c84e80e`; Java at `0179713`; M/B frontend at `31fc16e`; management-agent shared source at `1b51e50`. The mixed run completed on `b5c5e7b` before the subsequent submission-prompt-only correction; the one-submission and legacy regression ran on the latest deployment. Old images/configurations were retained for rollback. Scoped source scans and diff checks passed. Later documentation-only commits do not change deployment.

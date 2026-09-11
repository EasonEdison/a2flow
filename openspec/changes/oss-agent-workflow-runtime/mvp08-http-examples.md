# MVP08 Runtime HTTP examples

Source candidate consumes accepted assets at 6ac3f56. Illustrative HTTP, not executed requests
or new shared contracts.
Host authentication must inject TrustedContext; no userId/environment headers/body are trusted.

## Start and discover while the synchronous request runs

POST /runtime/runs
Content-Type: application/json

```json
{"controlRequestId":"mvp08.start.001","definitionKey":"activity-planning","inputs":{"requirement":"Plan a small community activity"}}
```

definitionKey and the closed requirement input are fixed by the accepted demo asset/host profile.
Start returns the existing committed run snapshot after synchronous execution returns/waits.
During the POST, a separate authenticated request can discover the allocated run:

GET /runtime/controls/mvp08.start.001

```json
{"controlRequestId":"mvp08.start.001","runId":"<allocated-run-id>","delivery":"DISPATCHING"}
```

DISPATCHING is receipt state, not a node success or liveness guarantee.
Refresh retains controlId/runId; missing receipt never means start a different execution.

## Read and observe the same run

GET /runtime/session
GET /runtime/workflows?limit=20
GET /runtime/runs?limit=20
GET /runtime/runs/<run-id>/view
GET /runtime/runs/<run-id>
GET /runtime/runs/<run-id>/progress
GET /runtime/runs/<run-id>/nodes/<node-id>/executions/<32-lowercase-hex>/history?limit=100
GET /runtime/runs/<run-id>/nodes/<node-id>/executions/<32-lowercase-hex>/stream

Reconnect the stream with Last-Event-ID: <same-execution-id>:<last-committed-seq>.
Do not also supply after. History accepts after=<same-execution-id>:<seq>.
The catalog has run-scoped cursors; never interchange catalog and execution cursors.
/runtime/runs/<run-id>/events remains a one-shot runtime.snapshot, not an SSE/replay route.

## Current node-bound Action

POST /runtime/runs/<run-id>/nodes/<node-id>/actions
Content-Type: application/json

```json
{"interactionId":"<saved-interaction-id>","actionName":"confirm_activity","controlRequestId":"mvp08.confirm.001","inputs":{"optionId":"<saved-option-id>","confirmed":true}}
```

The optionId must come from the saved card and pass current version/configuration revalidation.
No caller-provided businessSuccess, interactionCompleted, nodeId/runId body override or native
checkpoint reference is accepted.

## Stop and fresh restart

POST /runtime/runs/<run-id>/stop
```json
{"controlRequestId":"mvp08.stop.001"}
```

POST /runtime/runs/<stopped-run-id>/restart
```json
{"controlRequestId":"mvp08.restart.001","inputs":{"requirement":"A fresh activity request"}}
```

Restart allocates a new run and does not inherit prior context/results. Refresh is never restart.
Owner run-list/session/view routes are implemented read paths. Cards come from the saved Interaction
display snapshot; final outputs and node terminal state come from committed execution/view facts.

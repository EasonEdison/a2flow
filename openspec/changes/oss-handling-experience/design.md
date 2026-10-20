# Design

Keep raw task state and add latest assistant deliveryStatus to detail and rail. Running or interrupted delivery overrides the UI progress label without rewriting saved operation outcomes. Confirmation rejects unfinished delivery at the backend, under the task row lock. Failed/unknown operations remain non-confirmable.

Use one presentation helper for task labels and existing content-operation labels. Show real titles, IDs, revision, audience and collapsible Markdown; retain raw envelope and errors under technical details. Unknown capabilities use a neutral label, never an invented business success. Rail entries show status, time and confirmation summary instead of the full prompt. New task entry stays separate from continuation.

Confirmation records an explicit statement of completed scope and remaining work. User acknowledgement and original workflow state remain separate. Ambiguous save responses disable resubmission until the saved state is read again.

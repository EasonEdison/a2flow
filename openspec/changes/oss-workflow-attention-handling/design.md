# Contracts and invariants

B owns processing tasks, message/card associations and operation claims. Runtime accepts a typed provider through composition; it does not depend on B business models. The frontend sends processingTarget or processingTaskId with a persistent processingRequestId. The server validates scope and freezes the original run evidence. A message pair and task binding are admitted transactionally.

The provider claims each canonical ability+argument operation within the task before dispatch. A stable request ID is passed to the business call. A repeated operation reads its persisted result rather than sending again. RUNNING and UNKNOWN are not retried; failed outcomes do not silently become success. This provides platform dispatch control, not a guarantee of arbitrary downstream exactly-once behavior.

Operation states: RUNNING, RETURNED, FAILED, UNKNOWN. Task states: OPEN, WAITING_INPUT, RESULT_RECORDED, FAILED, UNKNOWN, RESOLVED. RETURNED means an RPC response was received successfully; it is not a universal business success predicate. RESOLVED records explicit human confirmation with a conclusion and time. It does not mutate the original workflow or erase attention evidence.

Direct execute_ability is covered by task claims. Temporary input submission reuses existing action idempotency and unique continuation. Existing multi-ability Application actions retain their own execution path; card completion alone is never promoted to a processing result.

Rejected alternatives: attaching every future Chat operation to the latest reference; trusting model prose as a completion receipt; replaying uncertain calls; treating viewed reminders or submitted forms as business completion.

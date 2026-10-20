# Chat write confirmation

Read-only capabilities run without an additional prompt. WRITE/DESTRUCTIVE with REQUEST_APPROVAL use a host-authored temporary card showing the actual arguments. The model cannot supply approval receipts. A durable same-owner claim precedes RPC; immutable source, action, arguments and tool scope bind the receipt. A completed confirmation resumes the conversation using the actual ACTION outcome, without repeating the write.

Handling tasks retain their original task, turn and tool-call identity. WAITING_INPUT admits only its exact claimed confirmation card and no other waiting card. Ordinary temporary input never grants this exception. Unknown outcomes remain terminal and are not retried.

The shared helper and RPC governance contract are delivered by the parent execution-guards change. This change owns Chat adapters, card transitions, and handling-task admission. Existing A2UI mapped action confirmation is a separate coordinated compatibility requirement before deployment.

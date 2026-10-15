# Work activities and conversation run references

Approved scope: B-side work activity rail for attention, running and completed instances; manual and scheduled execution results can be explicitly referenced in a Chat turn; original waiting interactions resume the same run after submission. Runs remain independent of conversations. Background completion does not create a model turn or bind to the latest Chat.

Implementation reuses persisted runtime views, owner/environment identity, existing card Actions and checkpointed Chat. Activities are not derived from rate-limited notifications. Result tools only read saved data. Explicit business attention requires saved tool evidence and never changes lifecycle or performs remediation.

UI: desktop collapsible rail and narrow drawer; human names, source and times; removable reference chips; detail reuses existing RunDetail while retaining Chat and draft. No generic automatic retry, new scheduler engine or authorization bypass.

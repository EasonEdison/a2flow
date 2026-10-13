# Temporary generated interactions in Chat and Flow

Status: implemented and deployed, 2026-10-13. Public Chat accepted; public Workflow gate remains open. See regression and readiness for evidence boundaries.

Generate task-local A2UI from the user's request and supplied context without a
pre-authored Application. Chat and Workflow share the generator and card protocol.
Collect choices/form input, save the result, then continue the owning task. Completed
cards remain historical; there is no application library or general business database.

The existing published-application and generated-layout paths remain supported.
Actual business operations continue through authorized Skill capabilities. A saved
user submission is not evidence that a business operation succeeded.

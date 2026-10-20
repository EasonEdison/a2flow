# Regression

Baseline: `cdadb987` (2026-10-20). This record separates source checks, an isolated
fresh installation and the existing public deployment. Existing business runs are
not replayed as an acceptance substitute.

## Source and fault boundaries

- 353 Python files parsed, 98 local entry-document links checked, direct Runtime
  import boundary and frontend manifests checked; four Compose groups render.
- Java JDK 17 compilation passed. Initial public-deployment package compared 564
  Java build inputs; B TypeScript/Vite passed after the notification refresh fix.
  Deployment verifies the built-input manifest against the integrated source.
- Exact changed-file secret scan and private/company-pattern scan passed before
  publication. Final integration repeats the diff and artifact checks.
- [Outbox checks](../portfolio-runtime-outbox/regression.md): 15 real isolated
  PostgreSQL/native checkpoint scenarios, including deferred commit failure,
  deduplication, process restart, acknowledgement loss and waiting notification
  recovery. Root repeated the combined candidate successfully. No model or
  business calls in the fault-injection probe; no external sends.
- [Account checks](../oss-account-abuse-guards/regression.md): shared process/M/B
  admission, explicit trusted proxies, registration policy, safe failures, and
  synthetic account recovery under exact pinned HTTP dependencies. Existing
  production accounts were not changed.

## Empty self-hosted installation

- Public Node/Python/Maven/Temurin/nginx image builds completed. PostgreSQL 16.6
  and Redis persist through named volumes. No private SDK image or existing
  A2Flow database was used.
- Explicit databases, Java migration and schema initialization ran twice. One
  explicit administrator, unchanged password hash, one V001 receipt and the
  expected schema receipts remained. No sample assets were seeded at startup.
- Normal M/B browser login succeeded. A real model created one Skill and one
  Workflow through management chat, then published both to PRT (27 completed
  tool operations, two successful deployment receipts). No business adapter or
  service was generated.
- B started the published Workflow. The real model generated a temporary theme /
  participant-count form; the native parent and child checkpoints referenced the
  same interrupt, with one waiting outbox item and one unread notification.
- The complete isolated stack was stopped and recreated on retained volumes,
  using the final public-build images. The same run and waiting interaction,
  two publication receipts and one notification survived, with no new run.
- Browser restoration showed the waiting work item and one unread notification;
  clicking the notice opened the same form. Submitted once with synthetic inputs
  `open-source technical exchange` and `12` participants. The same Skill and summary
  completed automatically. Without a browser refresh, unread notifications
  increased from one to two; waiting and completion each appeared once. The
  submitted card became read-only history and the summary used both supplied
  values. Fresh-install registration returned `403 REGISTRATION_DISABLED`.

## UI defect found during real acceptance

The backend had persisted the waiting notice, but B loaded its notification list
only at login. Added a visible-page 15-second refresh, focus/visibility refresh,
abort on account/effect changes, explicit stale-result errors and manual refresh.
The waiting run is reused to check completion appears without a manual reload.

## Public deployment

TLS certificate issuance, external trust/hostname validation and a dry-run renewal
with nginx reload hook passed. Application HTTPS activation, final source
integration, existing-data comparison and public acceptance remain pending.
No general HA, volumetric DoS, business exactly-once or disaster-recovery SLA is
claimed by these checks.

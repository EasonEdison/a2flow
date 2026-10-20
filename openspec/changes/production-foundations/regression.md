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


## Integrated deployment and public acceptance — 2026-10-20

Application commit `4927929058d1b69f7e1fb42560f67644c44a5d9d` was merged to
main and both configured remotes. Project checks and typed-subset CI completed
successfully. The exact outgoing 67 files passed secret/private-pattern scans;
650 compiled Java/frontend inputs matched integrated source, all 67 changed release
files matched main, and all seven served B assets matched the accepted build.

B, account login, Runtime, Scheduler and Java management services were recreated
from captured per-service configuration. Actual images/entry points, read-only
mounts and resource/security settings were retained; Scheduler retains its 128 MiB
limit. All five services were running with zero restarts after deployment. The
account admission migration was applied explicitly and the real database role's
SELECT/INSERT/DELETE privileges were checked. No existing account was reset or
promoted. Ordinary TLS verification, automatic HTTP redirect, login pages and
internal-route blocking passed. Certificate renewal dry-run and reload hook passed.

A synthetic nonexistent username alternated between M and B: eight responses were
invalid credentials, the ninth was 429 with a positive Retry-After. Changing
untrusted forwarding headers did not escape the shared quota. Both surfaces
rejected a foreign Origin before credential checking. Existing self-registration
policy was retained; the operator registered and logged in a regular member through
the public B UI. Secure/HttpOnly/SameSite cookie settings were verified in source
and active configuration; raw successful Set-Cookie values were not collected.

Using that member, the published two-step temporary-interaction acceptance flow
was started once. The page received its waiting notification without reloading,
and the activity rail showed the same pending run. A full page refresh preserved
the form. Submitting a single short acceptance comment automatically completed
the collection node, next-node receipt and final summary. The original form became
read-only. The unread count changed from one to two without another reload;
the rail moved from pending to completed. Opening the completion notification read
back the saved result and exact submitted comment.

Read-only database evidence confirmed one start, one consumed resume command,
three completed outbox entries (waiting/resume/completed) and two notices
(waiting/completed). All 35 pre-existing run documents retained their exact
ordered digest; five existing schedules remained disabled. No prior business run
was replayed and the acceptance flow made no business writes. The independently
built local self-host stack was stopped after evidence capture; temporary model
key copies and synthetic administrator input were removed, persistent volumes
and non-secret evidence retained.

Public authenticated M creation was not repeated because the operator used a new
regular B account; the original administrator remains available. M create/publish
with a real model was verified in the fresh self-host installation above. No full
unit suite was run under the owner's validation scope. No scale/HA, adversarial
penetration or external-provider unknown-outcome retry claim is made.


## Public authenticated management follow-up — 2026-10-20

After the operator signed in with the existing administrator, one normal browser
conversation requested an independent temporary-interaction acceptance workflow.
The agent reused two published Skills and the built-in summary, completed 23 tool
calls and returned the saved PRT result. The prior public-M limitation above is
closed by this follow-up.

Read-only authoritative checks found exactly three successful management mutations:
workflow create, draft update and PRT deploy. All target the new workflow. Its
release state contains one build and one deployment, with PRT build version one;
this is not a claim that the separate formal-version array has an entry. The two
reused Skills retain their previous release timestamps and were not republished.

The regular-member B preset catalog displays the new workflow. Full refresh of
the management conversation retains the same completed turn and publication.
The 36 existing runtime documents retain their pre-check ordered digest; the new
workflow was not started, no business capability was called and no schedule was
created. Screenshots and read-only receipt evidence are retained privately.
This follow-up changes only acceptance documentation; deployed application code
remains unchanged.

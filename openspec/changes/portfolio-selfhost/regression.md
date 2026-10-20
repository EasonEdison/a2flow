# Regression

Verified on a new local Compose PostgreSQL volume, not an existing deployment.
No production records were copied and no asset seed ran. Full unit suites are not run.

## Source builds and bootstrap

- Python syntax and actual generated Compose configuration pass. Generated private
  files preserve mounted path spelling, exact proxy trust and per-service certificate roles.
- Both frontends build from fresh public Node dependencies. Gateway serves both
  entry pages and emitted JS/CSS assets; the internal API route returns 404.
- Complete public Python Dockerfile build passes. All seven actual service/bootstrap
  modules import inside the image with networking disabled.
- Complete public Maven/Temurin 17 Dockerfile build compiles 604 Java sources and
  copies runtime dependencies successfully. A temporary image using already compiled
  local classes was used while public layers downloaded, then replaced by the final
  public-build image. It is not counted as the public build proof.
- New PostgreSQL volume initialization succeeds. Database creation, Java V001 and
  full schema/admin initialization each run twice successfully. Readonly verification
  confirms one Java receipt, four PRT SQL receipts, one explicit administrator and
  the unchanged initial password hash.
- Eleven Compose services run with zero restart counts. `/login` and `/employee/`
  return 200; unauthenticated `/api/auth/session` returns 401; internal ingress is 404.

Final locally built image IDs:

| Image | SHA-256 |
| --- | --- |
| gateway | af97137bbb3e1bcd0ecb80736c7d4aa5f223510d53ced617864cfb70b98c8f57 |
| python | 851246c6b0cb1ca6db8c4a3608812fb7804bb8b8e6843c5f27beb94d6dbc0a3b |
| management | 7e690b978ef545bfe9ef59811ea62447d0339685b5fa6a69434274729d4cd22c |

Java inputs match integrated candidate c3480ef; Python includes its outbox/waiting
changes and the selfhost launcher exit-status fix. B inputs are unchanged from
fd3294a through c3480ef. Its 86 tracked build-input aggregate is
`4dc798f1a73dd8d00ec37110319ddf010e46f2ac3e10862cb930d2d127c44627`:
sorted relative path bytes, NUL, then each file SHA-256 raw bytes. The package-lock
SHA-256 is `59e492a93bc695223a88a6ebdb21fe37720c04bdd066f394066b8990383b851c`.

## Authenticated publication

The coordinating agent logged into M/B through the normal browser and invoked the
real model using a privately supplied provider credential. Readonly database proof:

- Management conversation `331cc0944a884453b592838121af7367`, turn
  `0f4c689f82ae44f79958356df4eb6695`: user 1, PRT, COMPLETED, 27 tool starts and
  27 completions, two successful RELEASE_PREPROD_DEPLOY mutations.
- Skill `activity-suggestion-acceptance` and Workflow
  `wf_8d8c8631ed8c41789d4cca0777e6b45f` each have PRT version and serving records;
  two publication receipts exist. These were published through management tools,
  not inserted by bootstrap.
- M identity is resolved only from `a2flow_management_session`; B login alone is
  not accepted by that provider. The recorded caller is the explicitly created ADMIN.

Model-backed B missing-input/resume and full-stack restart/history checks remain
in progress under the coordinating agent. No success for those checks is claimed yet.

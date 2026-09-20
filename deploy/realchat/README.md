# Real Chat / management PRT integration

This is a parallel private deployment, not a migration of the attended or
management-preview databases. All three application hosts share one PostgreSQL
asset namespace. Existing deployments and volumes are untouched.

Build `deploy/realchat/Dockerfile` from a clean reviewed integration commit. Set
`A2FLOW_REALCHAT_IMAGE`, `A2FLOW_REALCHAT_STATIC` (built `management/` and
`employee/` subdirectories), and `A2FLOW_REALCHAT_SECRETS` outside Git. Secret
files must belong to the application UID with mode 0400; the separate Postgres
copy must be readable by the database image's postgres UID. Both password
copies contain the same value. Never print environment or secret contents.

Start `postgres`, run `initialize` once, then start `management`, `bside`, and
`runtime`. Initialization installs demo prerequisites, not acceptance edits.
Do not rerun seed against edited/published assets to force an old snapshot.

Listeners bind only server loopback: M 8780, B 8781, Runtime 8782. Forward local
14183 to 8780 and 14184 to 8781 with SSH. Browser origins are exact and deliberate.
M uses its private-preview login; B uses its existing login/session flow.

Acceptance must use the real M page: save/validate/publish an Application edit,
confirm its component references are registered, then invoke the bound Skill in
Chat and operate the resulting card. Unknown component references must fail
validation. A card produced by mock API interception is not acceptance proof.

Registered components are renderer contracts, not uploaded executable code.
Adding an unimplemented renderer requires a code release before registration.
Installed business operation adapters remain the demo registry; real service
execution does not imply integration with an external company's APIs.

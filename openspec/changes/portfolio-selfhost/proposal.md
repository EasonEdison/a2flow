# Empty-installation self hosting

Approved scope: add an independently runnable, source-buildable installation under
`deploy/selfhost`, retaining existing operator deployments unchanged. No old data,
accounts, credentials or published assets are copied. Source baseline cdadb987.

The current application hosts deliberately bind loopback. Applications therefore
share a gateway network namespace; only the gateway maps a host-loopback port.
PostgreSQL uses an installation-owned socket/data volume, Redis has an owned data
volume. Public exposure requires an explicit HTTPS proxy and exact browser origin.

Build images from public Python, Node, Maven/JDK, nginx and PostgreSQL sources;
never require a private prebuilt SDK. Low-memory hosts import reviewed build outputs
instead of compiling Java/npm in place. All runtime secrets are generated outside
Git; administrator identity/password and model credential are explicitly supplied.

Initialization is an explicit command, separate from startup. It initializes only
its own new databases, records its installation identity and schema stages, and
refuses takeover of unmanaged database/role names. Repetition verifies completed
stages and does not reset passwords, overwrite assets or create another admin.
A same-origin example importer uses normal authenticated management publication,
never inserts published assets directly. Restarts keep data and do not seed.

Acceptance: clean build, configuration syntax, empty-volume initialization,
initialization replay, real login and PRT publication, model-backed missing-input
submission/resume, saved history after restart. Source/build evidence, installation
and model-backed acceptance are reported separately. Root owns integration/deploy.

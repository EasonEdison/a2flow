# Regression

Candidate installation verification is in progress; no model-backed result is claimed.

- Python syntax and actual generated Compose configuration pass. Generated private
  files preserve mounted path spelling, exact proxy trust and per-service certificate roles.
- Both frontends build from fresh public Node dependencies. The gateway image serves
  both entry pages and emitted JS/CSS assets; the internal API route returns 404.
- Full Python Dockerfile build succeeds from public dependencies; all seven actual
  service/bootstrap modules import inside that image with networking disabled.
- A new Compose PostgreSQL volume starts successfully. `initialize databases` runs
  twice successfully against the same isolated installation. No existing database
  rows were copied and no assets were seeded.
- Java source image build, schema initialization/replay, M/B login, normal PRT
  publication, model-backed interaction/resume and restart remain pending.

Full unit suites are not run. Existing public deployment evidence is not a substitute
for this new empty installation. Final image IDs and integrated source revision will
be recorded after the complete stack passes.

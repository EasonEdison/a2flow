# Readiness

READY for coordinated source integration of the management startup fix; deployment
and public acceptance remain the parent task's responsibility.

The first expanded gate was actually green on GitHub for
`dd73ce8a60493ab6030fcf75f1073e390e375b47`:
[Core invariant probes](https://github.com/EasonEdison/a2flow/actions/runs/39418947462),
[Project checks](https://github.com/EasonEdison/a2flow/actions/runs/39418947366) and
[Python quality](https://github.com/EasonEdison/a2flow/actions/runs/39418947418).
That evidence did not cover production Spring composition. Public deployment
subsequently found missing approval bean registration; the host was rolled back.

The added startup probe first reproduced the exact missing-guard failure against
unpatched compiled classes. After explicitly importing the real guard/store in
`RuntimeRpcConfiguration`, a full JDK 17 build compiled 611 sources and the whole
Java gate passed: production context 8, durable PostgreSQL approval 41, and package
restore 107. The actual Hikari pool and loopback gRPC lifecycle started and closed;
no application bean was replaced and no business call occurred.

The updated startup gate has passed locally but has not yet run on GitHub. The
previous six Python probes were unchanged by this Java wiring correction.
See [regression](regression.md) for source/evidence boundaries. Containers, private
credentials and temporary classes were removed; previous self-host volumes and
stopped containers were preserved. No deployment was performed by this worker.

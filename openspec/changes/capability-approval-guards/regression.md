# Targeted verification

2026-10-20, isolated local execution, synthetic inputs only.

- Generated Java Proto and all production backend Java sources compiled using JDK 17 with the existing public dependency set. Four pre-existing Lombok Jackson ambiguity warnings; no errors.
- `CapabilityApprovalGuardProbe` without a database: `{"result":"PASS","checks":32,"businessRpcCalls":5,"postgres":false}`.
- Same probe against a dedicated empty loopback PostgreSQL 16 database: `{"result":"PASS","checks":41,"businessRpcCalls":5,"postgres":true}`.
- READ with both valid policies executes; a supplied receipt is not consumed. Invalid/missing governance, unapproved WRITE/DESTRUCTIVE, ordinary demo boolean, model-supplied approval values, changed owner/environment/action/source/policy/arguments all cause zero business RPCs. Preview does not consume.
- Approved synthetic writes execute; duplicate receipt and unavailable store reject before RPC.
- PostgreSQL: eight concurrent claims have one winner; a new store sees prior consumption; alternate receipt ID or alternate confirmation for the same tool call cannot bypass uniqueness. A trigger-injected SQL failure rolls back the claim. Probe random schema removed and zero remaining probe schemas verified; dedicated container removed.

## Reproduce

From `services/management-java`, after ordinary production compilation / dependency copy:

```sh
javac --release 17 -cp 'target/classes:target/dependency/*' -d target/probe-classes backend/storage/db/tests/CapabilityApprovalGuardProbe.java
java -ea -cp 'target/probe-classes:target/classes:target/dependency/*' dev.a2flow.management.capabilityrpc.CapabilityApprovalGuardProbe
```

Optional real PostgreSQL verification accepts exactly a dedicated loopback database `a2flow_approval_probe` with an empty public schema. It creates and drops only a random `approval_probe_*` schema. Supply password through `A2FLOW_PROBE_DB_PASSWORD` when needed; do not put credentials in arguments:

```sh
java -ea -cp 'target/probe-classes:target/classes:target/dependency/*' dev.a2flow.management.capabilityrpc.CapabilityApprovalGuardProbe jdbc:postgresql://127.0.0.1:15441/a2flow_approval_probe probe
```

Full Maven lifecycle was not used as evidence: the offline public cache lacked plugin transitive POM metadata. Generated sources and all backend sources were instead compiled with JDK 17 `javac`, the same public dependency jars, and the Lombok processor. No ECS build, production database writes, model calls or live business RPCs were performed by this worker. Parent integration runs repository-wide checks and deploys the complete Runtime confirmation path.

## Rollout boundary

Apply additive `backend/storage/db/migration/V003__capability_approval_consumption.sql` explicitly to the management database before write confirmation is enabled. Bootstrap must include that file after V002. Missing table/store failures deny writes. Legacy READ releases retain `REQUEST_APPROVAL` metadata and remain executable under the user's explicit READ exemption. Existing writes require the new persisted Runtime confirmation; A2UI actions and management dry-run without a receipt are explicitly blocked. This Java slice alone is not complete user-facing confirmation/resume delivery.

The committed admission is not atomic with the remote RPC. A lost response or crash after consumption leaves an unknown outcome and cannot reuse the receipt; no automatic business retry is introduced.

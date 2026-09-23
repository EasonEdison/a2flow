# Errors

## [ERR-20260923-001] remote-apply-patch

**Logged**: 2026-09-23T00:00:00+08:00
**Priority**: low
**Status**: resolved
**Area**: infra

### Summary
The server worktree does not provide an `apply_patch` executable.

### Error
`bash: line 4: apply_patch: command not found`

### Context
- The repository is edited only through SSH on the user-authorized server.
- No file was changed by the failed invocation.

### Resolution
- **Resolved**: 2026-09-23T00:01:00+08:00
- **Notes**: Files were staged with the supported patch tool, copied into the assigned server path, and audited there.

## [ERR-20260923-002] content-mvp-pytest

**Logged**: 2026-09-23T00:30:00+08:00
**Priority**: low
**Status**: pending
**Area**: tests

### Summary
The isolated runtime/typing venv does not include pytest.

### Error
`No module named pytest`

### Context
- Ruff and strict mypy completed successfully before this test invocation.
- Do not silently mutate the coordinator-owned venv while PostgreSQL and transport checks run in parallel.

### Suggested Fix
Run tests from the existing quality environment if its dependency set is sufficient, or have the coordinator add pytest once to the dedicated venv.

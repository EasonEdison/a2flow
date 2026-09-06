# Phase 1 Contract Regression

- Baseline: `SW-P1-20260907.2`
- Candidate revision: `SW-CONTRACTS-P1-CANDIDATE.1`
- Status: `SCHEMA PASS / ADAPTER SOURCE PASS / RUNTIME NO READY`
- Executed focused cases: `57`

## Environment

- Command: `python3 packages/contracts/tests/validate_contracts.py`
- Python: `3.6.8`
- jsonschema: `2.6.0`
- Supported validator dialect on host: Draft 3/4
- Dependency installation: none
- System Python mutation: none; PY-01 execution belongs only to Runtime/main-brain coordination

### Approved Python adapter environment

- Approval: `SW-P1-SUBSET-01`
- Command: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/contracts/src python3.11 -m unittest discover -s packages/contracts/tests/python -v`
- Python: `3.11.13`
- Third-party dependencies: none
- Result: `16/16 PASS`; the suite replays all `25` existing fixtures whose definitions are in the approved Skill/Policy closure
- Import smoke: `UseSkillRequest.from_mapping(...).to_mapping()` PASS

## TDD evidence

| Cycle | Expected break | Observed result |
| --- | --- | --- |
| RED-1 | Schema absent | exit 1, `FAIL schema missing` |
| GREEN-1 | 最小上下文/环境/版本/控制/事件 | 19/19 PASS |
| RED-2 | publication CAS、入口版本、closed retry、mismatch event 缺口 | 27 total / 19 PASS / 8 FAIL |
| GREEN-2 | 补齐上述最小约束 | 27/27 PASS |
| RED-3 | Skill consumer definitions 缺失 | 36 total / 27 PASS / 9 FAIL |
| GREEN-3 | use_skill request/context/material/result | 36/36 PASS |
| RED-4 | use_skill 尚未按 content + artifact 分层 | 36 total / 35 PASS / 1 FAIL |
| GREEN-4 | content/artifact 与版本 evidence 分层 | 36/36 PASS |
| RED-5 | ResultInterpretationPolicy 与 package-relative logicalPath 尚未实现 | 39 total / 33 PASS / 6 FAIL |
| GREEN-5 | 两种最小策略与规范化材料逻辑路径 | 39/39 PASS |
| RED-6 | named policy set 容器尚未实现 | 41 total / 39 PASS / 2 FAIL |
| GREEN-6 | resultInterpretationPolicies + defaultSuccessPolicyRef | 41/41 PASS |
| RED-7 | pre-merge review 的 control/event/policy/material/Action 缺口 | 53 total / 40 PASS / 13 FAIL |
| GREEN-7 | 非空/唯一引用、closed event、runSequence、四事实片段与 CR/LF 边界 | 53/53 PASS |
| CHECK-8 | fresh START 不携带 recorded versions | 54/54 PASS |
| RED-8 | Draft 4 `$` 接受 identifier/skillKey 终末换行 | 57 total / 54 PASS / 3 FAIL |
| GREEN-8 | identifier/skillKey 显式排除 CR/LF | 57/57 PASS |
| RED-9 | `skillweave_contracts` 尚不存在 | unittest import error，0 tests executed |
| GREEN-9 | 严格冻结模型、显式 dispatcher、approved-only schema loader、不可变错误接口 | 13/13 PASS；批准闭包 25 个既有正反例对照 PASS |
| RED-10 | reviewer probes：异常 issues 可回写、复合 schema `$ref` 悬空、Workflow 显式 null 被误当缺省 | 16 total / 12 PASS / 4 FAIL |
| GREEN-10 | 防御性复制+只读 issues、自包含 definition schema、缺省/null 严格区分 | 16/16 PASS |

## Covered contract cases

| Area | Positive | Negative | Result |
| --- | --- | --- | --- |
| Trusted context | userId + PRT/ONLINE | sellerId/extra override | PASS |
| Serving/publication | PRT current；ONLINE stable+candidate；CAS revision | 第三 serving 版本；PRT 写 ONLINE slot | PASS |
| Resolution/version guard | ONLINE gray from ONLINE；ALLOW/RESET_REQUIRED | ONLINE->PRT；mismatch+ALLOW | PASS |
| Control requests | node-bound interaction；A2UI-only retry；non-empty versions | business idempotency；missing/empty/conflicting versions；generic retry | PASS |
| ResultInterpretationPolicy/Action | SCHEMA_VALID；JSON_POINTER_EQUALS；named set；success/completion binding；四事实 | unsupported operator；missing expected/fact；duplicate/dangling policy | PASS |
| Events | runSequence；closed Interaction/Node/Run Result scope | missing/mismatched/redundant ref；foreign fact；blocked+ALLOW | PASS |
| use_skill | logical request；server scope；READ_ONLY handles；真实 package-relative logicalPath/digest/size；content+artifact | identity override；newline skillKey；missing node；raw locator；parent traversal；newline；duplicate logicalPath；Workflow route | PASS |

Exact fixtures and expected validity live in `packages/contracts/tests/cases.json`; all data is synthetic and project-authored.

## Still unverified

- TrustedContext/TrustedInvocationContext provenance and model schema exclusion.
- PRT/ONLINE separate PostgreSQL databases and ONLINE-only stable/gray reads.
- Multi-instance publication/control dedupe and CAS persistence.
- execution/continue/Action ingress ordering before model/Tool/business calls.
- Deep Agents content_and_artifact visibility, checkpoint serialization and PostgreSQL reopen.
- ResultInterpretationPolicy interpreter runtime behavior, A2UI success/completion and Finalizer boundaries.
- Event transaction/delivery protocol and end-to-end Runtime behavior.
- Installed-wheel/package metadata behavior; root manifest/lock remains main-brain-owned.

Schema PASS cannot satisfy these runtime gates.

"""Bounded design/admission probe; default mode performs no I/O except stdout."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from dataclasses import dataclass
import io
import json
import logging
import os
from pathlib import Path
import re
import time
from typing import Any


@dataclass(frozen=True)
class Case:
    name: str
    app: str
    intent: str


CASES = (
    Case("people", "people-selector", "把人员选择界面用 Card 分成说明、人员选择、分页操作三个清晰区域；保留所有工程锚点、分页和填入聊天输入框动作，不按未声明的业务字段重新分组。"),
    Case("reading", "reading-point-selector", "把阅读要点界面设计成易读的卡片布局，每条清晰展示观点、原文引用和解释。若合同声明 evidenceLocator 和 modelSuggestion 的只读权限，用新 Text 展示它们，保留 List 模板作用域、多选、输入与确认动作。"),
    Case("topic", "content-topic-selector", "优化选题确认卡片布局，把可编辑标题、角度和确认操作层次分明地排列。保留每个 List 模板作用域、所有工程锚点、输入与确认动作。"),
    Case("manuscript", "content-manuscript-editor", "优化稿件编辑布局，把标题与正文编辑、预览、保存确认和导出区域用 Card 清晰组织。保留所有工程锚点、输入绑定、原函数及动作，不能伪造保存、确认或导出状态。"),
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    mode = result.add_mutually_exclusive_group()
    mode.add_argument("--read-only", action="store_true", help="read published contracts and probe admission; no model calls")
    mode.add_argument("--live", action="store_true", help="one actual design attempt per selected case; no activation")
    result.add_argument("--case", action="append", choices=[case.name for case in CASES], help="default: all four; duplicates rejected")
    result.add_argument("--max-calls", type=int, help="required in live mode, exactly the selected case count (1–4)")
    result.add_argument("--dsn-file", default=os.environ.get("A2FLOW_CAPABILITY_DSN_FILE"), help="existing published-asset database DSN secret file")
    result.add_argument("--database", default=os.environ.get("A2FLOW_CAPABILITY_DATABASE"))
    result.add_argument("--environment", choices=["PRT", "ONLINE"], default=os.environ.get("A2FLOW_CAPABILITY_ENVIRONMENT"))
    result.add_argument("--user-id", type=int, help="operator-approved trusted verification owner; never inferred from chat records")
    result.add_argument("--provider-key-file", default=os.environ.get("A2FLOW_DEEPSEEK_KEY_FILE"), help="existing DeepSeek secret file, read only with --live")
    return result


def safe_code(error: Exception) -> str:
    # Never serialize exception details, provider response bodies or validation input.
    value = getattr(error, "code", None)
    if isinstance(value, str) and re.fullmatch(r"A2UI_[A-Z0-9_]+", value):
        return value
    if type(error).__name__ in {"ActionRejected", "ModelConfigurationError"}:
        value = str(error)
        if re.fullmatch(r"(?:A2UI|MODEL|DEEPSEEK|INVALID_DEEPSEEK)_[A-Z0-9_]+", value):
            return value
    return {
        "ValidationError": "CANDIDATE_SCHEMA_INVALID",
        "APITimeoutError": "PROVIDER_TIMEOUT",
        "TimeoutError": "PROVIDER_TIMEOUT",
        "AuthenticationError": "PROVIDER_AUTHENTICATION_FAILED",
        "RateLimitError": "PROVIDER_RATE_LIMITED",
        "APIConnectionError": "PROVIDER_CONNECTION_FAILED",
        "FileNotFoundError": "SECRET_FILE_UNAVAILABLE",
        "PermissionError": "SECRET_FILE_UNAVAILABLE",
        "ModuleNotFoundError": "DEPENDENCY_UNAVAILABLE",
    }.get(type(error).__name__, "PROBE_FAILED")


def components(candidate: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (message["updateComponents"]["surfaceId"], component["id"]): component
        for message in candidate["messages"] if "updateComponents" in message
        for component in message["updateComponents"]["components"]
    }


def source_candidate(published: Any) -> dict[str, Any]:
    return {
        "messages": deepcopy([message for message in published.build.initial_messages
                              if "updateDataModel" not in message]),
        "actionPlacements": [
            {"bindingId": action.binding_id, "surfaceId": action.surface_id,
             "sourceComponentId": action.source_component_id}
            for action in published.build.action_bindings
        ],
    }


def check(published: Any, membership: dict[str, str], candidate: dict[str, Any],
          name: str, expected: str | None = None) -> dict[str, Any]:
    from a2flow_a2ui.generation import validate_candidate
    from a2flow_a2ui.models import GeneratedCandidate
    try:
        admitted = validate_candidate(published, membership, GeneratedCandidate.model_validate(candidate))
        # Admission alone permits omitted bindings; the quality gate requires all actions.
        if {item.binding_id for item in admitted.build.action_bindings} != {
            item.binding_id for item in published.build.action_bindings
        }:
            return {"check": name, "passed": False, "code": "QUALITY_ACTIONS_NOT_PRESERVED"}
    except Exception as error:
        code = safe_code(error)
        return {"check": name, "passed": expected == code, "code": code}
    return {"check": name, "passed": expected is None,
            "code": "ADMITTED" if expected is None else "INVALID_CANDIDATE_ADMITTED"}


def admission_matrix(published: Any, membership: dict[str, str], policy: Any) -> list[dict[str, Any]]:
    source = source_candidate(published)
    rows = [check(published, membership, source, "source-engineering-preserved")]
    bad = deepcopy(source)
    bad["messages"][0]["version"] = "v0.invalid"
    rows.append(check(published, membership, bad, "invalid-version", "A2UI_GENERATION_MESSAGE_VERSION_INVALID"))
    bad = deepcopy(source)
    bad["messages"].append({"version": "v0.9.1", "updateDataModel": {"surfaceId": "main", "path": "/", "value": {}}})
    rows.append(check(published, membership, bad, "model-data-write", "A2UI_GENERATION_MESSAGE_ENVELOPE_INVALID"))
    if source["actionPlacements"]:
        bad = deepcopy(source)
        bad["actionPlacements"] = []
        rows.append(check(published, membership, bad, "missing-action-placement", "A2UI_GENERATION_ACTION_NOT_ALLOWED"))
    bad = deepcopy(source)
    text = next((item for item in components(bad).values() if item["component"] == "Text"), None)
    if text is not None:
        text["text"] = {"path": "/__quality_undeclared_path__"}
        rows.append(check(published, membership, bad, "undeclared-data-path", "A2UI_GENERATION_DATA_PATH_NOT_ALLOWED"))
    # Rename a non-action Text and its explicit child references, keeping the tree valid.
    bad = deepcopy(source)
    indexed = components(bad)
    key = next((key for key, value in indexed.items() if value["component"] == "Text"), None)
    if key is not None:
        replacement = "quality-renamed-anchor"
        indexed[key]["id"] = replacement
        for (surface, _), component in indexed.items():
            if surface != key[0]:
                continue
            if isinstance(component.get("children"), list):
                component["children"] = [replacement if child == key[1] else child for child in component["children"]]
            for field in ("child", "trigger", "content"):
                if component.get(field) == key[1]:
                    component[field] = replacement
        rows.append(check(published, membership, bad, "missing-engineering-anchor", "A2UI_GENERATION_ANCHOR_MISSING"))
    # Give an existing relative Text an additional root lineage: syntactically valid,
    # but explicitly forbidden by the real scope validator.
    rule = next((item for item in policy.relative_data_bindings
                 if item.component_type == "Text" and item.property_path == "/text"), None)
    if rule is not None:
        bad = deepcopy(source)
        indexed = components(bad)
        target = next((value for (surface, _), value in indexed.items()
                       if surface == rule.surface_id and value.get("text") == {"path": rule.path}), None)
        root_id = next(item.root_component_id for item in policy.surfaces if item.surface_id == rule.surface_id)
        root = indexed[(rule.surface_id, root_id)]
        if target is not None and isinstance(root.get("children"), list):
            root["children"].append(target["id"])
            rows.append(check(published, membership, bad, "relative-text-outside-list", "A2UI_GENERATION_DATA_PATH_NOT_ALLOWED"))
        else:
            rows.append({"check": "relative-text-outside-list", "passed": False, "code": "MATRIX_SHAPE_UNSUPPORTED"})
    else:
        rows.append({"check": "relative-text-outside-list", "passed": None, "code": "NOT_APPLICABLE"})
    display = next(iter(policy.read_only_display_bindings), None)
    if display is not None:
        good = deepcopy(source)
        indexed = components(good)
        parent = indexed[(display.surface_id, display.template_scopes[-1].item_component_id)]
        new_id = "quality-read-only-field"
        wrapper_id = "quality-display-wrapper"
        added = [{"id": new_id, "component": "Text", "text": {"path": display.path}}]
        supported = not any(key[1] in {new_id, wrapper_id} for key in indexed)
        if isinstance(parent.get("children"), list):
            parent["children"].append(new_id)
        elif isinstance(parent.get("child"), str) and "Column" in {item.type for item in policy.allowed_components}:
            added.append({"id": wrapper_id, "component": "Column", "children": [parent["child"], new_id]})
            parent["child"] = wrapper_id
        else:
            supported = False
        if supported:
            update = next(message["updateComponents"] for message in good["messages"]
                          if "updateComponents" in message and message["updateComponents"]["surfaceId"] == display.surface_id)
            update["components"].extend(added)
            rows.append(check(published, membership, good, "declared-read-only-field-in-list"))
        else:
            rows.append({"check": "declared-read-only-field-in-list", "passed": False, "code": "MATRIX_SHAPE_UNSUPPORTED"})
    else:
        rows.append({"check": "declared-read-only-field-in-list", "passed": None, "code": "NOT_APPLICABLE"})
    return rows


def layout(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"surface": surface, **{name: value for name, value in component.items()
                                   if name in {"id", "component", "children", "child", "trigger", "content", "tabs", "direction"}}}
            for (surface, _), component in components(candidate).items()]


def run_case(args: argparse.Namespace, case: Case) -> dict[str, Any]:
    from a2flow_a2ui.generation import contract
    from a2flow_a2ui.releases import PostgresApplicationReader
    from a2flow_a2ui.runtime import A2uiRuntimeService
    from a2flow_capability.models import Environment, TrustedContext

    class NoBusinessCalls:
        def execute_action_code(self, action_code: str, arguments: Any, context: Any) -> Any:
            raise RuntimeError("BUSINESS_CALL_FORBIDDEN")

    owner = TrustedContext(args.user_id, Environment(args.environment), "quality-" + case.name, "PC")
    reader = PostgresApplicationReader(Path(args.dsn_file).read_text().strip(), args.database, owner.environment)
    # The same method backs DescribeGenerationSource; no RPC activation is constructed.
    published, policy = A2uiRuntimeService(reader, NoBusinessCalls(), reader).describe_generation_source(case.app, owner)
    membership = reader.generation_catalog(published.build.catalog.catalog_id, owner)
    if contract(published, membership) != policy:
        return {"case": case.name, "passed": False, "code": "SOURCE_CHANGED_DURING_PROBE", "modelCalls": 0}
    rows = admission_matrix(published, membership, policy)
    result: dict[str, Any] = {
        "case": case.name, "checks": rows, "modelCalls": 0,
        "passed": all(row["passed"] is not False for row in rows),
        "anchors": len(policy.required_anchors), "actions": len(policy.allowed_actions),
        "relativeBindings": len(policy.relative_data_bindings),
        "readOnlyDisplayBindings": len(policy.read_only_display_bindings),
        "visualReview": "NOT_PERFORMED",
    }
    if not args.live or not result["passed"]:
        return result
    from agent_workflow_runtime.a2ui_generation import DeepAgentA2uiGenerator
    from agent_workflow_runtime.model_factory import DeepSeekModelFactory
    from skillweave_contracts import TrustedContext as AgentContext
    from pydantic import SecretStr
    agent_owner = AgentContext.from_mapping({"userId": str(args.user_id), "environment": args.environment})
    key = SecretStr(Path(args.provider_key_file).read_text().strip())
    # Matches deploy.realchat.launcher.runtime: one flash request, 30s, 4096 tokens.
    factory = DeepSeekModelFactory(
        lambda reference, current: {"model_id": reference, "credential_ref": "quality-secret-file",
                                    "timeout_seconds": 30.0, "options": {"thinking": "disabled", "max_tokens": 4096}},
        lambda reference, current: key,
    )
    started = time.monotonic()
    result["modelCalls"] = 1  # Conservative attempt count, including construction failure.
    try:
        candidate = DeepAgentA2uiGenerator(lambda: factory.create("deepseek-v4-flash", agent_owner)).generate(
            case.intent, policy.model_dump(by_alias=True, mode="json"))
        data = candidate.model_dump(by_alias=True, mode="json")
        admission = check(published, membership, data, "generated-engineering-preserved")
        result["checks"].append(admission)
        result["passed"] = result["passed"] and admission["passed"]
        result["generatedComponents"] = len(components(data))
        result["layoutChanged"] = layout(data) != layout(source_candidate(published))
        if not result["layoutChanged"]:
            result["passed"] = False
            result["checks"].append({"check": "requested-layout-change", "passed": False, "code": "LAYOUT_UNCHANGED"})
    except Exception as error:
        result["passed"] = False
        result["checks"].append({"check": "generate", "passed": False, "code": safe_code(error)})
    result["durationMs"] = round((time.monotonic() - started) * 1000)
    # Capture concurrent source changes without replaying or repairing the candidate.
    try:
        current, current_policy = A2uiRuntimeService(reader, NoBusinessCalls(), reader).describe_generation_source(case.app, owner)
        if current != published or current_policy != policy:
            result["passed"] = False
            result["checks"].append({"check": "source-stable", "passed": False, "code": "SOURCE_CHANGED_DURING_PROBE"})
    except Exception as error:
        result["passed"] = False
        result["checks"].append({"check": "source-stable", "passed": False, "code": safe_code(error)})
    return result


def main() -> int:
    cli = parser()
    args = cli.parse_args()
    names = args.case or [case.name for case in CASES]
    if len(set(names)) != len(names):
        cli.error("duplicate cases are not allowed")
    selected = [case for case in CASES if case.name in names]
    if not (args.read_only or args.live):
        print(json.dumps({"mode": "plan", "modelCalls": 0,
                          "cases": [{"case": case.name, "app": case.app, "intent": case.intent} for case in selected]}, ensure_ascii=False))
        return 0
    if not all((args.dsn_file, args.database, args.environment)) or args.user_id is None:
        cli.error("execution requires --dsn-file, --database, --environment and --user-id")
    if args.live and (args.max_calls != len(selected) or not args.provider_key_file):
        cli.error("live requires --provider-key-file and --max-calls exactly equal to selected cases (1–4)")
    if args.read_only and args.max_calls not in (None, 0):
        cli.error("read-only mode does not permit model calls")
    logging.disable(logging.CRITICAL)
    results = []
    for case in selected:
        # Third-party diagnostics cannot leak contracts or secrets into the report.
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            try:
                result = run_case(args, case)
            except Exception as error:
                result = {"case": case.name, "passed": False, "code": safe_code(error), "modelCalls": 0}
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    failures = Counter(row.get("code", "CHECK_FAILED") for result in results
                       for row in result.get("checks", [result]) if row.get("passed") is False)
    print(json.dumps({"summary": {"cases": len(results), "passed": sum(result["passed"] for result in results),
                                "modelCalls": sum(result["modelCalls"] for result in results),
                                "failures": dict(failures), "visualReview": "NOT_PERFORMED"}}))
    return 0 if all(result["passed"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

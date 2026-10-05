"""Published A2UI Show/Load/Action runtime with fail-closed adapters."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import cast
from zoneinfo import ZoneInfo

from a2flow_capability.models import ExecutionResult, JsonObject, JsonValue, TrustedContext

from .jsonutil import (
    Lookup,
    read,
    reject_authority_keys,
    require_object,
    require_size,
    validate_schema,
    write,
)
from .ledger import PROTOCOL_VERSION, SurfaceLedger
from .models import (
    A2uiError,
    ActionBinding,
    ActionExecutionObservation,
    ApplicationBuild,
    BusinessPredicate,
    BusinessPredicateOperator,
    BusinessPredicateSource,
    BusinessPredicateVersion,
    CapabilityInvoker,
    ComposerDraftEffect,
    ComposerDraftEffectSpec,
    EmittedActionDeclaration,
    ExecutionSummary,
    MappingSource,
    PublishedApplication,
    PublishedApplicationReader,
    RequestMapping,
    RequestTransformType,
    ResultAdapter,
    ResultAdapterType,
    ResultOutcome,
    ResultSource,
    ResultTransform,
    ResultTransformType,
    RuntimeResult,
    RuntimeSession,
    ShowInputSource,
    TrustedCard,
)

_OBSERVATION_PRIVATE_KEYS = frozenset({
    "authorization", "cookie", "credential", "credentials",
    "credentialhandle", "runtimesessiontoken", "transportauthority", "targetendpoint",
})
_KEY_VALUE_SEPARATOR = "\N{FULLWIDTH COLON}"
_COLUMN_SEPARATOR = "\N{FULLWIDTH COMMA}"
_ARRAY_ITEM_SEPARATOR = "\N{IDEOGRAPHIC COMMA}"


def _trusted(context: TrustedContext, now: datetime | None = None) -> JsonObject:
    instant = now or datetime.now(UTC)
    business = instant.astimezone(ZoneInfo("Asia/Shanghai"))
    start = business.replace(hour=0, minute=0, second=0, microsecond=0)
    return {
        "runtime": {
            "time": {
                "currentEpochMillis": int(instant.timestamp() * 1000),
                "currentDayStartEpochMillis": int(start.timestamp() * 1000),
                "currentDayStartEpochSeconds": int(start.timestamp()),
                "zoneId": "Asia/Shanghai",
            }
        },
        "userId": context.user_id,
        "client": context.client,
        "operator": str(context.user_id),
        "environment": context.environment.value,
    }


def _execution_map(result: ExecutionResult) -> JsonObject:
    value: JsonObject = {
        "actionCode": result.action_code,
        "capabilityVersion": result.capability_version,
        "clientType": result.client_type,
        "requestedEnvironment": result.requested_environment.value,
        "resolvedEnvironment": result.resolved_environment.value,
        "success": result.success,
        "httpStatus": None,
        "contentType": None,
        "traceId": None,
        "data": copy.deepcopy(result.data),
        "errorCode": result.error_code.value if result.error_code is not None else None,
        "message": result.message,
    }
    return value


def _metadata(result: ExecutionResult) -> JsonObject:
    complete = _execution_map(result)
    complete.pop("data")
    return complete


def _child_context(context: TrustedContext, binding_id: str) -> TrustedContext:
    raw = json.dumps([context.request_id, binding_id], ensure_ascii=False, separators=(",", ":"))
    request_id = "a2ui:" + hashlib.sha256(raw.encode()).hexdigest()
    return TrustedContext(context.user_id, context.environment, request_id, context.client)


def _source(
    mapping: RequestMapping,
    action: JsonObject,
    params: JsonObject,
    trusted: JsonObject,
    previous: ExecutionResult | None,
) -> Lookup:
    if mapping.source is MappingSource.CONSTANT:
        return Lookup(True, copy.deepcopy(mapping.constant_value))
    if mapping.source_path is None:
        raise A2uiError("A2UI_REQUEST_MAPPING_INVALID")
    roots: dict[MappingSource, JsonValue] = {
        MappingSource.ACTION_CONTEXT: action,
        MappingSource.APP_PARAMS: params,
        MappingSource.TRUSTED_CONTEXT: trusted,
        MappingSource.CAPABILITY_PREVIOUS_RESULT: (
            _execution_map(previous) if previous is not None else None
        ),
    }
    return read(roots[mapping.source], mapping.source_path)


def map_request(
    mappings: tuple[RequestMapping, ...],
    *,
    action: JsonObject,
    params: JsonObject,
    trusted: JsonObject,
    previous: ExecutionResult | None,
) -> JsonObject:
    if len(mappings) > 256:
        raise A2uiError("A2UI_REQUEST_MAPPING_INVALID")
    result: JsonValue = {}
    targets: list[tuple[str, ...]] = []
    for mapping in mappings:
        from .jsonutil import tokens

        target = tokens(mapping.target_path, allow_root=False)
        if any(target[: len(item)] == item or item[: len(target)] == target for item in targets):
            raise A2uiError("A2UI_REQUEST_MAPPING_INVALID")
        targets.append(target)
        lookup = _source(mapping, action, params, trusted, previous)
        if not lookup.found:
            raise A2uiError("A2UI_REQUEST_MAPPING_SOURCE_MISSING")
        value = lookup.value
        transform = mapping.transform
        if transform is not None:
            if mapping.source not in {MappingSource.ACTION_CONTEXT, MappingSource.APP_PARAMS}:
                raise A2uiError("A2UI_REQUEST_MAPPING_INVALID")
            if transform.type is RequestTransformType.STRING_PREFIX:
                if (
                    not transform.prefix
                    or type(value) is not str
                    or transform.mask_source_path is not None
                ):
                    raise A2uiError("A2UI_REQUEST_MAPPING_INVALID")
                value = transform.prefix + value
            else:
                if transform.mask_source_path is None or not isinstance(value, list):
                    raise A2uiError("A2UI_REQUEST_MAPPING_INVALID")
                root: JsonValue = (
                    action if mapping.source is MappingSource.ACTION_CONTEXT else params
                )
                mask = read(root, transform.mask_source_path)
                if not mask.found or not isinstance(mask.value, list):
                    raise A2uiError("A2UI_REQUEST_MAPPING_INVALID")
                if any(type(flag) is not bool for flag in mask.value):
                    raise A2uiError("A2UI_REQUEST_MAPPING_INVALID")
                value = [item for item, flag in zip(value, mask.value, strict=False) if flag]
        result = write(result, mapping.target_path, value)
    return require_object(result, "A2UI_REQUEST_MAPPING_INVALID")


def observable_request(
    mappings: tuple[RequestMapping, ...],
    *,
    action: JsonObject,
    params: JsonObject,
    trusted: JsonObject,
) -> JsonObject:
    """Return exact mapped business values, without trusted/internal mappings."""

    visible = tuple(
        item for item in mappings
        if item.source in {
            MappingSource.ACTION_CONTEXT, MappingSource.APP_PARAMS, MappingSource.CONSTANT,
        }
    )
    mapped = map_request(
        visible, action=action, params=params, trusted=trusted, previous=None,
    )

    return require_object(_observable_value(mapped), "A2UI_ACTION_OBSERVATION_INVALID")


def _observable_value(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        return {
            key: _observable_value(child)
            for key, child in value.items()
            if key.replace("_", "").replace("-", "").lower()
            not in _OBSERVATION_PRIVATE_KEYS
        }
    if isinstance(value, list):
        return [_observable_value(child) for child in value]
    return copy.deepcopy(value)


def _message(value: JsonValue) -> JsonObject:
    message = require_object(value, "A2UI_ADAPTER_RESULT_INVALID")
    keys = [key for key in message if key != "version"]
    if message.get("version") != PROTOCOL_VERSION or len(keys) != 1:
        raise A2uiError("A2UI_ADAPTER_RESULT_INVALID")
    if keys[0] not in {"createSurface", "updateComponents", "updateDataModel", "deleteSurface"}:
        raise A2uiError("A2UI_ADAPTER_RESULT_INVALID")
    require_object(message[keys[0]], "A2UI_ADAPTER_RESULT_INVALID")
    return copy.deepcopy(message)


def _result_root(
    source: ResultSource, result: ExecutionResult, trusted: JsonObject, action: JsonObject
) -> JsonValue:
    roots: dict[ResultSource, JsonValue] = {
        ResultSource.CAPABILITY_DATA: result.data,
        ResultSource.CAPABILITY_META: _metadata(result),
        ResultSource.TRUSTED_CONTEXT: trusted,
        ResultSource.ACTION_CONTEXT: action,
    }
    if source not in roots:
        raise A2uiError("A2UI_ADAPTER_INVALID")
    return roots[source]


def _integer(value: JsonValue, code: str) -> int:
    if type(value) not in {int, float}:
        raise A2uiError(code)
    try:
        decimal = Decimal(str(value))
    except InvalidOperation:
        raise A2uiError(code) from None
    if decimal != decimal.to_integral_value():
        raise A2uiError(code)
    return int(decimal)


def _pagination_total(value: JsonValue) -> int:
    """Accept a numeric total or the canonical decimal string emitted for protobuf uint64."""

    if type(value) is str:
        if (
            not value
            or not value.isascii()
            or not value.isdigit()
            or (len(value) > 1 and value.startswith("0"))
        ):
            raise A2uiError("A2UI_ADAPTER_RESULT_INVALID")
        return int(value)
    return _integer(value, "A2UI_ADAPTER_RESULT_INVALID")


def _transform(
    transform: ResultTransform, value: JsonValue, target_path: str, action: JsonObject
) -> JsonValue:
    if transform.type is ResultTransformType.NUMBER_TO_STRING:
        if type(value) not in {int, float}:
            raise A2uiError("A2UI_ADAPTER_RESULT_INVALID")
        return format(Decimal(str(value)).normalize(), "f")
    if transform.type is ResultTransformType.MINOR_UNIT_TO_DECIMAL_STRING:
        if transform.scale != 2 or transform.component_ids is not None:
            raise A2uiError("A2UI_ADAPTER_INVALID")
        minor = _integer(value, "A2UI_ADAPTER_RESULT_INVALID")
        return f"{Decimal(minor).scaleb(-2):.2f}"
    if transform.type is ResultTransformType.BOOLEAN_ARRAY_TRUE_COUNT:
        if (
            transform.scale is not None
            or transform.component_ids is not None
            or not isinstance(value, list)
        ):
            raise A2uiError("A2UI_ADAPTER_INVALID")
        if any(type(item) is not bool for item in value):
            raise A2uiError("A2UI_ADAPTER_RESULT_INVALID")
        return sum(1 for item in value if item)
    if transform.type is ResultTransformType.ARRAY_TO_CHILDREN_PREFIX:
        ids = transform.component_ids
        segments = target_path.split("/")
        if (
            not isinstance(value, list)
            or not ids
            or len(ids) > 100
            or len(ids) != len(set(ids))
            or len(segments) != 5
            or segments[1:3] != ["updateComponents", "components"]
            or segments[4] != "children"
            or not segments[3].isdigit()
            or (len(segments[3]) > 1 and segments[3].startswith("0"))
        ):
            raise A2uiError("A2UI_ADAPTER_INVALID")
        return list(ids[: len(value)])
    if transform.type is ResultTransformType.ARRAY_OBJECT_TO_OPTIONS:
        if (
            not isinstance(value, list)
            or len(value) > 100
            or transform.value_path is None
            or not transform.label_columns
            or len(transform.label_columns) > 20
            or transform.label_separator is None
            or not transform.label_separator
            or len(transform.label_separator) > 8
        ):
            raise A2uiError("A2UI_ADAPTER_INVALID")
        options: list[JsonValue] = []
        seen: set[str] = set()
        for raw_item in value:
            item = require_object(raw_item, "A2UI_ADAPTER_RESULT_INVALID")
            value_lookup = read(item, transform.value_path)
            if (
                not value_lookup.found
                or type(value_lookup.value) is not str
                or not value_lookup.value
                or value_lookup.value in seen
            ):
                raise A2uiError("A2UI_ADAPTER_RESULT_INVALID")
            seen.add(value_lookup.value)
            labels: list[str] = []
            for column in transform.label_columns:
                lookup = read(item, column.source_path)
                if not lookup.found:
                    raise A2uiError("A2UI_ADAPTER_RESULT_INVALID")
                labels.append(
                    f"{column.label}{_KEY_VALUE_SEPARATOR}{_label_value(lookup.value)}"
                )
            options.append({
                "label": transform.label_separator.join(labels),
                "value": value_lookup.value,
            })
        return options
    total = _pagination_total(value)
    raw_page: JsonValue = transform.page_number
    if transform.action_page_path is not None:
        page_lookup = read(action, transform.action_page_path)
        raw_page = page_lookup.value if page_lookup.found else None
    size = _integer(transform.page_size, "A2UI_ADAPTER_INVALID")
    page = _integer(raw_page, "A2UI_ADAPTER_RESULT_INVALID")
    if total < 0 or total > 9007199254740991 or size <= 0 or page <= 0:
        raise A2uiError("A2UI_ADAPTER_RESULT_INVALID")
    pages = math.ceil(total / size)
    if total > 0 and page > pages:
        raise A2uiError("A2UI_ADAPTER_RESULT_INVALID")
    shown_page = 0 if total == 0 else page
    return {
        "total": total,
        "pageSize": size,
        "pageNum": shown_page,
        "totalPages": pages,
        "prevPage": max(1, page - 1),
        "nextPage": 1 if total == 0 else min(pages, page + 1),
        "prevDisabled": total == 0 or page == 1,
        "nextDisabled": total == 0 or page >= pages,
        "display": {"pageNum": str(shown_page), "totalPages": str(pages), "total": str(total)},
    }


def _scalar_text(value: JsonValue) -> str:
    if type(value) is str:
        return value
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) in {int, float}:
        return format(Decimal(str(value)).normalize(), "f")
    raise A2uiError("A2UI_ADAPTER_RESULT_INVALID")


def _label_value(value: JsonValue) -> str:
    if isinstance(value, list):
        return _ARRAY_ITEM_SEPARATOR.join(_scalar_text(item) for item in value)
    return _scalar_text(value)


def _composer_draft_effect(
    spec: ComposerDraftEffectSpec | None,
    result: ExecutionResult,
    request_id: str,
) -> tuple[ComposerDraftEffect, ...]:
    if spec is None:
        return ()
    items_lookup = read(result.data, spec.items_path)
    if (
        not items_lookup.found
        or not isinstance(items_lookup.value, list)
        or not items_lookup.value
        or len(items_lookup.value) > 100
    ):
        raise A2uiError("A2UI_COMPOSER_EFFECT_INVALID")
    lines: list[str] = []
    for raw_item in items_lookup.value:
        item = require_object(raw_item, "A2UI_COMPOSER_EFFECT_INVALID")
        values: list[str] = []
        for column in spec.columns:
            lookup = read(item, column.source_path)
            if not lookup.found or isinstance(lookup.value, list):
                raise A2uiError("A2UI_COMPOSER_EFFECT_INVALID")
            try:
                text = _scalar_text(lookup.value)
            except A2uiError:
                raise A2uiError("A2UI_COMPOSER_EFFECT_INVALID") from None
            values.append(f"{column.label}{_KEY_VALUE_SEPARATOR}{text}")
        lines.append(_COLUMN_SEPARATOR.join(values))
    text = "\n".join(lines)
    if not text or len(text) > 4000:
        raise A2uiError("A2UI_COMPOSER_EFFECT_INVALID")
    return (ComposerDraftEffect(spec.type, spec.mode, request_id, text),)


def adapt(
    ledger: SurfaceLedger,
    outcome: ResultOutcome,
    adapters: tuple[ResultAdapter, ...],
    result: ExecutionResult,
    trusted: JsonObject,
    action: JsonObject,
) -> tuple[tuple[JsonObject, ...], SurfaceLedger]:
    if outcome is ResultOutcome.NO_UI_MESSAGES:
        if adapters:
            raise A2uiError("A2UI_ADAPTER_INVALID")
        return (), ledger
    if not adapters:
        raise A2uiError("A2UI_ADAPTER_INVALID")
    messages: list[JsonObject] = []
    previous_order = 0
    for adapter in adapters:
        if adapter.order <= previous_order:
            raise A2uiError("A2UI_ADAPTER_INVALID")
        previous_order = adapter.order
        if adapter.type is ResultAdapterType.A2UI_PASSTHROUGH:
            if (
                adapter.source not in {ResultSource.CAPABILITY_DATA, ResultSource.CAPABILITY_META}
                or adapter.source_path is None
                or adapter.cardinality not in {"ONE", "MANY"}
            ):
                raise A2uiError("A2UI_ADAPTER_INVALID")
            lookup = read(
                _result_root(adapter.source, result, trusted, action), adapter.source_path
            )
            if not lookup.found or lookup.value is None:
                if adapter.required:
                    raise A2uiError("A2UI_ADAPTER_SOURCE_MISSING")
                continue
            raw = [lookup.value] if adapter.cardinality == "ONE" else lookup.value
            if not isinstance(raw, list):
                raise A2uiError("A2UI_ADAPTER_RESULT_INVALID")
            messages.extend(_message(item) for item in raw)
            continue
        if adapter.message_template is None or adapter.bindings is None:
            raise A2uiError("A2UI_ADAPTER_INVALID")
        rendered: JsonValue = copy.deepcopy(adapter.message_template)
        for binding in adapter.bindings:
            lookup = (
                Lookup(True, copy.deepcopy(binding.constant_value))
                if binding.source is ResultSource.CONSTANT
                else read(
                    _result_root(binding.source, result, trusted, action), binding.source_path or ""
                )
            )
            if not lookup.found or lookup.value is None:
                if binding.required:
                    raise A2uiError("A2UI_ADAPTER_SOURCE_MISSING")
                continue
            target_value: JsonValue = lookup.value
            if binding.transform is not None:
                target_value = _transform(
                    binding.transform, target_value, binding.target_path, action
                )
            rendered = write(rendered, binding.target_path, target_value)
        messages.append(_message(rendered))
    if not messages:
        return (), ledger
    next_ledger = ledger.reduce(messages)
    return tuple(messages), next_ledger


def _predicate(predicate: BusinessPredicate | None, result: ExecutionResult) -> bool:
    if not result.success:
        return False
    if predicate is None:
        return True
    if predicate.version is not BusinessPredicateVersion.JSON_POINTER_V1:
        raise A2uiError("A2UI_BUSINESS_PREDICATE_INVALID")
    for clause in predicate.all_of:
        if clause.source is not BusinessPredicateSource.CAPABILITY_DATA:
            raise A2uiError("A2UI_BUSINESS_PREDICATE_INVALID")
        lookup = read(result.data, clause.source_path)
        if not lookup.found or lookup.value is None:
            return False
        if clause.operator is BusinessPredicateOperator.EQUALS:
            actual, expected = lookup.value, clause.expected_value
            if type(actual) in {int, float} and type(expected) in {int, float}:
                matched = Decimal(str(actual)) == Decimal(str(expected))
            else:
                matched = actual == expected
        elif clause.operator is BusinessPredicateOperator.GREATER_THAN:
            if type(lookup.value) not in {int, float} or type(clause.expected_value) not in {
                int,
                float,
            }:
                return False
            matched = Decimal(str(lookup.value)) > Decimal(str(clause.expected_value))
        elif clause.operator is BusinessPredicateOperator.IS_ARRAY:
            if clause.expected_value is not True:
                raise A2uiError("A2UI_BUSINESS_PREDICATE_INVALID")
            matched = isinstance(lookup.value, list)
        else:
            raise A2uiError("A2UI_BUSINESS_PREDICATE_INVALID")
        if not matched:
            return False
    return True


@dataclass(frozen=True, slots=True)
class _Selected:
    succeeded: bool
    outcome: ResultOutcome
    adapters: tuple[ResultAdapter, ...]
    complete: bool
    branch_id: str | None


def _select(binding: ActionBinding, result: ExecutionResult) -> _Selected:
    if not _predicate(binding.business_success_predicate, result):
        return _Selected(
            False, binding.failure_outcome, binding.failure_result_adapters, False, None
        )
    for branch in binding.success_branches:
        if _predicate(branch.when, result):
            return _Selected(
                True,
                branch.outcome,
                branch.result_adapters,
                branch.complete_workflow_interaction_on_success,
                branch.branch_id,
            )
    return _Selected(
        True,
        binding.success_outcome,
        binding.result_adapters,
        binding.complete_workflow_interaction_on_success,
        None,
    )


def _show(
    build: ApplicationBuild, params: JsonObject, trusted: JsonObject
) -> tuple[tuple[JsonObject, ...], SurfaceLedger]:
    validate_schema(build.params_schema, params, "A2UI_PARAMS_INVALID")
    messages: list[JsonObject] = copy.deepcopy(list(build.initial_messages))
    for binding in build.input_bindings:
        if binding.target_message_index >= len(messages):
            raise A2uiError("A2UI_SHOW_BINDING_INVALID")
        if binding.source is ShowInputSource.CONSTANT:
            lookup = Lookup(True, copy.deepcopy(binding.constant_value))
        else:
            if binding.source_path is None:
                raise A2uiError("A2UI_SHOW_BINDING_INVALID")
            root: JsonValue = params if binding.source is ShowInputSource.APP_PARAMS else trusted
            lookup = read(root, binding.source_path)
        if not lookup.found or lookup.value is None:
            if binding.required:
                raise A2uiError("A2UI_SHOW_SOURCE_MISSING")
            continue
        rendered = write(messages[binding.target_message_index], binding.target_path, lookup.value)
        messages[binding.target_message_index] = require_object(
            rendered, "A2UI_SHOW_BINDING_INVALID"
        )
    ledger = SurfaceLedger.empty().reduce(messages)
    return tuple(messages), ledger


def _session(build: ApplicationBuild) -> RuntimeSession:
    return RuntimeSession(
        str(uuid.uuid4()),
        build.app_build_id,
        build.protocol_version,
        build.catalog.catalog_id,
        build.catalog.revision,
        build.catalog.digest,
    )


class A2uiRuntimeService:
    def __init__(
        self, releases: PublishedApplicationReader, capabilities: CapabilityInvoker
    ) -> None:
        self._releases = releases
        self._capabilities = capabilities

    def describe(self, app_code: str, context: TrustedContext) -> PublishedApplication:
        self._check_context(context)
        return self._releases.current(app_code, context)

    def activate(
        self,
        app_code: str,
        params: JsonObject,
        context: TrustedContext,
    ) -> RuntimeResult:
        self._check_context(context)
        published = self._releases.current(app_code, context)
        trusted = _trusted(context)
        messages, ledger = _show(published.build, params, trusted)
        all_messages = list(messages)
        executions: list[ExecutionSummary] = []
        previous: ExecutionResult | None = None
        for binding in published.build.load_bindings:
            arguments = map_request(
                binding.request_mappings,
                action={},
                params=params,
                trusted=trusted,
                previous=previous,
            )
            result = self._capabilities.execute_action_code(
                binding.capability.action_code,
                arguments,
                _child_context(context, binding.binding_id),
            )
            if result.action_code != binding.capability.action_code:
                raise A2uiError("A2UI_CAPABILITY_RESULT_INVALID")
            succeeded = result.success
            outcome = binding.success_outcome if succeeded else binding.failure_outcome
            adapters = binding.result_adapters if succeeded else binding.failure_result_adapters
            emitted, ledger = adapt(ledger, outcome, adapters, result, trusted, {})
            all_messages.extend(emitted)
            executions.append(
                ExecutionSummary(
                    binding.binding_id,
                    result.action_code,
                    succeeded,
                    result.capability_version,
                    None if succeeded else (result.error_code.value if result.error_code else None),
                )
            )
            previous = result
            if not succeeded:
                break
        session = _session(published.build)
        return self._response(
            published, params, tuple(all_messages), ledger, tuple(executions), False, None, session
        )

    def act(
        self,
        card: TrustedCard,
        correlation_id: str,
        idempotency_key: str,
        action_message: JsonObject,
        context: TrustedContext,
    ) -> RuntimeResult:
        self._check_context(context)
        if (
            card.user_id != context.user_id
            or not card.app_code.strip()
            or context.request_id != idempotency_key
        ):
            raise A2uiError("A2UI_CARD_CONTEXT_MISMATCH")
        published = self._releases.current(card.app_code, context)
        build = published.build
        if (
            not correlation_id.strip()
            or not idempotency_key.strip()
        ):
            raise A2uiError("A2UI_CARD_CONTEXT_MISMATCH")
        validate_schema(build.params_schema, card.params, "A2UI_PARAMS_INVALID")
        ledger = SurfaceLedger.replay(card.snapshot)
        binding, action_context = self._resolve_action(build, ledger, action_message)
        trusted = _trusted(context)
        arguments = map_request(
            binding.request_mappings,
            action=action_context,
            params=card.params,
            trusted=trusted,
            previous=None,
        )
        observable_arguments = observable_request(
            binding.request_mappings,
            action=action_context,
            params=card.params,
            trusted=trusted,
        )
        result = self._capabilities.execute_action_code(
            binding.capability.action_code, arguments, _child_context(context, binding.binding_id)
        )
        if result.action_code != binding.capability.action_code:
            raise A2uiError("A2UI_CAPABILITY_RESULT_INVALID")
        capability_error = result.error_code.value if result.error_code else None
        try:
            selected = _select(binding, result)
        except A2uiError as error:
            observation = ActionExecutionObservation(
                binding.binding_id, result.action_code, observable_arguments,
                _observable_value(result.data), result.success, None,
                capability_error, error.code,
            )
            summary = ExecutionSummary(
                binding.binding_id, result.action_code, result.success,
                result.capability_version, capability_error,
            )
            return self._response(
                published, card.params, (), ledger, (summary,), False, None, _session(build),
                action_observation=observation,
            )
        try:
            messages, next_ledger = adapt(
                ledger, selected.outcome, selected.adapters, result, trusted, action_context
            )
            composer_draft_effects = (
                _composer_draft_effect(
                    binding.composer_draft_effect, result, idempotency_key
                )
                if selected.succeeded
                else ()
            )
        except A2uiError as error:
            observation = ActionExecutionObservation(
                binding.binding_id, result.action_code, observable_arguments,
                _observable_value(result.data), result.success, selected.succeeded,
                capability_error, error.code,
            )
            summary = ExecutionSummary(
                binding.binding_id, result.action_code, selected.succeeded,
                result.capability_version,
                None if selected.succeeded else capability_error,
            )
            return self._response(
                published, card.params, (), ledger, (summary,), False, None, _session(build),
                action_observation=observation,
            )
        observation = ActionExecutionObservation(
            binding.binding_id, result.action_code, observable_arguments,
            _observable_value(result.data), result.success, selected.succeeded,
            capability_error, None,
        )
        summary = ExecutionSummary(
            binding.binding_id,
            result.action_code,
            selected.succeeded,
            result.capability_version,
            None
            if selected.succeeded
            else (result.error_code.value if result.error_code else None),
        )
        return self._response(
            published,
            card.params,
            messages,
            next_ledger,
            (summary,),
            selected.complete,
            selected.branch_id,
            _session(build),
            action_observation=observation,
            composer_draft_effects=composer_draft_effects,
        )

    def _resolve_action(
        self, build: ApplicationBuild, ledger: SurfaceLedger, message: JsonObject
    ) -> tuple[ActionBinding, JsonObject]:
        if set(message) != {"version", "action"} or message.get("version") != PROTOCOL_VERSION:
            raise A2uiError("A2UI_ACTION_INVALID")
        action = require_object(message["action"], "A2UI_ACTION_INVALID")
        if set(action) != {"name", "surfaceId", "sourceComponentId", "timestamp", "context"}:
            raise A2uiError("A2UI_ACTION_INVALID")
        raw_name, raw_surface_id, raw_component_id = (
            action["name"],
            action["surfaceId"],
            action["sourceComponentId"],
        )
        if any(
            type(value) is not str or not value.strip()
            for value in (raw_name, raw_surface_id, raw_component_id)
        ):
            raise A2uiError("A2UI_ACTION_INVALID")
        name = cast(str, raw_name)
        surface_id = cast(str, raw_surface_id)
        component_id = cast(str, raw_component_id)
        try:
            timestamp = datetime.fromisoformat(str(action["timestamp"]).replace("Z", "+00:00"))
        except ValueError:
            raise A2uiError("A2UI_ACTION_INVALID") from None
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise A2uiError("A2UI_ACTION_INVALID")
        matches = [
            item
            for item in build.action_bindings
            if item.surface_id == surface_id and item.action_code == name
        ]
        if not matches:
            raise A2uiError("A2UI_ACTION_NOT_BOUND")
        if len(matches) != 1:
            raise A2uiError("A2UI_BUILD_ACTION_CLOSURE_INVALID")
        binding = matches[0]
        if not ledger.has_surface(surface_id):
            raise A2uiError("A2UI_SURFACE_NOT_FOUND")
        if component_id != binding.source_component_id or component_id not in (
            binding.allowed_source_component_ids
        ):
            raise A2uiError("A2UI_ACTION_SOURCE_INVALID")
        declarations = [
            item
            for item in build.action_declarations
            if item.surface_id == surface_id
            and item.source_component_id == component_id
            and item.action_code == name
        ]
        if (
            len(declarations) != 1
            or declarations[0].context_template_digest != binding.declaration_digest
        ):
            raise A2uiError("A2UI_BUILD_ACTION_CLOSURE_INVALID")
        context_value = require_object(action["context"], "A2UI_ACTION_CONTEXT_INVALID")
        require_size(context_value, 64 * 1024, "A2UI_ACTION_CONTEXT_INVALID")
        reject_authority_keys(context_value)
        validate_schema(binding.context_schema, context_value, "A2UI_ACTION_CONTEXT_INVALID")
        return binding, context_value

    def _response(
        self,
        published: PublishedApplication,
        params: JsonObject,
        messages: tuple[JsonObject, ...],
        ledger: SurfaceLedger,
        executions: tuple[ExecutionSummary, ...],
        complete: bool,
        branch: str | None,
        session: RuntimeSession,
        *,
        action_observation: ActionExecutionObservation | None = None,
        composer_draft_effects: tuple[ComposerDraftEffect, ...] = (),
    ) -> RuntimeResult:
        actions = tuple(
            EmittedActionDeclaration(
                surfaceId=item.surface_id,
                sourceComponentId=item.source_component_id,
                actionCode=item.action_code,
                contextSchema=item.context_schema,
            )
            for item in published.build.action_bindings
        )
        return RuntimeResult(
            published.release,
            copy.deepcopy(params),
            messages,
            ledger.snapshot(),
            executions,
            actions,
            complete,
            branch,
            session,
            published.build.interaction_mode,
            (
                action_observation.business_success
                if action_observation is not None
                and action_observation.business_success is not None
                else all(item.success for item in executions)
            ),
            action_observation,
            composer_draft_effects,
        )

    def _check_context(self, context: TrustedContext) -> None:
        if context.client not in {"PC", "APP"}:
            raise A2uiError("A2UI_CLIENT_NOT_SUPPORTED")

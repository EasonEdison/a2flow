"""Explicit owner-scoped follow-up tasks and durable business dispatch receipts.

This repository never resolves business cases from model prose or reminder reads.
A committed operation claim is dispatched once; ambiguous claims are not retried.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import uuid
from typing import Any, Callable, Mapping, TypedDict

from skillweave_contracts.user_id import require_user_id
from .errors import BsideError
from .interaction_continuation import continuation_reference


class ProcessingContext(TypedDict):
    taskId: str
    activityId: str
    runId: str
    attentionId: str
    conversationId: str
    objective: str
    status: str


class OperationEnvelope(TypedDict):
    status: str
    operationId: str
    requestId: str
    replayed: bool
    result: dict[str, Any] | None
    errorCode: str | None


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _time(value: Any) -> Any:
    return value.isoformat() if isinstance(value, dt.datetime) else value


def _context(row: Mapping[str, Any]) -> ProcessingContext:
    return {'taskId': row['task_id'], 'activityId': row['activity_id'], 'runId': row['run_id'],
            'attentionId': row['attention_id'], 'conversationId': str(row['conversation_id']),
            'objective': row['objective'], 'status': row['status']}


class ProcessingTasksRepository:
    def __init__(self, connection_factory: Callable[[], Any], work_activities: Any) -> None:
        self._factory = connection_factory
        self._activities = work_activities

    @staticmethod
    def _scope(user_id: int, environment: str, conversation_id: str) -> tuple[int, str, int]:
        require_user_id(user_id)
        if environment not in {'PRT', 'ONLINE'} or not re.fullmatch(r'[1-9][0-9]*', str(conversation_id)):
            raise BsideError('INVALID_PROCESSING_SCOPE', 400)
        return user_id, environment, int(conversation_id)

    @staticmethod
    def _row(connection: Any, scope: tuple[int, str, int], task_id: str, *, lock: bool = False) -> Any:
        row = connection.execute('SELECT * FROM processing_tasks WHERE user_id=%s AND environment=%s '
                                 'AND conversation_id=%s AND task_id=%s' + (' FOR UPDATE' if lock else ''),
                                 (*scope, task_id)).fetchone()
        if row is None:
            raise BsideError('PROCESSING_TASK_NOT_FOUND', 404)
        return row

    @staticmethod
    def _waiting_card(connection: Any, scope: tuple[int, str, int], task_id: str) -> bool:
        return connection.execute(
            "SELECT 1 FROM processing_cards p JOIN chat_a2ui_cards c ON c.user_id=p.user_id "
            "AND c.environment=p.environment AND c.conversation_id=p.conversation_id::text AND c.card_id=p.card_id "
            "WHERE p.user_id=%s AND p.environment=%s AND p.conversation_id=%s AND p.task_id=%s "
            "AND c.status IN ('WAITING_ACTION','EXECUTING') LIMIT 1", (*scope, task_id)).fetchone() is not None

    def get_context(self, *, user_id: int, environment: str, conversation_id: str,
                    task_id: str) -> ProcessingContext:
        scope = self._scope(user_id, environment, conversation_id)
        with self._factory() as connection:
            return _context(self._row(connection, scope, task_id))

    def begin_turn(self, *, user_id: int, environment: str, conversation_id: str,
                   request_id: str, text: str, references: list[dict[str, Any]],
                   target: Mapping[str, str] | None = None, task_id: str | None = None,
                   ) -> tuple[bool, ProcessingContext, dict[str, Any], dict[str, Any]]:
        """Atomically create the user/assistant pair and explicit task relation."""
        scope = self._scope(user_id, environment, conversation_id)
        if bool(target) == bool(task_id) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', request_id):
            raise BsideError('INVALID_PROCESSING_REQUEST', 400)
        activity = None
        if target:
            activity = self._activities.get(user_id=user_id, environment=environment,
                                            activity_id=target['activityId'])
            if not any(a['attentionId'] == target['attentionId'] and a['kind'] == 'business'
                       for a in activity['attentionItems']):
                raise BsideError('BUSINESS_ATTENTION_NOT_FOUND', 404)
        # Reference readAt is intentionally excluded: refresh must not change request identity.
        digest = hashlib.sha256(_json({'text': text, 'target': target, 'taskId': task_id,
            'referenceActivities': [r.get('activityId') for r in references]}).encode()).hexdigest()
        with self._factory() as connection:
            owner = connection.execute('SELECT user_id FROM conversations WHERE id=%s FOR UPDATE',
                                       (scope[2],)).fetchone()
            if owner is None or owner['user_id'] != user_id:
                raise BsideError('CONVERSATION_NOT_FOUND', 404)
            prior = connection.execute('SELECT * FROM processing_turns WHERE user_id=%s AND environment=%s '
                                       'AND conversation_id=%s AND request_id=%s', (*scope, request_id)).fetchone()
            if prior:
                if prior['request_digest'] != digest:
                    raise BsideError('PROCESSING_REQUEST_CONFLICT', 409)
                rows = connection.execute('SELECT * FROM messages WHERE id IN (%s,%s) ORDER BY id',
                                          (prior['input_message_id'], prior['assistant_message_id'])).fetchall()
                return False, _context(self._row(connection, scope, prior['task_id'])), dict(rows[0]), dict(rows[1])
            if target:
                task_id = 'handling-' + uuid.uuid4().hex
                task = connection.execute('INSERT INTO processing_tasks '
                    '(task_id,user_id,environment,conversation_id,activity_id,run_id,attention_id,objective,status) '
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'OPEN') RETURNING *",
                    (task_id, *scope, target['activityId'], activity['runId'], target['attentionId'], text)).fetchone()
            else:
                task = self._row(connection, scope, str(task_id), lock=True)
                if task['status'] in {'RESOLVED', 'FAILED', 'UNKNOWN'}:
                    raise BsideError('PROCESSING_TASK_NOT_CONTINUABLE', 409)
            context = _context(task)
            contents = [('user', {'text': text, 'delivery': 'submitted', 'runReferences': references,
                                  'processingTaskId': task_id}),
                        ('assistant', {'text': '', 'delivery': 'running', 'parts': [], 'processingTaskId': task_id})]
            rows = []
            for role, content in contents:
                rows.append(dict(connection.execute('INSERT INTO messages(conversation_id,role,content) '
                    'VALUES (%s,%s,%s::jsonb) RETURNING *', (scope[2], role, _json(content))).fetchone()))
            connection.execute('INSERT INTO processing_turns(user_id,environment,conversation_id,request_id,'
                'request_digest,task_id,input_message_id,assistant_message_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                (*scope, request_id, digest, task_id, rows[0]['id'], rows[1]['id']))
            if target:
                connection.execute('UPDATE processing_tasks SET origin_message_id=%s WHERE task_id=%s',
                                   (rows[0]['id'], task_id))
            return True, context, rows[0], rows[1]

    def bind_card(self, *, user_id: int, environment: str, conversation_id: str,
                  task_id: str, card_id: str) -> None:
        scope = self._scope(user_id, environment, conversation_id)
        if not isinstance(card_id, str) or not 1 <= len(card_id) <= 256:
            raise BsideError('INVALID_PROCESSING_CARD', 400)
        with self._factory() as connection:
            task = self._row(connection, scope, task_id, lock=True)
            if task['status'] in {'RESOLVED', 'FAILED', 'UNKNOWN'}:
                raise BsideError('PROCESSING_TASK_NOT_CONTINUABLE', 409)
            saved_card = connection.execute('SELECT status,binding_metadata FROM chat_a2ui_cards WHERE user_id=%s '
                'AND environment=%s AND conversation_id=%s AND card_id=%s',
                (user_id, environment, str(scope[2]), card_id)).fetchone()
            if saved_card is None or saved_card['binding_metadata'].get('processingTaskId') != task_id:
                raise BsideError('PROCESSING_CARD_NOT_FOUND', 404)
            connection.execute('INSERT INTO processing_cards(user_id,environment,conversation_id,card_id,task_id) '
                               'VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING', (*scope, card_id, task_id))
            row = connection.execute('SELECT task_id FROM processing_cards WHERE user_id=%s AND environment=%s '
                                     'AND conversation_id=%s AND card_id=%s', (*scope, card_id)).fetchone()
            if row['task_id'] != task_id:
                raise BsideError('PROCESSING_CARD_CONFLICT', 409)
            if saved_card['status'] == 'WAITING_ACTION':
                connection.execute("UPDATE processing_tasks SET status='WAITING_INPUT',updated_at=now() WHERE task_id=%s", (task_id,))

    def context_for_card(self, *, user_id: int, environment: str, conversation_id: str,
                         card_id: str) -> ProcessingContext | None:
        scope = self._scope(user_id, environment, conversation_id)
        with self._factory() as connection:
            row = connection.execute('SELECT task_id FROM processing_cards WHERE user_id=%s AND environment=%s '
                                     'AND conversation_id=%s AND card_id=%s', (*scope, card_id)).fetchone()
            card = connection.execute('SELECT binding_metadata FROM chat_a2ui_cards WHERE user_id=%s '
                                      'AND environment=%s AND conversation_id=%s AND card_id=%s',
                                      (user_id, environment, str(scope[2]), card_id)).fetchone()
            metadata_task = card['binding_metadata'].get('processingTaskId') if card else None
            if row is None and (card is None or 'processingTaskId' not in card['binding_metadata']):
                return None
            if row is None or not isinstance(metadata_task, str) or metadata_task != row['task_id']:
                raise BsideError('PROCESSING_CARD_BINDING_UNCONFIRMED', 409)
            return _context(self._row(connection, scope, row['task_id']))

    def bind_continuation(self, *, user_id: int, environment: str, conversation_id: str,
                          task_id: str, card_id: str, input_message_id: int,
                          assistant_message_id: int,
                          confirmation_request_id: str | None = None) -> ProcessingContext:
        scope = self._scope(user_id, environment, conversation_id)
        reference = continuation_reference(card_id, confirmation_request_id)
        with self._factory() as connection:
            task = self._row(connection, scope, task_id, lock=True)
            card = connection.execute('SELECT task_id FROM processing_cards WHERE user_id=%s AND environment=%s '
                                      'AND conversation_id=%s AND card_id=%s', (*scope, card_id)).fetchone()
            if card is None or card['task_id'] != task_id:
                raise BsideError('PROCESSING_CARD_NOT_FOUND', 404)
            for message_id, role in ((input_message_id, 'user'), (assistant_message_id, 'assistant')):
                row = connection.execute("UPDATE messages SET content=content || %s::jsonb WHERE id=%s "
                    "AND conversation_id=%s AND role=%s AND ref_kind='temporary_interaction' AND ref_id=%s RETURNING id",
                    (_json({'processingTaskId': task_id}), message_id, scope[2], role, reference)).fetchone()
                if row is None:
                    raise BsideError('PROCESSING_MESSAGE_NOT_FOUND', 404)
            connection.execute('INSERT INTO processing_turns(user_id,environment,conversation_id,request_id,'
                'request_digest,task_id,input_message_id,assistant_message_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) '
                'ON CONFLICT DO NOTHING', (*scope, 'card:' + reference, reference, task_id, input_message_id, assistant_message_id))
            if task['status'] == 'WAITING_INPUT' and not self._waiting_card(connection, scope, task_id):
                has_result = connection.execute("SELECT 1 FROM processing_operations WHERE task_id=%s AND status='RETURNED' LIMIT 1",
                                                (task_id,)).fetchone()
                connection.execute("UPDATE processing_tasks SET status=%s,updated_at=now() WHERE task_id=%s",
                                   ('RESULT_RECORDED' if has_result else 'OPEN', task_id))
            return _context(self._row(connection, scope, task_id))

    @staticmethod
    def _confirmed_write(connection: Any, scope: tuple[int, str, int], task_id: str,
                         card_id: str, turn_id: str, tool_call_id: str,
                         ability_key: str, encoded: str) -> bool:
        """Admit only the exact durably claimed card; never infer approval from prose."""
        if not isinstance(card_id, str) or not card_id or len(card_id) > 128:
            return False
        row = connection.execute(
            "SELECT c.binding_metadata,r.payload FROM processing_cards p "
            "JOIN chat_a2ui_cards c ON c.user_id=p.user_id AND c.environment=p.environment "
            "AND c.conversation_id=p.conversation_id::text AND c.card_id=p.card_id "
            "JOIN chat_a2ui_action_requests r ON r.user_id=c.user_id AND r.environment=c.environment "
            "AND r.conversation_id=c.conversation_id AND r.card_id=c.card_id "
            "AND r.request_id=c.active_request_id "
            "WHERE p.user_id=%s AND p.environment=%s AND p.conversation_id=%s AND p.task_id=%s "
            "AND p.card_id=%s AND c.status='EXECUTING' AND r.state='CLAIMED'",
            (*scope, task_id, card_id)).fetchone()
        if row is None:
            return False
        metadata = row['binding_metadata']
        binding = metadata.get('approval', {})
        receipt = binding.get('receipt', {})
        context = metadata.get('approvalProcessingContext', {})
        if (metadata.get('definitionSource') != 'TEMPORARY'
                or metadata.get('processingTaskId') != task_id
                or context.get('taskId') != task_id
                or context.get('conversationId') != str(scope[2])
                or metadata.get('approvalProcessingTurnId') != turn_id
                or metadata.get('toolCallId') != tool_call_id
                or receipt.get('user_id') != scope[0] or receipt.get('environment') != scope[1]
                or receipt.get('run_id') != str(scope[2]) or receipt.get('tool_call_id') != tool_call_id
                or receipt.get('action_code') != ability_key
                or receipt.get('side_effect_level') not in {'WRITE', 'DESTRUCTIVE'}
                or receipt.get('approval_policy') != 'REQUEST_APPROVAL'
                or _json(binding.get('arguments')) != encoded
                or receipt.get('arguments_digest') != hashlib.sha256(encoded.encode()).hexdigest()
                or row['payload'] != {'actionName': 'submit', 'inputs': {'confirmation': ['approve']}}):
            return False
        return connection.execute(
            "SELECT 1 FROM processing_cards p JOIN chat_a2ui_cards c ON c.user_id=p.user_id "
            "AND c.environment=p.environment AND c.conversation_id=p.conversation_id::text "
            "AND c.card_id=p.card_id WHERE p.user_id=%s AND p.environment=%s "
            "AND p.conversation_id=%s AND p.task_id=%s AND p.card_id<>%s "
            "AND c.status IN ('WAITING_ACTION','EXECUTING') LIMIT 1",
            (*scope, task_id, card_id)).fetchone() is None

    def execute_operation(self, *, user_id: int, environment: str, conversation_id: str,
                          task_id: str, turn_id: str, tool_call_id: str, ability_key: str,
                          arguments: Mapping[str, Any], invoke: Callable[[str], dict[str, Any]],
                          confirmation_card_id: str | None = None) -> OperationEnvelope:
        scope = self._scope(user_id, environment, conversation_id)
        encoded = _json(dict(arguments))
        if len(encoded.encode()) > 262144 or not ability_key or len(ability_key) > 256:
            raise BsideError('PROCESSING_ARGUMENTS_INVALID', 400)
        digest = hashlib.sha256((ability_key + '\0' + encoded).encode()).hexdigest()
        with self._factory() as connection:
            task = self._row(connection, scope, task_id, lock=True)
            turn = connection.execute('SELECT 1 FROM processing_turns WHERE user_id=%s AND environment=%s '
                'AND conversation_id=%s AND task_id=%s AND input_message_id::text=%s',
                (*scope, task_id, turn_id)).fetchone()
            if turn is None:
                raise BsideError('PROCESSING_TURN_NOT_FOUND', 404)
            prior = connection.execute('SELECT * FROM processing_operations WHERE task_id=%s AND operation_digest=%s',
                                       (task_id, digest)).fetchone()
            if prior:
                return self._envelope(prior, replayed=True)
            confirmed = False
            if confirmation_card_id is not None:
                confirmed = self._confirmed_write(connection, scope, task_id, confirmation_card_id,
                                                  turn_id, tool_call_id, ability_key, encoded)
                if not confirmed:
                    raise BsideError('PROCESSING_CONFIRMATION_INVALID', 409)
            if (task['status'] in {'RESOLVED', 'FAILED', 'UNKNOWN'}
                    or (task['status'] == 'WAITING_INPUT' and not confirmed)):
                raise BsideError('PROCESSING_TASK_NOT_EXECUTABLE', 409)
            if connection.execute("SELECT 1 FROM processing_operations WHERE task_id=%s AND status='RUNNING'", (task_id,)).fetchone():
                raise BsideError('PROCESSING_OPERATION_IN_PROGRESS', 409)
            operation_id = uuid.uuid4().hex
            request_id = 'processing:' + operation_id
            connection.execute('INSERT INTO processing_operations(operation_id,task_id,operation_digest,ability_key,'
                'arguments,turn_id,tool_call_id,request_id,status) VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s,\'RUNNING\')',
                (operation_id, task_id, digest, ability_key, encoded, turn_id, tool_call_id, request_id))
        # Claim committed before invoking: a process crash cannot create a second dispatch.
        result = None
        error_code = None
        status = 'UNKNOWN'
        try:
            candidate = invoke(request_id)
            if (not isinstance(candidate, dict) or type(candidate.get('success')) is not bool
                    or candidate.get('requestId') != request_id or candidate.get('actionCode') != ability_key
                    or candidate.get('resolvedEnvironment') != environment):
                error_code = 'PROCESSING_RESULT_UNCONFIRMED'
            elif len(_json(candidate).encode()) > 1048576:
                error_code = 'PROCESSING_RESULT_TOO_LARGE'
            else:
                result = candidate
                raw_code = candidate.get('errorCode')
                # These execution errors are raised before business dispatch. Transport
                # or response decoding failures cannot establish absence of a side effect.
                rejected_before_dispatch = {'TRUSTED_CONTEXT_REQUIRED', 'CAPABILITY_CLIENT_NOT_SUPPORTED',
                    'RELEASE_ENVIRONMENT_INVALID', 'EXECUTION_PLAN_INVALID', 'ARGUMENT_INVALID',
                    'ARGUMENT_TYPE_MISMATCH', 'REQUEST_MAPPING_INVALID'}
                status = 'RETURNED' if candidate['success'] else (
                    'FAILED' if raw_code in rejected_before_dispatch else 'UNKNOWN')
                if isinstance(raw_code, str) and re.fullmatch(r'[A-Z][A-Z0-9_]{0,127}', raw_code):
                    error_code = raw_code
        except Exception:
            error_code = 'PROCESSING_DISPATCH_UNCONFIRMED'
        with self._factory() as connection:
            self._row(connection, scope, task_id, lock=True)
            row = connection.execute('UPDATE processing_operations SET status=%s,result=%s::jsonb,error_code=%s,'
                'finished_at=now() WHERE operation_id=%s RETURNING *',
                (status, _json(result) if result is not None else None, error_code, operation_id)).fetchone()
            task_status = {'RETURNED': 'RESULT_RECORDED', 'FAILED': 'FAILED', 'UNKNOWN': 'UNKNOWN'}[status]
            if status == 'RETURNED' and self._waiting_card(connection, scope, task_id):
                task_status = 'WAITING_INPUT'
            summary = ability_key + ('：已返回执行结果，待确认' if status == 'RETURNED' else '：执行失败' if status == 'FAILED' else '：执行结果未知')
            connection.execute('UPDATE processing_tasks SET status=%s,result_summary=%s,updated_at=now() WHERE task_id=%s',
                               (task_status, summary, task_id))
            return self._envelope(row, replayed=False)

    @staticmethod
    def _envelope(row: Mapping[str, Any], *, replayed: bool) -> OperationEnvelope:
        return {'status': row['status'], 'operationId': row['operation_id'], 'requestId': row['request_id'],
                'replayed': replayed, 'result': row['result'], 'errorCode': row['error_code']}

    @staticmethod
    def _delivery(connection: Any, task_id: str) -> str | None:
        row = connection.execute(
            "SELECT m.content->>'delivery' delivery FROM processing_turns t "
            "JOIN messages m ON m.id=t.assistant_message_id AND m.conversation_id=t.conversation_id "
            "WHERE t.task_id=%s ORDER BY t.input_message_id DESC LIMIT 1", (task_id,)).fetchone()
        return row['delivery'] if row else None

    def get(self, *, user_id: int, environment: str, task_id: str) -> dict[str, Any]:
        require_user_id(user_id)
        with self._factory() as connection:
            row = connection.execute('SELECT * FROM processing_tasks WHERE user_id=%s AND environment=%s AND task_id=%s',
                                     (user_id, environment, task_id)).fetchone()
            if row is None:
                raise BsideError('PROCESSING_TASK_NOT_FOUND', 404)
            delivery = self._delivery(connection, task_id)
            operations = connection.execute('SELECT * FROM processing_operations WHERE task_id=%s ORDER BY created_at,operation_id LIMIT 100',
                                            (task_id,)).fetchall()
        return {**_context(row), 'deliveryStatus': delivery, 'createdAt': _time(row['created_at']), 'updatedAt': _time(row['updated_at']),
                'resultSummary': row['result_summary'], 'resolutionSummary': row['resolution_summary'],
                'resolvedAt': _time(row['resolved_at']), 'resolutionSource': 'USER_CONFIRMATION' if row['resolved_at'] else None,
                'operations': [{'operationId': o['operation_id'], 'abilityKey': o['ability_key'], 'status': o['status'],
                    'requestId': o['request_id'], 'turnId': o['turn_id'], 'toolCallId': o['tool_call_id'],
                    'createdAt': _time(o['created_at']), 'finishedAt': _time(o['finished_at']),
                    'result': o['result'], 'errorCode': o['error_code']} for o in operations]}

    def resolve(self, *, user_id: int, environment: str, task_id: str, summary: str) -> dict[str, Any]:
        if not isinstance(summary, str) or not summary.strip() or len(summary) > 2000:
            raise BsideError('PROCESSING_RESOLUTION_REQUIRED', 400)
        with self._factory() as connection:
            row = connection.execute('SELECT * FROM processing_tasks WHERE user_id=%s AND environment=%s AND task_id=%s FOR UPDATE',
                                     (user_id, environment, task_id)).fetchone()
            if row is None:
                raise BsideError('PROCESSING_TASK_NOT_FOUND', 404)
            if row['status'] == 'RESOLVED':
                if row['resolution_summary'] != summary.strip():
                    raise BsideError('PROCESSING_RESOLUTION_CONFLICT', 409)
            elif (row['status'] != 'RESULT_RECORDED'
                  or self._delivery(connection, task_id) not in {'completed', 'waiting_action'}
                  or self._waiting_card(connection, (user_id, environment, row['conversation_id']), task_id)
                  or connection.execute(
                    "SELECT 1 FROM processing_operations WHERE task_id=%s AND status IN ('RUNNING','UNKNOWN','FAILED')", (task_id,)).fetchone()):
                raise BsideError('PROCESSING_RESULT_NOT_CONFIRMED', 409)
            else:
                connection.execute("UPDATE processing_tasks SET status='RESOLVED',resolution_summary=%s,resolved_at=now(),"
                                   'updated_at=now() WHERE task_id=%s', (summary.strip(), task_id))
        return self.get(user_id=user_id, environment=environment, task_id=task_id)

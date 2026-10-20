"""Owner-scoped read projection of committed workflow facts; never executes runs.

Runtime documents are authoritative. Notifications and browser presence do not
participate in classification. Only explicit reminder acknowledgements are owned
here. Each list reads a consistent database snapshot and returns bounded pages.
"""
from __future__ import annotations

import base64
import binascii
import datetime as dt
import hashlib
import json
from typing import Any, Callable, Mapping

from skillweave_contracts.user_id import require_user_id
from .errors import BsideError


_BASE = """
WITH facts AS (
 SELECT o.control_id, o.workflow_key, o.created_at,
        COALESCE(r.run_id, o.run_id) AS run_id,
        COALESCE(v.document->>'title', o.workflow_key) AS workflow_name,
        COALESCE(r.document->>'status',
          CASE WHEN c.document->>'status'='UNCONFIRMED' THEN 'UNCONFIRMED'
               ELSE 'SUBMITTED' END) AS run_status,
        COALESCE(v.revision,0)::text || ':' || COALESCE(r.document->>'revision','0') AS result_revision,
        CASE WHEN s.message_id IS NOT NULL THEN 'scheduled'
             ELSE COALESCE(o.source_type,'unknown') END AS source_type,
        s.payload->>'schedule_id' AS schedule_id, s.payload->>'scheduled_at' AS scheduled_at,
        COALESCE(v.document->'nodes','[]'::jsonb) AS nodes,
        left(v.document#>>'{outputs,-1,content}',1000) AS summary,
        COALESCE(w.items,'[]'::jsonb) AS waiting,
        COALESCE(b.items,'[]'::jsonb) AS business,
        EXISTS (SELECT 1 FROM work_activity_attention_acks a
                WHERE a.user_id=o.user_id AND a.environment=%(environment)s
                  AND a.activity_id=o.control_id
                  AND a.attention_id='failed:' || COALESCE(r.document->>'revision','0')) AS failure_ack
 FROM run_ownership o
 LEFT JOIN runtime_run_controls c ON c.user_id=o.user_id AND c.environment=%(environment)s AND c.control_id=o.control_id
 LEFT JOIN runtime_runs r ON r.user_id=o.user_id AND r.environment=%(environment)s
       AND r.run_id=COALESCE(c.document->>'run_id',o.run_id)
 LEFT JOIN runtime_mvp_views v ON v.user_id=r.user_id AND v.environment=r.environment AND v.run_id=r.run_id
 LEFT JOIN scheduler_outbox s ON s.message_id=o.control_id
       AND s.payload->>'kind'='start_workflow'
       AND s.payload->>'user_id'=%(user_id)s::text AND s.payload->>'environment'=%(environment)s
 LEFT JOIN LATERAL (
   SELECT jsonb_agg(jsonb_build_object('attentionId','waiting:' || i.interaction_id,
     'kind','waiting','title','等待填写或确认','summary',NULL,
     'nodeId',i.node_id,'interactionId',i.interaction_id,'acknowledged',false)
     ORDER BY i.node_id,i.interaction_id) AS items
   FROM runtime_interactions i
   WHERE i.user_id=r.user_id AND i.environment=r.environment AND i.run_id=r.run_id
     AND r.document->>'status'='RUNNING' AND i.document->>'phase'='WAITING'
     AND i.document->>'run_active'='true' AND i.document->>'node_waiting'='true'
     AND i.document->>'resume_started'='false'
 ) w ON true
 LEFT JOIN LATERAL (
   SELECT jsonb_agg(jsonb_build_object('attentionId',b.attention_id,'kind','business',
     'title',b.title,'summary',b.summary,'nodeId',b.node_id,'evidenceRefs',b.evidence_refs,
      'acknowledged',a.attention_id IS NOT NULL,
     'processingTasks',COALESCE((SELECT jsonb_agg(t.item ORDER BY t.created_at DESC) FROM (
       SELECT p.created_at,jsonb_build_object('taskId',p.task_id,'conversationId',p.conversation_id::text,
         'status',p.status,'objective',left(p.objective,300),'updatedAt',p.updated_at,
         'resolutionSummary',p.resolution_summary,
         'deliveryStatus',(SELECT m.content->>'delivery' FROM processing_turns pt
           JOIN messages m ON m.id=pt.assistant_message_id AND m.conversation_id=pt.conversation_id
           WHERE pt.task_id=p.task_id ORDER BY pt.input_message_id DESC LIMIT 1),
         'resultSummary',p.result_summary) AS item
       FROM processing_tasks p WHERE p.user_id=b.user_id AND p.environment=b.environment
         AND p.activity_id=o.control_id AND p.attention_id=b.attention_id
       ORDER BY p.created_at DESC LIMIT 10) t),'[]'::jsonb)) ORDER BY b.created_at,b.attention_id) AS items
   FROM runtime_workflow_attentions b
   LEFT JOIN work_activity_attention_acks a ON a.user_id=b.user_id AND a.environment=b.environment
     AND a.activity_id=o.control_id AND a.attention_id=b.attention_id
   WHERE b.user_id=r.user_id AND b.environment=r.environment AND b.run_id=r.run_id
 ) b ON true
 WHERE o.user_id=%(user_id)s
   AND (o.environment=%(environment)s OR c.control_id IS NOT NULL OR s.message_id IS NOT NULL)
), grouped AS (
 SELECT *, CASE WHEN jsonb_array_length(waiting)>0
      OR (run_status IN ('FAILED','UNCONFIRMED') AND NOT failure_ack)
      OR EXISTS (SELECT 1 FROM jsonb_array_elements(business) b WHERE b->>'acknowledged'='false')
      THEN 'attention' WHEN run_status IN ('RUNNING','SUBMITTED') THEN 'running'
      ELSE 'completed' END AS activity_group
 FROM facts
)
"""


def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, dt.datetime) else value


def _nodes(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    nodes = [dict(node) for node in row['nodes']]
    waiting = {item['nodeId'] for item in row['waiting']}
    for node in nodes:
        if row['run_status'] == 'STOPPED' and node.get('status') != 'SUCCEEDED':
            node['status'] = 'STOPPED'
        elif row['run_status'] == 'FAILED' and node.get('status') in ('RUNNING','WAITING'):
            node['status'] = 'UNCONFIRMED'
        elif row['run_status'] == 'RUNNING' and node.get('nodeId') in waiting and node.get('status') not in ('SUCCEEDED','STOPPED'):
            node['status'] = 'WAITING'
    return nodes


def _item(row: Mapping[str, Any]) -> dict[str, Any]:
    nodes = _nodes(row)
    current = next((n for n in nodes if n.get('status') in ('WAITING','RUNNING')), None)
    attention = list(row['waiting']) + list(row['business'])
    if row['run_status'] in ('FAILED', 'UNCONFIRMED'):
        attention.append({'attentionId': 'failed:' + row['result_revision'].split(':')[-1],
                          'kind': 'failed', 'title': '运行失败' if row['run_status']=='FAILED' else '运行结果未确认',
                          'summary': None, 'acknowledged': row['failure_ack']})
    if row['waiting']:
        waiting_node = next((n for n in nodes if n.get('nodeId') == row['waiting'][0]['nodeId']), None)
        if waiting_node:
            current = {**waiting_node, 'status': 'WAITING'}
    return {'activityId': row['control_id'], 'controlRequestId': row['control_id'],
            'runId': row['run_id'], 'workflowKey': row['workflow_key'],
            'workflowName': row['workflow_name'], 'sourceType': row['source_type'],
            'scheduleId': row['schedule_id'], 'scheduledAt': row['scheduled_at'],
            'scheduleName': ('定时计划 #' + row['schedule_id']) if row['schedule_id'] else None,
            'createdAt': _iso(row['created_at']), 'updatedAt': None,
            'startedAt': None, 'finishedAt': None,
            'runStatus': row['run_status'], 'currentNode': current,
            'summary': row['summary'], 'attentionItems': attention,
            'resultRevision': row['result_revision'], 'group': row['activity_group']}


class WorkActivitiesRepository:
    def __init__(self, connection_factory: Callable[[], Any]) -> None:
        self._factory = connection_factory

    @staticmethod
    def _scope(user_id: int, environment: str) -> dict[str, Any]:
        require_user_id(user_id)
        if environment not in ('PRT', 'ONLINE'):
            raise BsideError('INVALID_ENVIRONMENT', 400)
        return {'user_id': user_id, 'environment': environment}

    def list_runs(self, *, user_id: int, environment: str, group: str | None = None,
                  query: str = '', status: str = '', source_type: str = '',
                  created_after: str | None = None, created_before: str | None = None,
                  cursor: str | None = None, limit: int = 20) -> dict[str, Any]:
        params = self._scope(user_id, environment)
        if type(limit) is not int or not 1 <= limit <= 50 or group not in (None, 'attention','running','completed'):
            raise BsideError('INVALID_ACTIVITY_PAGE', 400)
        filters = []
        if query:
            filters.append('workflow_name ILIKE %(query)s')
            params['query'] = '%' + str(query)[:200] + '%'
        if status:
            filters.append('run_status=%(status)s')
            params['status'] = status
        if source_type:
            filters.append('source_type=%(source_type)s')
            params['source_type'] = source_type
        for name, value, op in (('after',created_after,'>='),('before',created_before,'<')):
            if value:
                try:
                    parsed = dt.datetime.fromisoformat(str(value).replace('Z','+00:00'))
                    if parsed.tzinfo is None:
                        raise ValueError()
                except ValueError:
                    raise BsideError('INVALID_ACTIVITY_TIME',400) from None
                filters.append('created_at ' + op + ' %(' + name + ')s')
                params[name] = parsed
        where = ' WHERE ' + ' AND '.join(filters) if filters else ''
        with self._factory() as connection:
            connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            count_rows = connection.execute(_BASE + 'SELECT activity_group,count(*) AS count FROM grouped' + where + ' GROUP BY activity_group',params).fetchall()
            counts = {key:0 for key in ('attention','running','completed')}
            counts.update({r['activity_group']:r['count'] for r in count_rows})
            if group:
                filters.append('activity_group=%(group)s')
                params['group'] = group
            if cursor:
                try:
                    if not isinstance(cursor,str) or len(cursor)>1024:
                        raise ValueError()
                    value = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
                    if not isinstance(value,list) or len(value)!=2 or not all(isinstance(x,str) for x in value):
                        raise ValueError()
                    params['cursor_time'] = dt.datetime.fromisoformat(value[0])
                    if params['cursor_time'].tzinfo is None or not 1<=len(value[1])<=256:
                        raise ValueError()
                    params['cursor_id'] = value[1]
                except (ValueError,TypeError,UnicodeError,binascii.Error):
                    raise BsideError('INVALID_ACTIVITY_CURSOR',400) from None
                filters.append('(created_at,control_id)<(%(cursor_time)s,%(cursor_id)s)')
            params['limit'] = limit + 1
            where = ' WHERE ' + ' AND '.join(filters) if filters else ''
            rows = connection.execute(_BASE + 'SELECT * FROM grouped' + where + ' ORDER BY created_at DESC,control_id DESC LIMIT %(limit)s',params).fetchall()
        page = rows[:limit]
        next_cursor = None
        if len(rows)>limit:
            next_cursor = base64.urlsafe_b64encode(json.dumps([_iso(page[-1]['created_at']),page[-1]['control_id']]).encode()).decode()
        return {'items':[_item(row) for row in page], 'counts':counts, 'nextCursor':next_cursor,
                'updatedAt':dt.datetime.now(dt.timezone.utc).isoformat()}

    def get(self, *, user_id: int, environment: str, activity_id: str) -> dict[str, Any]:
        params = self._scope(user_id,environment)
        params['activity_id'] = activity_id
        with self._factory() as connection:
            row = connection.execute(_BASE + 'SELECT * FROM grouped WHERE control_id=%(activity_id)s',params).fetchone()
        if row is None:
            raise BsideError('ACTIVITY_NOT_FOUND',404)
        return _item(row)

    def get_result(self, *, user_id: int, environment: str, activity_id: str,
                   node_id: str | None = None, offset: int = 0, limit: int = 12000) -> dict[str, Any]:
        if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=12000:
            raise BsideError('INVALID_RESULT_PAGE',400)
        params = self._scope(user_id,environment)
        params['activity_id'] = activity_id
        with self._factory() as connection:
            connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            row = connection.execute(_BASE + 'SELECT * FROM grouped WHERE control_id=%(activity_id)s',params).fetchone()
            if row is None:
                raise BsideError('ACTIVITY_NOT_FOUND',404)
            view = connection.execute('SELECT document FROM runtime_mvp_views WHERE user_id=%s AND environment=%s AND run_id=%s',
                                      (user_id,environment,row['run_id'])).fetchone() if row['run_id'] else None
            evidence = []
            for attention in row['business']:
                if node_id is not None and attention['nodeId'] != node_id:
                    continue
                for reference in attention['evidenceRefs']:
                    fact = connection.execute(
                        "SELECT message->'data' AS result FROM runtime_operation_facts f "
                        "CROSS JOIN LATERAL (SELECT (f.document->>'result_json')::jsonb AS saved) encoded "
                        "CROSS JOIN LATERAL jsonb_array_elements(CASE "
                        "WHEN saved->>'type'='Command' THEN COALESCE(saved#>'{update,messages}','[]'::jsonb) "
                        "WHEN saved->>'type'='tool' THEN jsonb_build_array(saved) ELSE '[]'::jsonb END) message "
                        "WHERE user_id=%s AND environment=%s AND run_id=%s "
                        "AND document->>'node_id'=%s AND document->>'kind'='TOOL' "
                        "AND document->>'status'='RETURNED' AND message->>'type'='tool' "
                        "AND message#>>'{data,name}'='execute_ability' "
                        "AND message#>>'{data,tool_call_id}'=%s LIMIT 1",
                        (user_id,environment,row['run_id'],attention['nodeId'],reference.removeprefix('tool:')),
                    ).fetchone()
                    saved = fact['result'] if fact else None
                    evidence.append({'attentionId':attention['attentionId'],'evidenceRef':reference,
                                     'nodeId':attention['nodeId'],
                                     'availability':'AVAILABLE' if saved else 'UNAVAILABLE',
                                     'toolResult':saved.get('content') if saved else None})
            processing = connection.execute(
                "SELECT p.task_id,p.attention_id,p.status,p.objective,p.resolution_summary,p.resolved_at,"
                "COALESCE((SELECT jsonb_agg(op.item ORDER BY op.created_at) FROM ("
                "SELECT x.created_at,jsonb_build_object('operationId',x.operation_id,'abilityKey',x.ability_key,"
                "'status',x.status,'requestId',x.request_id,'createdAt',x.created_at,'finishedAt',x.finished_at,"
                "'result',x.result,'errorCode',x.error_code) item FROM processing_operations x "
                "WHERE x.task_id=p.task_id ORDER BY x.created_at LIMIT 100) op),'[]'::jsonb) operations "
                "FROM processing_tasks p WHERE p.user_id=%s AND p.environment=%s AND p.activity_id=%s "
                "ORDER BY p.created_at DESC LIMIT 10", (user_id,environment,activity_id)).fetchall()
        result = _item(row)
        document = view['document'] if view else {}
        outputs = document.get('outputs',[])
        if node_id is not None:
            if not any(n.get('nodeId')==node_id for n in document.get('nodes',[])):
                raise BsideError('RESULT_NODE_NOT_FOUND',404)
            outputs = [o for o in outputs if o.get('nodeId')==node_id]
        processing_results = [{'taskId': p['task_id'], 'attentionId': p['attention_id'], 'status': p['status'],
                               'objective': p['objective'], 'resolutionSummary': p['resolution_summary'],
                               'resolvedAt': _iso(p['resolved_at']), 'operations': p['operations']} for p in processing]
        saved_result = {'outputs': outputs, 'attentionEvidence': evidence, 'processingTasks': processing_results}
        serialized = json.dumps(saved_result,ensure_ascii=False,separators=(',',':'))
        # Revision includes the exact saved outputs, not merely a display version.
        result['resultRevision'] += ':' + hashlib.sha256(json.dumps({'result':saved_result,'business':row['business']},
            ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:16]
        observed_at = dt.datetime.now(dt.timezone.utc).isoformat()
        result.update(observedAt=observed_at, readAt=observed_at,
                      availability='AVAILABLE' if view else 'NOT_YET_AVAILABLE',
                      nodes=[{'nodeId':n.get('nodeId'),'title':n.get('title'),'status':n.get('status')}
                             for n in _nodes(row)],
                      resultPage=serialized[offset:offset+limit], resultOffset=offset,
                      nextOffset=offset+limit if offset+limit<len(serialized) else None,
                      truncated=offset>0 or offset+limit<len(serialized),
                      resultFormat='saved-workflow-result-json',
                      attentionEvidence=[{k:v for k,v in e.items() if k!='toolResult'} for e in evidence],
                      outputIndex=[{'nodeId':o.get('nodeId'),'kind':o.get('kind')} for o in outputs])
        return result

    def acknowledge(self, *, user_id: int, environment: str, activity_id: str,
                    attention_id: str) -> dict[str, Any]:
        item = self.get(user_id=user_id,environment=environment,activity_id=activity_id)
        reminder = next((a for a in item['attentionItems'] if a['attentionId']==attention_id),None)
        if reminder is None:
            raise BsideError('ATTENTION_NOT_FOUND',404)
        if reminder['kind']=='waiting':
            raise BsideError('INTERACTION_REQUIRES_SUBMISSION',409)
        with self._factory() as connection:
            connection.execute('INSERT INTO work_activity_attention_acks(user_id,environment,activity_id,attention_id) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                               (user_id,environment,activity_id,attention_id))
        return {'acknowledged':True,'attentionId':attention_id}

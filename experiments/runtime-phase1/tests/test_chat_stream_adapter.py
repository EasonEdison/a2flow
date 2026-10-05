import asyncio
import threading
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from deploy.attended.chat_runner import ChatLoopRunner


class Store:
    @contextmanager
    def session(self, *args):
        yield object(), 'thread'


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_events_before_worker_returns_and_session_finishes(self):
        gate = threading.Event()
        class Loop:
            def __init__(self, **kwargs):
                self.emitter = kwargs['emitter']
            def turn(self, text):
                self.emitter.emit('text_delta', {
                    'text': 'first', 'modelMessageId': 'model-final',
                })
                if not gate.wait(3):
                    raise RuntimeError('test timed out')
                self.emitter.emit('reasoning_delta', {
                    'text': 'provider reasoning', 'modelMessageId': 'model-final',
                })
                self.emitter.emit('tool_call_started', {
                    'toolCallId': 'call-1', 'name': 'use_skill',
                    'arguments': {'skillKey': 'demo'},
                    'startedAt': '2026-10-05T12:00:00+00:00',
                })
                self.emitter.emit('tool_call', {'tool': 'use_skill', 'secret': 'not forwarded'})
                self.emitter.emit('tool_call_finished', {
                    'toolCallId': 'call-1', 'name': 'use_skill',
                    'lifecycleStatus': 'returned', 'toolMessageStatus': 'success',
                    'startedAt': '2026-10-05T12:00:00+00:00',
                    'finishedAt': '2026-10-05T12:00:00.010000+00:00',
                    'durationMs': 10, 'result': {'keys': ['content']},
                })
                self.emitter.emit('done', {
                    'content': 'first', 'finalModelMessageId': 'model-final',
                })
        runner = ChatLoopRunner(model_factory=None, model_reference='test', environment='PRT',
                                reader=None, conversation_store=Store(), history_loader=None)
        with patch('agent_workflow_runtime.chat.loop.ChatLoop', Loop):
            stream = runner.iterate(user_id=1, conversation_id=1, text='x', turn_id='1')
            try:
                first = await asyncio.wait_for(anext(stream), 2)
                self.assertEqual({
                    'type': 'text_delta', 'text': 'first',
                    'modelMessageId': 'model-final',
                }, first)
            finally:
                gate.set()
            rest = [event async for event in stream]
            self.assertEqual([
                'reasoning_delta', 'tool_call_started', 'tool_call',
                'tool_call_finished', 'done',
            ], [event['type'] for event in rest])
            self.assertEqual('model-final', rest[-1]['finalModelMessageId'])
            self.assertNotIn('secret', str(rest))

    async def test_session_commit_failure_suppresses_model_done(self):
        class Broken(Store):
            @contextmanager
            def session(self, *args):
                yield object(), 'thread'
                raise RuntimeError('private db failure')
        class Loop:
            def __init__(self, **kwargs):
                self.emitter = kwargs['emitter']
            def turn(self, text):
                self.emitter.emit('done', {})
        runner = ChatLoopRunner(model_factory=None, model_reference='test', environment='PRT',
                                reader=None, conversation_store=Broken(), history_loader=None)
        with patch('agent_workflow_runtime.chat.loop.ChatLoop', Loop):
            events = [event async for event in runner.iterate(user_id=1, conversation_id=1, text='x', turn_id='1')]
        self.assertEqual([{'type': 'error', 'code': 'CHAT_UNAVAILABLE'}], events)

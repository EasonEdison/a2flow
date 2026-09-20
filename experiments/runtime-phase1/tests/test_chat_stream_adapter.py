import asyncio
from contextlib import contextmanager
import threading
import unittest
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
                self.emitter.emit('text_delta', {'text': 'first'})
                if not gate.wait(3):
                    raise RuntimeError('test timed out')
                self.emitter.emit('reasoning_delta', {'text': 'provider reasoning'})
                self.emitter.emit('tool_call', {'tool': 'use_skill', 'secret': 'not forwarded'})
                self.emitter.emit('done', {})
        runner = ChatLoopRunner(model_factory=None, model_reference='test', environment='PRT',
                                reader=None, conversation_store=Store(), history_loader=None)
        with patch('agent_workflow_runtime.chat.loop.ChatLoop', Loop):
            stream = runner.iterate(user_id=1, conversation_id=1, text='x', turn_id='1')
            try:
                first = await asyncio.wait_for(anext(stream), 2)
                self.assertEqual({'type': 'text_delta', 'text': 'first'}, first)
            finally:
                gate.set()
            rest = [event async for event in stream]
            self.assertEqual(['reasoning_delta', 'tool_call', 'done'], [event['type'] for event in rest])
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

import asyncio
import copy
import json
import unittest

from a2flow_bside.chat_delivery import ChatDelivery, ChatStreamingResponse


class Messages:
    def __init__(self):
        self.saved = []

    def update_delivery(self, **kwargs):
        self.saved.append(copy.deepcopy(kwargs))


def delivery(runner, messages=None):
    return ChatDelivery(messages=messages or Messages(), runner=runner,
                        user_id=123, conversation_id=1, text='hello',
                        input_message={'id': 11}, assistant_message={'id': 12})


class DeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_disconnect_before_response_body_starts(self):
        class Runner:
            async def iterate(self, **kwargs):
                for _ in range(200):
                    yield {'type': 'text_delta', 'text': 'x'}
                yield {'type': 'done'}
        turn = delivery(Runner())
        task = asyncio.create_task(turn.produce())
        async def broken_send(event):
            raise OSError('connection gone before headers')
        async def receive():
            return {'type': 'http.disconnect'}
        with self.assertRaises(Exception):
            await ChatStreamingResponse(turn)({'type': 'http', 'asgi': {'spec_version': '2.4'}}, receive, broken_send)
        await asyncio.wait_for(task, 2)
        self.assertTrue(turn.detached)
        self.assertEqual('completed', turn.messages.saved[-1]['content']['delivery'])

    async def test_disconnect_keeps_single_worker_and_final_save(self):
        proceed = asyncio.Event()
        class Runner:
            calls = 0
            async def iterate(self, **kwargs):
                self.calls += 1
                yield {'type': 'text_delta', 'text': 'first'}
                await proceed.wait()
                yield {'type': 'text_delta', 'text': ' last'}
                yield {'type': 'done'}
        runner = Runner()
        turn = delivery(runner)
        task = asyncio.create_task(turn.produce())
        stream = turn.stream()
        self.assertIn('turn_started', await anext(stream))
        self.assertIn('first', await anext(stream))
        self.assertFalse(task.done())
        await stream.aclose()
        proceed.set()
        await asyncio.wait_for(task, 2)
        self.assertEqual(1, runner.calls)
        self.assertEqual('first last', turn.messages.saved[-1]['content']['text'])
        self.assertEqual('completed', turn.messages.saved[-1]['content']['delivery'])

    async def test_failure_and_missing_terminal_are_not_success(self):
        for raise_error in (False, True):
            class Runner:
                async def iterate(self, **kwargs):
                    yield {'type': 'text_delta', 'text': 'partial'}
                    if raise_error:
                        raise RuntimeError('private error')
            turn = delivery(Runner())
            task = asyncio.create_task(turn.produce())
            events = [json.loads(item[6:]) async for item in turn.stream()]
            await task
            self.assertNotIn('done', [item['type'] for item in events])
            self.assertIn(turn.messages.saved[-1]['content']['delivery'], ('failed', 'unconfirmed'))
            self.assertNotIn('private error', str(events))

    async def test_commit_failure_never_sends_done(self):
        class Broken(Messages):
            def update_delivery(self, **kwargs):
                raise RuntimeError('db unavailable')
        class Runner:
            async def iterate(self, **kwargs):
                yield {'type': 'done'}
        turn = delivery(Runner(), Broken())
        task = asyncio.create_task(turn.produce())
        events = [json.loads(item[6:]) async for item in turn.stream()]
        await task
        self.assertEqual(['turn_started', 'error'], [event['type'] for event in events])

    async def test_full_subscriber_queue_disconnect_unblocks_producer(self):
        reached = asyncio.Event()
        class Runner:
            async def iterate(self, **kwargs):
                for index in range(200):
                    if index == 63:
                        reached.set()
                    yield {'type': 'text_delta', 'text': 'x'}
                yield {'type': 'done'}
        turn = delivery(Runner())
        task = asyncio.create_task(turn.produce())
        stream = turn.stream()
        await anext(stream)
        await reached.wait()
        await stream.aclose()
        await asyncio.wait_for(task, 2)
        self.assertEqual('x' * 200, turn.messages.saved[-1]['content']['text'])
        self.assertLessEqual(turn.pending.qsize(), 64)

    async def test_done_waits_for_native_iterator_exit_and_saved_projection(self):
        gate = asyncio.Event()
        class Runner:
            async def iterate(self, **kwargs):
                yield {'type': 'done'}
                await gate.wait()
        turn = delivery(Runner())
        task = asyncio.create_task(turn.produce())
        stream = turn.stream()
        await anext(stream)
        self.assertEqual([], turn.messages.saved)
        gate.set()
        event = json.loads((await anext(stream))[6:])
        self.assertEqual('done', event['type'])
        self.assertEqual('completed', turn.messages.saved[-1]['content']['delivery'])
        await task
        await stream.aclose()

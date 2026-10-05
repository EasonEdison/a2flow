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
    async def test_card_wait_is_not_reported_as_business_completion(self):
        class Runner:
            async def iterate(self, **kwargs):
                yield {'type': 'application_rendered', 'card': {'cardId': 'card-1'}}
                yield {'type': 'waiting_action', 'cardId': 'card-1'}
                yield {'type': 'done'}
        turn = delivery(Runner())
        task = asyncio.create_task(turn.produce())
        events = [json.loads(item[6:]) async for item in turn.stream()]
        await task
        self.assertEqual('waiting_action', turn.messages.saved[-1]['content']['delivery'])
        self.assertEqual('done', events[-1]['type'])
        self.assertEqual('waiting_action', events[-1]['content']['delivery'])
        waiting = next(event for event in events if event['type'] == 'waiting_action')
        self.assertEqual('application:card-1', waiting['partId'])

    async def test_persists_text_and_cards_in_actual_event_order(self):
        class Runner:
            async def iterate(self, **kwargs):
                yield {'type': 'text_delta', 'text': '文字A',
                       'modelMessageId': 'model-one'}
                yield {'type': 'application_rendered',
                       'card': {'cardId': 'card-1', 'status': 'WAITING_ACTION'}}
                yield {'type': 'text_delta', 'text': '文字B',
                       'modelMessageId': 'model-one'}
                yield {'type': 'application_rendered',
                       'card': {'cardId': 'card-2', 'status': 'DISPLAY_ONLY'}}
                yield {'type': 'text_delta', 'text': '文字C',
                       'modelMessageId': 'model-one'}
                yield {'type': 'done', 'content': '文字A文字B文字C',
                       'finalModelMessageId': 'model-one'}

        turn = delivery(Runner())
        task = asyncio.create_task(turn.produce())
        events = [json.loads(item[6:]) async for item in turn.stream()]
        await task

        persisted = turn.messages.saved[-1]['content']
        self.assertEqual([
            {'type': 'text', 'id': 'text:12:1', 'text': '文字A',
             'modelMessageId': 'model-one'},
            {'type': 'application', 'id': 'application:card-1',
             'cardId': 'card-1'},
            {'type': 'text', 'id': 'text:12:2', 'text': '文字B',
             'modelMessageId': 'model-one'},
            {'type': 'application', 'id': 'application:card-2',
             'cardId': 'card-2'},
            {'type': 'text', 'id': 'text:12:3', 'text': '文字C',
             'modelMessageId': 'model-one'},
        ], persisted['parts'])
        self.assertNotIn('card', persisted['parts'][1])
        self.assertNotIn('card', persisted['events'][0])

        text_events = [event for event in events if event['type'] == 'text_delta']
        self.assertEqual(
            ['text:12:1', 'text:12:2', 'text:12:3'],
            [event['partId'] for event in text_events],
        )
        application_events = [
            event for event in events if event['type'] == 'application_rendered'
        ]
        self.assertEqual(
            ['application:card-1', 'application:card-2'],
            [event['partId'] for event in application_events],
        )
        done = events[-1]
        self.assertEqual(5, len(done['content']['parts']))
        self.assertEqual('card-1', done['content']['parts'][1]['card']['cardId'])
        self.assertEqual('card-2', done['content']['parts'][3]['card']['cardId'])

    async def test_done_only_final_text_is_added_once_after_card(self):
        class Runner:
            async def iterate(self, **kwargs):
                yield {'type': 'application_rendered',
                       'card': {'cardId': 'card-1', 'status': 'DISPLAY_ONLY'}}
                yield {'type': 'done', 'content': '最终文字',
                       'finalModelMessageId': 'model-final'}

        turn = delivery(Runner())
        task = asyncio.create_task(turn.produce())
        events = [json.loads(item[6:]) async for item in turn.stream()]
        await task

        self.assertEqual([
            ('application', 'application:card-1'),
            ('text', 'text:12:1'),
        ], [
            (part['type'], part['id'])
            for part in turn.messages.saved[-1]['content']['parts']
        ])
        self.assertEqual(
            '最终文字', turn.messages.saved[-1]['content']['parts'][1]['text'],
        )
        self.assertEqual(2, len(events[-1]['content']['parts']))

    async def test_done_without_model_id_does_not_duplicate_streamed_text(self):
        class Runner:
            async def iterate(self, **kwargs):
                yield {'type': 'text_delta', 'text': '最终文字'}
                yield {'type': 'application_rendered',
                       'card': {'cardId': 'card-1', 'status': 'DISPLAY_ONLY'}}
                yield {'type': 'done', 'content': '最终文字'}

        turn = delivery(Runner())
        task = asyncio.create_task(turn.produce())
        events = [json.loads(item[6:]) async for item in turn.stream()]
        await task

        parts = events[-1]['content']['parts']
        self.assertEqual(['text', 'application'], [part['type'] for part in parts])
        self.assertEqual('最终文字', parts[0]['text'])

    async def test_disconnect_before_response_body_starts(self):
        class Runner:
            async def iterate(self, **kwargs):
                for _ in range(200):
                    yield {'type': 'text_delta', 'text': 'x',
                           'modelMessageId': 'model-final'}
                yield {'type': 'done', 'content': 'x' * 200,
                       'finalModelMessageId': 'model-final'}
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
                yield {'type': 'text_delta', 'text': 'first',
                       'modelMessageId': 'model-final'}
                await proceed.wait()
                yield {'type': 'text_delta', 'text': ' last',
                       'modelMessageId': 'model-final'}
                yield {'type': 'done', 'content': 'first last',
                       'finalModelMessageId': 'model-final'}
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
                    yield {'type': 'text_delta', 'text': 'x',
                           'modelMessageId': 'model-final'}
                yield {'type': 'done', 'content': 'x' * 200,
                       'finalModelMessageId': 'model-final'}
        turn = delivery(Runner())
        task = asyncio.create_task(turn.produce())
        stream = turn.stream()
        await anext(stream)
        await reached.wait()
        await stream.aclose()
        await asyncio.wait_for(task, 2)
        self.assertEqual('x' * 200, turn.messages.saved[-1]['content']['text'])
        self.assertLessEqual(turn.pending.qsize(), 64)

    async def test_persists_ordered_model_tool_and_card_execution(self):
        full_result = {
            'businessSuccess': False,
            'items': [
                {'index': index, 'text': 'visible-' * 100}
                for index in range(30)
            ],
            'nested': {'one': {'two': {'three': {'four': 'kept'}}}},
        }

        class Runner:
            async def iterate(self, **kwargs):
                yield {'type': 'reasoning_delta', 'text': '先查数据',
                       'modelMessageId': 'model-process'}
                yield {'type': 'text_delta', 'text': '正在处理',
                       'modelMessageId': 'model-process'}
                yield {
                    'type': 'tool_call_started', 'toolCallId': 'call-1',
                    'name': 'execute_ability', 'arguments': {'query': 'public'},
                    'startedAt': '2026-10-05T12:00:00+00:00',
                }
                yield {
                    'type': 'tool_call_finished', 'toolCallId': 'call-1',
                    'name': 'execute_ability', 'lifecycleStatus': 'returned',
                    'toolMessageStatus': 'success',
                    'startedAt': '2026-10-05T12:00:00+00:00',
                    'finishedAt': '2026-10-05T12:00:00.025000+00:00',
                    'durationMs': 25, 'result': full_result,
                    'businessSuccess': False,
                }
                yield {'type': 'text_delta', 'text': '最终回答',
                       'modelMessageId': 'model-final'}
                yield {'type': 'application_rendered',
                       'card': {'cardId': 'card-1', 'turnId': '11'}}
                yield {'type': 'done', 'content': '最终回答',
                       'finalModelMessageId': 'model-final'}

        turn = delivery(Runner())
        task = asyncio.create_task(turn.produce())
        events = [json.loads(item[6:]) async for item in turn.stream()]
        await task

        saved = turn.messages.saved[-1]['content']
        self.assertEqual('最终回答', saved['text'])
        self.assertEqual('', saved['reasoning'])
        self.assertEqual('11', saved['execution']['turnId'])
        self.assertEqual(
            [('model-process', 2, 'process'), ('model-final', 6, 'final')],
            [(item['messageId'], item['sequence'], item['phase'])
             for item in saved['execution']['modelMessages']],
        )
        tool = saved['execution']['toolCalls'][0]
        self.assertEqual(('call-1', 4, 'returned', False), (
            tool['toolCallId'], tool['sequence'], tool['lifecycleStatus'],
            tool['businessSuccess'],
        ))
        self.assertEqual(full_result, tool['result'])
        self.assertEqual('11', saved['events'][0]['turnId'])
        self.assertEqual('12', saved['events'][0]['assistantMessageId'])
        self.assertEqual('11', events[0]['turnId'])
        self.assertEqual('model-final', events[-1]['finalModelMessageId'])
        terminal = copy.deepcopy(events[-1]['content'])
        for part in terminal['parts']:
            part.pop('card', None)
        self.assertEqual(saved, terminal)

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

"""Run only against an explicitly selected disposable PostgreSQL database."""
import os
from pathlib import Path
import unittest
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from a2flow_bside.repositories import MessagesRepository


@unittest.skipUnless(os.environ.get('A2FLOW_TEST_CHAT_DSN'), 'disposable PG required')
class DeliveryPostgresTests(unittest.TestCase):
    def setUp(self):
        self.dsn = os.environ['A2FLOW_TEST_CHAT_DSN']
        with psycopg.connect(self.dsn) as connection:
            connection.execute(Path('services/b-side-api/src/a2flow_bside/schema.sql').read_text())
            self.conversation = connection.execute(
                'INSERT INTO conversations (user_id,title) VALUES (%s,%s) RETURNING id',
                (9223372036854775807, str(uuid4()))).fetchone()[0]
        self.repo = MessagesRepository(lambda: psycopg.connect(self.dsn, row_factory=dict_row))

    def test_latest_window_and_owner_scoped_update_survive_reconstruction(self):
        with psycopg.connect(self.dsn) as connection:
            connection.execute("INSERT INTO messages (conversation_id,role,content) "
                "SELECT %s,'user','{\"text\":\"old\"}'::jsonb FROM generate_series(1,205)",
                (self.conversation,))
        row = self.repo.append(conversation_id=self.conversation, role='assistant',
                               content={'text': '', 'delivery': 'running'})
        self.repo.update_delivery(conversation_id=self.conversation, message_id=row['id'],
                                  content={'text': 'complete', 'delivery': 'completed'})
        rebuilt = MessagesRepository(lambda: psycopg.connect(self.dsn, row_factory=dict_row))
        history = rebuilt.list_for(self.conversation)
        self.assertEqual(200, len(history))
        self.assertEqual(row['id'], history[-1]['id'])
        self.assertEqual('completed', history[-1]['content']['delivery'])
        self.assertEqual(sorted(item['id'] for item in history), [item['id'] for item in history])
        with self.assertRaisesRegex(ValueError, 'CHAT_MESSAGE_MISSING'):
            rebuilt.update_delivery(conversation_id=self.conversation + 999, message_id=row['id'], content={})

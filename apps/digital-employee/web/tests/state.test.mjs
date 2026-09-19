import test from 'node:test';
import assert from 'node:assert/strict';

import {
  appendMessage,
  markNotificationRead,
  removeSchedule,
  toggleSchedule,
  unreadCount,
  upsertConversation,
} from '../src/state.mjs';

test('会话置顶更新且不丢失其他会话', () => {
  const current = [
    { id: 'c1', title: '旧会话', updatedAt: '2026-01-01T00:00:00Z' },
    { id: 'c2', title: '另一个会话', updatedAt: '2026-01-02T00:00:00Z' },
  ];
  const next = upsertConversation(current, {
    id: 'c1',
    title: '已更新',
    updatedAt: '2026-01-03T00:00:00Z',
  });
  assert.deepEqual(next.map((item) => item.id), ['c1', 'c2']);
  assert.equal(next[0].title, '已更新');
});

test('消息追加保持原数组不可变', () => {
  const current = [{ id: 'm1', role: 'user', text: '你好' }];
  const next = appendMessage(current, { id: 'm2', role: 'assistant', text: '你好' });
  assert.equal(current.length, 1);
  assert.deepEqual(next.map((item) => item.id), ['m1', 'm2']);
});

test('通知已读更新与未读计数正确', () => {
  const current = [
    { id: 'n1', read: false },
    { id: 'n2', read: false },
    { id: 'n3', read: true },
  ];
  const next = markNotificationRead(current, 'n1');
  assert.equal(unreadCount(next), 1);
  assert.equal(current[0].read, false);
});

test('调度启停和删除保持不可变', () => {
  const current = [
    { id: 's1', enabled: true },
    { id: 's2', enabled: false },
  ];
  const toggled = toggleSchedule(current, 's1', false);
  const removed = removeSchedule(toggled, 's2');
  assert.equal(toggled[0].enabled, false);
  assert.deepEqual(removed.map((item) => item.id), ['s1']);
  assert.equal(current[0].enabled, true);
});

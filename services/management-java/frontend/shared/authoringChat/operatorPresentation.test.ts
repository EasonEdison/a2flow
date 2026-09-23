import {
  authoringSessionActorLabel,
  authoringTurnActorLabel,
  reconcilePersistedTurnAttribution,
} from './operatorPresentation';

function assertEqual(actual: unknown, expected: unknown, description: string) {
  if (actual !== expected) {
    throw new Error(`${description}: expected ${String(expected)}, received ${String(actual)}`);
  }
}

function test(description: string, callback: () => void) {
  callback();
  console.log(`PASS ${description}`);
}

test('persisted shared turn displays its stored operator', () => {
  assertEqual(
    authoringTurnActorLabel({ role: 'user', operator: 'other_operator' }),
    'other_operator',
    'persisted operator attribution',
  );
});

test('only optimistic user turn without operator displays viewer-relative label', () => {
  assertEqual(
    authoringTurnActorLabel({ role: 'user', optimistic: true }),
    '我',
    'optimistic current user attribution',
  );
});

test('metadata refresh reconciles optimistic turn to persisted operator without replacing other turns', () => {
  const optimisticTurn = {
    id: 'user-msg-1',
    role: 'user' as const,
    operator: undefined,
    optimistic: true,
  };
  const activeAssistantTurn = {
    id: 'assistant-live',
    role: 'assistant' as const,
    operator: undefined,
    optimistic: true,
  };
  const reconciled = reconcilePersistedTurnAttribution(
    [optimisticTurn, activeAssistantTurn],
    [{ id: 'user-msg-1', operator: 'other_operator' }],
  );

  assertEqual(
    reconciled?.[0]?.operator,
    'other_operator',
    'persisted operator copied to live turn',
  );
  assertEqual(reconciled?.[0]?.optimistic, false, 'persisted turn leaves optimistic state');
  assertEqual(authoringTurnActorLabel(reconciled?.[0]), 'other_operator', 'reconciled actor label');
  assertEqual(reconciled?.[1], activeAssistantTurn, 'unmatched live turn keeps object identity');
});

test('legacy persisted turn without operator does not impersonate current viewer', () => {
  assertEqual(
    authoringTurnActorLabel({ role: 'user' }),
    '未知用户',
    'legacy missing operator attribution',
  );
});

test('session option prefers recent operator and falls back to creator', () => {
  assertEqual(
    authoringSessionActorLabel({ lastOperator: 'recent_operator', creator: 'session_creator' }),
    'recent_operator',
    'recent session operator',
  );
  assertEqual(
    authoringSessionActorLabel({ creator: 'session_creator' }),
    'session_creator',
    'session creator fallback',
  );
});

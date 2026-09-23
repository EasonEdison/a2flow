export interface AuthoringTurnAttribution {
  role: 'user' | 'assistant';
  operator?: string;
  optimistic?: boolean;
}

export interface AuthoringSessionAttribution {
  creator?: string;
  lastOperator?: string;
}

export interface ReconciledAuthoringTurn {
  id: string;
  operator?: string;
  optimistic?: boolean;
}

function normalizedOperator(operator?: string): string {
  return (operator || '').trim();
}

/**
 * 共享历史使用持久化 operator 署名；只有未落库的本轮消息可以使用“我”。
 */
export function authoringTurnActorLabel(turn: AuthoringTurnAttribution): string {
  if (turn.role === 'assistant') return 'AI';
  const operator = normalizedOperator(turn.operator);
  if (operator) return operator;
  return turn.optimistic ? '我' : '未知用户';
}

/**
 * 头像只展示一个有界字符，完整操作者名称由消息元信息展示。
 */
export function authoringTurnAvatarLabel(turn: AuthoringTurnAttribution): string {
  const actor = authoringTurnActorLabel(turn);
  if (actor === 'AI' || actor === '我') return actor;
  if (actor === '未知用户') return '用';
  return (Array.from(actor)?.[0] || '用').toUpperCase();
}

/**
 * 会话列表优先展示最近操作者，旧会话缺失时回退创建人。
 */
export function authoringSessionActorLabel(session: AuthoringSessionAttribution): string {
  return normalizedOperator(session.lastOperator) || normalizedOperator(session.creator);
}

/**
 * 元数据刷新只对齐已持久化 Turn 的署名状态，不替换仍在流式更新的消息或事件对象。
 */
export function reconcilePersistedTurnAttribution<T extends ReconciledAuthoringTurn>(
  turns: T[],
  persistedTurns: ReconciledAuthoringTurn[],
): T[] {
  const persistedById = new Map(persistedTurns.map((turn) => [turn.id, turn]));
  return turns.map((turn) => {
    const persisted = persistedById.get(turn.id);
    if (!persisted) return turn;
    if (turn.operator === persisted.operator && turn.optimistic === false) return turn;
    return {
      ...turn,
      operator: persisted.operator,
      optimistic: false,
    };
  });
}

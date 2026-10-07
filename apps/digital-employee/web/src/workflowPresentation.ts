import type { NodeView } from './presentation';
import type { ChatJson, ChatModelMessage, ChatToolCall, Message } from './productApi';

function detail(node: NodeView, operationId: string, kind: string): ChatJson | undefined {
  const records = node.records.filter(record => record.eventKind === 'TOOL_DETAIL'
    && record.operationId === operationId && record.payload?.detailKind === kind);
  if (!records.length) return undefined;
  const count = Number(records[0].payload?.chunkCount);
  if (!Number.isSafeInteger(count) || count < 1 || records.length !== count) return undefined;
  const chunks = new Map(records.map(record => [Number(record.payload?.chunkIndex), record.payload?.text]));
  if (chunks.size !== count) return undefined;
  let text = '';
  for (let index = 0; index < count; index++) {
    const chunk = chunks.get(index);
    if (typeof chunk !== 'string') return undefined;
    text += chunk;
  }
  try { return JSON.parse(text) as ChatJson; } catch { return undefined; }
}

/** Project persisted observations only; never infer business success from prose. */
export function workflowMessage(node: NodeView): Message {
  const models = new Map<string, ChatModelMessage>();
  const tools = new Map<string, ChatToolCall>();
  node.records.forEach((record, sequence) => {
    if (record.kind === 'text' || record.kind === 'reasoning') {
      const id = record.modelCallId ?? record.id;
      const message = models.get(id) ?? { sequence, messageId: id, text: '', reasoning: '', phase: 'process' as const };
      if (record.kind === 'reasoning') message.reasoning += record.text;
      else message.text += record.text;
      models.set(id, message);
    }
    if (!record.eventKind?.startsWith('TOOL_') || !record.operationId || record.eventKind === 'TOOL_DETAIL') return;
    const id = record.operationId;
    const tool = tools.get(id) ?? {
      sequence, toolCallId: id, name: record.toolName ?? '工具调用', arguments: {},
      lifecycleStatus: 'running' as const, startedAt: record.observedAt ?? '',
    };
    if (record.eventKind === 'TOOL_RETURNED') tool.lifecycleStatus = 'returned';
    if (['TOOL_UNCONFIRMED', 'TOOL_INTERRUPTED'].includes(record.eventKind)) {
      tool.lifecycleStatus = 'returned';
      tool.observationStatus = record.eventKind === 'TOOL_INTERRUPTED' ? 'waiting' : 'unconfirmed';
    }
    if (record.eventKind !== 'TOOL_STARTED' && !record.eventKind.endsWith('_DELTA')) {
      tool.finishedAt = record.observedAt;
      const duration = Date.parse(tool.finishedAt ?? '') - Date.parse(tool.startedAt);
      if (Number.isFinite(duration) && duration >= 0) tool.durationMs = duration;
    }
    tools.set(id, tool);
  });
  for (const [id, tool] of tools) {
    if (tool.lifecycleStatus === 'running' && !['RUNNING', 'WAITING'].includes(node.status)) {
      tool.observationStatus = 'unconfirmed';
    }
    const args = detail(node, id, 'arguments');
    tool.argumentsUnavailable = !args || typeof args !== 'object' || Array.isArray(args);
    if (!tool.argumentsUnavailable) tool.arguments = args as Record<string, ChatJson>;
    const result = detail(node, id, 'result');
    tool.resultUnavailable = tool.lifecycleStatus === 'returned' && result === undefined;
    if (result && typeof result === 'object' && !Array.isArray(result)) {
      tool.result = result.result;
      if (result.toolMessageStatus === 'error' || result.toolMessageStatus === 'success') tool.toolMessageStatus = result.toolMessageStatus;
    }
  }
  return {
    id: node.id, role: 'assistant', text: '', createdAt: '',
    delivery: node.status === 'RUNNING' ? 'running' : 'completed',
    execution: { schemaVersion: 'v1', turnId: node.id, inputMessageId: '', assistantMessageId: node.id,
      modelMessages: [...models.values()].filter(message => message.text.trim() !== node.output?.trim() || message.reasoning), toolCalls: [...tools.values()] },
  };
}

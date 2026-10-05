import type { ThreadMessageLike } from '@assistant-ui/react';

import type {
  ChatExecution,
  ChatContentPart,
  ChatCard,
  ChatModelMessage,
  ChatStreamEvent,
  ChatToolCall,
  Message,
} from './productApi';

type AssistantContentPart = Exclude<ThreadMessageLike['content'], string>[number];

const messageDate = (value: string): Date | undefined => {
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? new Date(timestamp) : undefined;
};

const assistantStatus = (message: Message): ThreadMessageLike['status'] => {
  if (message.delivery === 'running') return { type: 'running' };
  if (message.delivery === 'failed' || message.delivery === 'unconfirmed') {
    return { type: 'incomplete', reason: 'error' };
  }
  return { type: 'complete', reason: 'stop' };
};

export const preserveUpdatedCards = (
  message: Message,
  updatedCards: ReadonlyMap<string, ChatCard>,
): Message => ({
  ...message,
  ...(message.parts ? {
    parts: message.parts.map(part => part.type === 'application' && updatedCards.has(part.cardId)
      ? { ...part, card: updatedCards.get(part.cardId)! }
      : part),
  } : {}),
  ...(message.legacyCards ? {
    legacyCards: message.legacyCards.map(card => updatedCards.get(card.cardId) ?? card),
  } : {}),
});

export const toAssistantMessage = (message: Message): ThreadMessageLike => {
  const createdAt = messageDate(message.createdAt);
  if (message.role === 'user') {
    return {
      id: message.id,
      role: 'user',
      content: [{ type: 'text', text: message.text }],
      ...(createdAt ? { createdAt } : {}),
    };
  }

  const execution = message.execution;
  const content: AssistantContentPart[] = [];
  execution?.modelMessages.forEach((modelMessage) => {
    if (modelMessage.reasoning) {
      content.push({ type: 'reasoning', text: modelMessage.reasoning });
    }
  });
  execution?.toolCalls.forEach((tool) => {
    content.push({
      type: 'tool-call',
      toolCallId: tool.toolCallId,
      toolName: tool.name,
      args: tool.arguments,
      ...(tool.lifecycleStatus === 'running' ? {} : { result: tool.result ?? null }),
      ...(tool.lifecycleStatus === 'raised' || tool.toolMessageStatus === 'error'
        ? { isError: true }
        : {}),
    });
  });
  if (message.parts?.length) {
    message.parts.forEach((part) => {
      if (part.type === 'text' && part.text) content.push({ type: 'text', text: part.text });
    });
  } else if (message.text) content.push({ type: 'text', text: message.text });

  return {
    id: message.id,
    role: 'assistant',
    content,
    status: assistantStatus(message),
    ...(createdAt ? { createdAt } : {}),
    metadata: { custom: { turnId: execution?.turnId ?? '' } },
  };
};

const appendTextPart = (
  parts: ChatContentPart[] | undefined,
  event: Extract<ChatStreamEvent, { type: 'text_delta' }>,
): ChatContentPart[] => {
  const current = parts ?? [];
  const last = current[current.length - 1];
  if (last?.id === event.partId) {
    if (last.type !== 'text') throw new Error('CHAT_PART_ORDER_INVALID');
    return current.map((part, index) => index === current.length - 1
      ? { ...last, text: last.text + event.text }
      : part);
  }
  if (current.some(part => part.id === event.partId)) throw new Error('CHAT_PART_ORDER_INVALID');
  return [...current, {
    type: 'text',
    id: event.partId,
    text: event.text,
    ...(event.modelMessageId ? { modelMessageId: event.modelMessageId } : {}),
  }];
};

const upsertApplicationPart = (
  parts: ChatContentPart[] | undefined,
  event: Extract<ChatStreamEvent, { type: 'application_rendered' }>,
): ChatContentPart[] => {
  const current = parts ?? [];
  const existing = current.findIndex(part => part.id === event.partId
    || (part.type === 'application' && part.cardId === event.card.cardId));
  const next = {
    type: 'application' as const,
    id: event.partId,
    cardId: event.card.cardId,
    card: event.card,
  };
  if (existing < 0) return [...current, next];
  const existingPart = current[existing];
  if (existingPart.type !== 'application') throw new Error('CHAT_PART_ORDER_INVALID');
  return current.map((part, index) => index === existing
    ? { ...next, id: existingPart.id }
    : part);
};

const emptyExecution = (
  turnId: string,
  inputMessageId: string,
  assistantMessageId: string,
): ChatExecution => ({
  schemaVersion: 'v1',
  turnId,
  inputMessageId,
  assistantMessageId,
  modelMessages: [],
  toolCalls: [],
});

const upsertModelMessage = (
  items: ChatModelMessage[],
  sequence: number,
  messageId: string,
  field: 'text' | 'reasoning',
  delta: string,
): ChatModelMessage[] => {
  const index = items.findIndex((item) => item.messageId === messageId);
  if (index < 0) {
    return [...items, {
      sequence,
      messageId,
      text: field === 'text' ? delta : '',
      reasoning: field === 'reasoning' ? delta : '',
      phase: 'process',
    }];
  }
  return items.map((item, itemIndex) => itemIndex === index
    ? { ...item, [field]: item[field] + delta }
    : item);
};

const startTool = (items: ChatToolCall[], event: Extract<ChatStreamEvent, { type: 'tool_call_started' }>) => {
  const next: ChatToolCall = {
    sequence: event.sequence,
    toolCallId: event.toolCallId,
    name: event.name,
    arguments: event.arguments,
    lifecycleStatus: 'running',
    startedAt: event.startedAt,
  };
  const current = items.find((item) => item.toolCallId === event.toolCallId);
  if (!current) return [...items, next];
  return items.map((item) => item.toolCallId === event.toolCallId ? next : item);
};

const finishTool = (items: ChatToolCall[], event: Extract<ChatStreamEvent, { type: 'tool_call_finished' }>) => {
  const current = items.find((item) => item.toolCallId === event.toolCallId);
  if (!current && !event.startedAt) return items;
  const next: ChatToolCall = {
    sequence: current?.sequence ?? event.sequence,
    toolCallId: event.toolCallId,
    name: event.name,
    arguments: current?.arguments ?? {},
    lifecycleStatus: event.lifecycleStatus,
    toolMessageStatus: event.toolMessageStatus,
    ...(event.businessSuccess !== undefined ? { businessSuccess: event.businessSuccess } : {}),
    startedAt: current?.startedAt ?? event.startedAt!,
    finishedAt: event.finishedAt,
    durationMs: event.durationMs,
    ...(event.result !== undefined ? { result: event.result } : {}),
    ...(event.errorCode ? { errorCode: event.errorCode } : {}),
  };
  if (!current) return [...items, next];
  return items.map((item) => item.toolCallId === event.toolCallId ? next : item);
};

export const applyChatStreamEvent = (
  message: Message,
  event: ChatStreamEvent,
): Message => {
  if (event.type === 'turn_started') {
    return {
      ...message,
      delivery: 'running',
      execution: emptyExecution(event.turnId, event.inputMessageId, event.messageId),
    };
  }
  if (event.type === 'text_delta' || event.type === 'reasoning_delta') {
    if (!message.execution) {
      return event.type === 'text_delta'
        ? { ...message, text: message.text + event.text, parts: appendTextPart(message.parts, event) }
        : { ...message, reasoning: (message.reasoning ?? '') + event.text };
    }
    if (!event.modelMessageId) {
      return event.type === 'text_delta'
        ? { ...message, text: message.text + event.text, parts: appendTextPart(message.parts, event) }
        : { ...message, reasoning: (message.reasoning ?? '') + event.text };
    }
    const next = {
      ...message,
      execution: {
        ...message.execution,
        modelMessages: upsertModelMessage(
          message.execution.modelMessages,
          event.sequence,
          event.modelMessageId,
          event.type === 'text_delta' ? 'text' : 'reasoning',
          event.text,
        ),
      },
    };
    return event.type === 'text_delta'
      ? { ...next, parts: appendTextPart(message.parts, event) }
      : next;
  }
  if (event.type === 'tool_call_started' && message.execution) {
    return {
      ...message,
      execution: {
        ...message.execution,
        toolCalls: startTool(message.execution.toolCalls, event),
      },
    };
  }
  if (event.type === 'tool_call_finished' && message.execution) {
    return {
      ...message,
      execution: {
        ...message.execution,
        toolCalls: finishTool(message.execution.toolCalls, event),
      },
    };
  }
  if (event.type === 'application_rendered' && message.execution) {
    return {
      ...message,
      parts: upsertApplicationPart(message.parts, event),
      execution: { ...message.execution, turnId: event.turnId },
    };
  }
  if (event.type === 'waiting_action' && message.execution) {
    return {
      ...message,
      delivery: 'waiting_action',
      execution: { ...message.execution, turnId: event.turnId },
    };
  }
  if (event.type === 'error') {
    return { ...message, delivery: 'unconfirmed', errorCode: event.code };
  }
  return message;
};

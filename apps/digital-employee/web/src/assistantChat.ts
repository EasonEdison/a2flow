import type { ThreadMessageLike } from '@assistant-ui/react';

import type {
  ChatExecution,
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
  if (message.text) content.push({ type: 'text', text: message.text });

  return {
    id: message.id,
    role: 'assistant',
    content,
    status: assistantStatus(message),
    ...(createdAt ? { createdAt } : {}),
    metadata: { custom: { turnId: execution?.turnId ?? '' } },
  };
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
    if (!event.modelMessageId || !message.execution) {
      return event.type === 'text_delta'
        ? { ...message, text: message.text + event.text }
        : { ...message, reasoning: (message.reasoning ?? '') + event.text };
    }
    return {
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
  if ((event.type === 'application_rendered' || event.type === 'waiting_action') && message.execution) {
    return {
      ...message,
      delivery: event.type === 'waiting_action' ? 'waiting_action' : message.delivery,
      execution: { ...message.execution, turnId: event.turnId },
    };
  }
  if (event.type === 'error') {
    return { ...message, delivery: 'unconfirmed', errorCode: event.code };
  }
  return message;
};

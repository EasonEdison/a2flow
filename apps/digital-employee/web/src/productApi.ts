import { parseView } from './api/contracts';
import { toView } from './api/adapter';
import type { RunView } from './presentation';
import { readChatStream } from './chatStream.mjs';
import { persistedChatErrorCode } from './errorPresentation';

export type Session = { userId: string; username: string; role: string };
export type Conversation = { id: string; title: string; updatedAt: string };
export type ChatEvent = { type: 'workflow_confirm'; workflowKey: string; title: string } | { type: 'interaction_required'; runId: string };
export type ChatJson = null | boolean | number | string | ChatJson[] | { [key: string]: ChatJson };
export type ChatModelMessage = {
  sequence: number;
  messageId: string;
  text: string;
  reasoning: string;
  phase: 'process' | 'final';
};
export type ChatToolCall = {
  observationStatus?: 'waiting' | 'unconfirmed';
  argumentsUnavailable?: boolean;
  resultUnavailable?: boolean;
  sequence: number;
  toolCallId: string;
  name: string;
  arguments: Record<string, ChatJson>;
  lifecycleStatus: 'running' | 'returned' | 'raised';
  toolMessageStatus?: 'success' | 'error' | null;
  businessSuccess?: boolean | null;
  startedAt: string;
  finishedAt?: string;
  durationMs?: number;
  result?: ChatJson;
  errorCode?: string;
};
export type ChatExecution = {
  schemaVersion: 'v1';
  turnId: string;
  inputMessageId: string;
  assistantMessageId: string;
  modelMessages: ChatModelMessage[];
  toolCalls: ChatToolCall[];
};
export type ChatTextPart = {
  type: 'text';
  id: string;
  text: string;
  modelMessageId?: string;
};
export type ChatApplicationPart = {
  type: 'application';
  id: string;
  cardId: string;
  card: ChatCard | null;
};
export type ChatContentPart = ChatTextPart | ChatApplicationPart;
export type Message = {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  createdAt: string;
  event?: ChatEvent;
  delivery?: string;
  errorCode?: string;
  reasoning?: string;
  tools?: string[];
  execution?: ChatExecution;
  parts?: ChatContentPart[];
  legacyCards?: ChatCard[];
};
type ChatStreamBase = { sequence: number; messageId: string; inputMessageId: string };
export type ChatStreamEvent = ChatStreamBase & (
  | { type: 'turn_started'; turnId: string }
  | { type: 'text_delta'; partId: string; modelMessageId?: string | null; text: string }
  | { type: 'reasoning_delta'; modelMessageId?: string | null; text: string }
  | { type: 'tool_call_started'; toolCallId: string; name: string; arguments: Record<string, ChatJson>; startedAt: string }
  | { type: 'tool_call_finished'; toolCallId: string; name: string; lifecycleStatus: 'returned' | 'raised'; toolMessageStatus: 'success' | 'error' | null; businessSuccess?: boolean | null; startedAt?: string; finishedAt: string; durationMs: number; result?: ChatJson; errorCode?: string }
  | { type: 'application_rendered'; turnId: string; assistantMessageId: string; partId: string; card: ChatCard }
  | { type: 'waiting_action'; turnId: string; assistantMessageId: string; partId: string; cardId: string }
  | { type: 'done'; finalModelMessageId?: string | null; content: unknown }
  | { type: 'error'; code?: string }
);
export type Workflow = { key: string; name: string; description: string; inputHint: string };
export type RunItem = { id: string; workflowKey: string; title: string; status: string; input: string; createdAt: string };
export type Schedule = { id: string; workflowKey: string; workflowName: string; input: string; cadence: string; enabled: boolean; nextRunAt: string };
export type Notification = { id: string; type: string; title: string; relatedType?: string; relatedId?: string; read: boolean; createdAt: string };

export type ApiError = Error & { code: string };
export type MemoryEntry = { id: string; text: string };
export type MemorySettings = { revision: number; enabled: boolean; entries: MemoryEntry[] };
export type ChatCard = { cardId: string; conversationId: string; turnId: string; status: string; result?: unknown;
  display: { applicationKey: string; applicationVersion?: string | number; protocolProfile: string;
    snapshotMessages: Record<string, unknown>[];
    catalog: { protocolVersion: string; catalogId: string; catalogRevision: string | number; catalogDigest: string };
    rootId?: string; components?: Record<string, unknown>[]; data?: Record<string, unknown>;
    actions: { actionName: string; surfaceId: string; componentId: string; inputSchema: Record<string, unknown> }[] } };
export type ComposerDraftEffect = { type: 'COMPOSER_DRAFT'; mode: 'APPEND'; requestId: string; text: string };
export type ChatActionResponse = { card: ChatCard; effects: ComposerDraftEffect[] };
export type WorkflowCard = { nodeId: string; interactionId: string; toolCallId?: string; card: ChatCard };

const friendlyMessages: Record<string, string> = {
  INVALID_USERNAME: '用户名需为 3–32 位字母、数字、下划线或连字符',
  INVALID_PASSWORD: '密码至少需要 8 位',
  USERNAME_TAKEN: '该用户名已被注册',
  INVALID_CREDENTIALS: '用户名或密码错误',
  AUTHENTICATION_REQUIRED: '登录已过期，请重新登录',
  UNAUTHENTICATED: '登录已过期，请重新登录',
  REQUEST_FAILED: '请求失败，请稍后再试',
  MEMORY_UNAVAILABLE: '个人记忆暂不可用，请稍后重新读取',
  INVALID_MEMORY_SETTINGS: '记忆格式或长度不符合要求，请检查后再保存',
  MEMORY_REVISION_CONFLICT: '记忆已在其他页面更新，请重新读取后再编辑，避免覆盖其他修改',
};

export function apiErrorMessage(error: unknown, fallback = '操作失败，请稍后再试'): string {
  const code = (error as ApiError | null)?.code;
  if (code) return friendlyMessages[code] ?? fallback;
  return fallback;
}

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    credentials: 'same-origin',
    cache: 'no-store',
    ...options,
    headers: options.body ? { 'Content-Type': 'application/json', ...options.headers } : options.headers,
  });
  const text = await response.text();
  if (!response.ok) {
    let code = response.status === 401 ? 'UNAUTHENTICATED' : 'REQUEST_FAILED';
    try {
      const payload = JSON.parse(text) as { error?: { code?: string } };
      if (payload?.error?.code) code = payload.error.code;
    } catch {
      /* non-JSON body */
    }
    const error = new Error(text || code) as ApiError;
    error.code = code;
    throw error;
  }
  return text ? JSON.parse(text) as T : {} as T;
}

const body = (value: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(value) });

type Row = Record<string, unknown>;

const textOf = (value: unknown): string => (typeof value === 'string' ? value : '');
const idOf = (value: unknown): string => (typeof value === 'number' ? String(value) : textOf(value));

const inputHintOf = (schema: unknown): string => {
  const props = (schema as { properties?: { requirement?: { description?: unknown } } } | null | undefined)?.properties;
  return typeof props?.requirement?.description === 'string'
    ? props.requirement.description
    : '输入工作流执行内容';
};

const contentText = (content: unknown): string => {
  if (typeof content === 'string') return content;
  if (content && typeof content === 'object' && !Array.isArray(content)) {
    const text = (content as { text?: unknown }).text;
    if (typeof text === 'string') return text;
  }
  return '';
};

const recordOf = (value: unknown): Row => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('CHAT_CONTRACT_INVALID');
  }
  return value as Row;
};

const optionalString = (value: unknown): string | undefined => (
  typeof value === 'string' && value ? value : undefined
);

const finiteDuration = (value: unknown): number | undefined => (
  Number.isSafeInteger(value) && Number(value) >= 0 ? Number(value) : undefined
);

const chatCardOf = (value: unknown): ChatCard => {
  const card = recordOf(value);
  const display = recordOf(card.display);
  const catalog = recordOf(display.catalog);
  const actions = Array.isArray(display.actions) ? display.actions.map((value) => {
    const action = recordOf(value);
    return {
      actionName: textOf(action.actionName),
      surfaceId: textOf(action.surfaceId),
      componentId: textOf(action.componentId),
      inputSchema: recordOf(action.inputSchema),
    };
  }) : [];
  if (!card.cardId || !card.conversationId || !card.status
    || !display.applicationKey || !display.protocolProfile
    || !catalog.protocolVersion || !catalog.catalogId || !catalog.catalogDigest
    || !Array.isArray(display.snapshotMessages)) {
    throw new Error('CHAT_CONTRACT_INVALID');
  }
  return {
    cardId: textOf(card.cardId),
    conversationId: textOf(card.conversationId),
    turnId: textOf(card.turnId),
    status: textOf(card.status),
    ...(card.result !== undefined ? { result: card.result } : {}),
    display: {
      applicationKey: textOf(display.applicationKey),
      ...(typeof display.applicationVersion === 'string' || typeof display.applicationVersion === 'number'
        ? { applicationVersion: display.applicationVersion } : {}),
      protocolProfile: textOf(display.protocolProfile),
      snapshotMessages: display.snapshotMessages.map(recordOf),
      catalog: {
        protocolVersion: textOf(catalog.protocolVersion),
        catalogId: textOf(catalog.catalogId),
        catalogRevision: typeof catalog.catalogRevision === 'number'
          ? catalog.catalogRevision : textOf(catalog.catalogRevision),
        catalogDigest: textOf(catalog.catalogDigest),
      },
      ...(optionalString(display.rootId) ? { rootId: textOf(display.rootId) } : {}),
      ...(Array.isArray(display.components) ? { components: display.components.map(recordOf) } : {}),
      ...(display.data && typeof display.data === 'object' && !Array.isArray(display.data)
        ? { data: recordOf(display.data) } : {}),
      actions,
    },
  };
};

const contentPartsOf = (content: unknown): ChatContentPart[] | undefined => {
  if (!content || typeof content !== 'object' || Array.isArray(content)) return undefined;
  const raw = (content as Row).parts;
  if (raw === undefined) return undefined;
  if (!Array.isArray(raw)) throw new Error('CHAT_CONTRACT_INVALID');
  const ids = new Set<string>();
  const cardIds = new Set<string>();
  return raw.map((value) => {
    const part = recordOf(value);
    const id = textOf(part.id);
    if (!id || ids.has(id)) throw new Error('CHAT_CONTRACT_INVALID');
    ids.add(id);
    if (part.type === 'text') {
      return {
        type: 'text',
        id,
        text: textOf(part.text),
        ...(optionalString(part.modelMessageId) ? { modelMessageId: textOf(part.modelMessageId) } : {}),
      } satisfies ChatTextPart;
    }
    if (part.type === 'application') {
      const cardId = textOf(part.cardId);
      if (!cardId || (part.card !== null && part.card === undefined)) {
        throw new Error('CHAT_CONTRACT_INVALID');
      }
      if (cardIds.has(cardId)) throw new Error('CHAT_CONTRACT_INVALID');
      cardIds.add(cardId);
      const card = part.card === null ? null : chatCardOf(part.card);
      if (card && card.cardId !== cardId) throw new Error('CHAT_CONTRACT_INVALID');
      return { type: 'application', id, cardId, card } satisfies ChatApplicationPart;
    }
    throw new Error('CHAT_CONTRACT_INVALID');
  });
};

const executionOf = (content: unknown): ChatExecution | undefined => {
  if (!content || typeof content !== 'object' || Array.isArray(content)) return undefined;
  const raw = (content as Row).execution;
  if (raw === undefined) return undefined;
  const execution = recordOf(raw);
  if (execution.schemaVersion !== 'v1') throw new Error('CHAT_EXECUTION_VERSION_UNSUPPORTED');
  const modelMessages = Array.isArray(execution.modelMessages) ? execution.modelMessages.map((value) => {
    const item = recordOf(value);
    if (!Number.isSafeInteger(item.sequence) || Number(item.sequence) < 1
      || (item.phase !== 'process' && item.phase !== 'final')) {
      throw new Error('CHAT_CONTRACT_INVALID');
    }
    return {
      sequence: Number(item.sequence),
      messageId: textOf(item.messageId),
      text: textOf(item.text),
      reasoning: textOf(item.reasoning),
      phase: item.phase,
    } satisfies ChatModelMessage;
  }) : [];
  const toolCalls = Array.isArray(execution.toolCalls) ? execution.toolCalls.map((value) => {
    const item = recordOf(value);
    if (!Number.isSafeInteger(item.sequence) || Number(item.sequence) < 1
      || !['running', 'returned', 'raised'].includes(textOf(item.lifecycleStatus))) {
      throw new Error('CHAT_CONTRACT_INVALID');
    }
    const toolMessageStatus = item.toolMessageStatus === null
      ? null
      : optionalString(item.toolMessageStatus);
    if (toolMessageStatus !== undefined && toolMessageStatus !== null
      && !['success', 'error'].includes(toolMessageStatus)) {
      throw new Error('CHAT_CONTRACT_INVALID');
    }
    const durationMs = finiteDuration(item.durationMs);
    return {
      sequence: Number(item.sequence),
      toolCallId: textOf(item.toolCallId),
      name: textOf(item.name),
      arguments: recordOf(item.arguments) as Record<string, ChatJson>,
      lifecycleStatus: textOf(item.lifecycleStatus) as ChatToolCall['lifecycleStatus'],
      ...(toolMessageStatus !== undefined ? { toolMessageStatus: toolMessageStatus as ChatToolCall['toolMessageStatus'] } : {}),
      ...(typeof item.businessSuccess === 'boolean' || item.businessSuccess === null
        ? { businessSuccess: item.businessSuccess as boolean | null } : {}),
      startedAt: textOf(item.startedAt),
      ...(optionalString(item.finishedAt) ? { finishedAt: textOf(item.finishedAt) } : {}),
      ...(durationMs !== undefined ? { durationMs } : {}),
      ...(item.result !== undefined ? { result: item.result as ChatJson } : {}),
      ...(optionalString(item.errorCode) ? { errorCode: textOf(item.errorCode) } : {}),
    } satisfies ChatToolCall;
  }) : [];
  return {
    schemaVersion: 'v1',
    turnId: textOf(execution.turnId),
    inputMessageId: textOf(execution.inputMessageId),
    assistantMessageId: textOf(execution.assistantMessageId),
    modelMessages,
    toolCalls,
  };
};

export const messageFromContent = (
  id: string,
  role: 'user' | 'assistant',
  content: unknown,
  createdAt: string,
): Message => {
  const event = contentEvent(content);
  const errorCode = persistedChatErrorCode(content);
  const execution = executionOf(content);
  const parts = contentPartsOf(content);
  const legacyCards = parts === undefined && Array.isArray((content as Row)?.legacyCards)
    ? ((content as Row).legacyCards as unknown[]).map(chatCardOf)
    : undefined;
  return {
    id,
    role,
    text: contentText(content),
    delivery: textOf((content as Row)?.delivery),
    // Legacy fields remain read-compatible for one release. New UI process rendering uses execution only.
    reasoning: textOf((content as Row)?.reasoning),
    tools: Array.isArray((content as Row)?.tools)
      ? ((content as Row).tools as unknown[]).filter((value): value is string => typeof value === 'string')
      : [],
    createdAt,
    ...(execution ? { execution } : {}),
    ...(parts !== undefined ? { parts } : {}),
    ...(legacyCards?.length ? { legacyCards } : {}),
    ...(event ? { event } : {}),
    ...(errorCode ? { errorCode } : {}),
  };
};

const refEvent = (row: Row): ChatEvent | undefined => (
  row.refKind === 'run' && row.refId
    ? { type: 'interaction_required', runId: textOf(row.refId) }
    : undefined
);

const contentEvent = (content: unknown): ChatEvent | undefined => {
  if (!content || typeof content !== 'object' || Array.isArray(content)) return undefined;
  const events = (content as { events?: unknown }).events;
  if (!Array.isArray(events)) return undefined;
  const confirm = events.find((item) => item && typeof item === 'object'
    && (item as Row).type === 'workflow_confirm' && (item as Row).workflowKey);
  if (confirm) return { type: 'workflow_confirm', workflowKey: textOf((confirm as Row).workflowKey), title: textOf((confirm as Row).title) || '工作流' };
  const interaction = events.find((item) => item && typeof item === 'object'
    && (item as Row).type === 'interaction_required' && (item as Row).runId);
  if (interaction) return { type: 'interaction_required', runId: textOf((interaction as Row).runId) };
  return undefined;
};

const cadenceOf = (row: Row): string => {
  if (row.ruleType === 'cron') return `${textOf(recordOf(row.ruleJson).expression)} · ${textOf(row.timezone)}`;
  if (row.ruleType === 'once') return '一次性执行';
  const rule = (row.ruleJson ?? {}) as { every?: unknown; at?: unknown };
  const base = rule.every === '15m' ? '每 15 分钟'
    : rule.every === '1h' ? '每小时'
      : rule.every === '1d' ? '每天'
        : rule.every === '1w' ? '每周' : textOf(rule.every);
  return typeof rule.at === 'string' && rule.at ? `${base} ${rule.at}` : base;
};

const readSurfaceStream = async (response: Response, onSurface: (view: RunView) => void) => {
  if (!response.body) return;
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let split;
      while ((split = buffer.indexOf('\n\n')) >= 0) {
        const block = buffer.slice(0, split);
        buffer = buffer.slice(split + 2);
        const line = block.split('\n').find((item) => item.startsWith('data:'));
        if (!line) continue;
        const item = JSON.parse(line.slice(5).trim()) as { type: string; view?: Row };
        if ((item.type === 'surface' || item.type === 'snapshot') && item.view && Array.isArray(item.view.nodes)) {
          onSurface(toView(parseView(item.view), {}));
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
};

export const productApi = {
  chatAction: (id: string, card: ChatCard, requestId: string, actionName: string, inputs: Record<string, unknown>) => api<ChatActionResponse>(
    `/api/conversations/${encodeURIComponent(id)}/cards/${encodeURIComponent(card.cardId)}/actions`,
    body({ requestId, actionName, inputs })),
  memory: (signal?: AbortSignal) => api<MemorySettings>('/api/memory', { signal }),
  saveMemory: (settings: MemorySettings) => api<MemorySettings>('/api/memory', {
    method: 'PUT', body: JSON.stringify(settings),
  }),
  session: () => api<Session>('/api/auth/session'),
  login: (username: string, password: string) => api<Session>('/api/auth/login', body({ username, password })),
  register: (username: string, password: string) => api<Session>('/api/auth/register', body({ username, password })),
  logout: () => api('/api/auth/logout', body({})),
  conversations: async (): Promise<{ items: Conversation[] }> => {
    const payload = await api<{ conversations?: Row[] }>('/api/conversations');
    return {
      items: (payload.conversations ?? []).map((row) => ({
        id: idOf(row.id),
        title: textOf(row.title) || '新会话',
        updatedAt: textOf(row.createdAt),
      })),
    };
  },
  createConversation: async (): Promise<Conversation> => {
    const row = await api<Row>('/api/conversations', body({}));
    return { id: idOf(row.id), title: textOf(row.title) || '新会话', updatedAt: textOf(row.createdAt) };
  },
  messages: async (id: string): Promise<{ items: Message[]; unassignedCards: ChatCard[] }> => {
    const payload = await api<{ messages?: Row[]; unassignedCards?: unknown[] }>(`/api/conversations/${encodeURIComponent(id)}/messages`);
    return {
      items: (payload.messages ?? []).map((row) => {
        const parsed = messageFromContent(
          idOf(row.id),
          row.role === 'user' ? 'user' : 'assistant',
          row.content,
          textOf(row.createdAt),
        );
        return parsed.event ? parsed : { ...parsed, event: refEvent(row) };
      }),
      unassignedCards: (payload.unassignedCards ?? []).map(chatCardOf),
    };
  },
  sendMessage: async (id: string, text: string, onEvent: (event: ChatStreamEvent) => void, signal?: AbortSignal) => {
    const response = await fetch(`/api/conversations/${encodeURIComponent(id)}/messages`, { ...body({ text }), signal, credentials: 'same-origin', headers: { 'Content-Type': 'application/json' } });
    if (!response.ok) {
      const error = new Error('发送失败') as ApiError;
      error.code = 'REQUEST_FAILED';
      throw error;
    }
    await readChatStream(response, onEvent);
  },
  workflows: async (): Promise<{ items: Workflow[] }> => {
    const payload = await api<{ workflows?: Row[] }>('/api/workflows');
    return {
      items: (payload.workflows ?? []).map((row) => {
        const key = textOf(row.definitionKey);
        return { key, name: textOf(row.name) || key, description: '', inputHint: inputHintOf(row.inputSchema) };
      }),
    };
  },
  runs: async (): Promise<{ items: RunItem[] }> => {
    const payload = await api<{ runs?: Row[] }>('/api/runs');
    return {
      items: (payload.runs ?? []).map((row) => {
        const view = (row.view ?? null) as Row | null;
        const bound = Boolean(view && view.runId);
        const lifecycle = textOf(row.lifecycle);
        const status = ['PENDING', 'RUNNING', 'WAITING', 'SUCCEEDED', 'STOPPED', 'FAILED', 'SKIPPED', 'UNKNOWN'].includes(lifecycle)
          ? lifecycle : bound ? 'UNKNOWN' : 'SUBMITTED';
        return {
          id: textOf(row.controlRequestId),
          workflowKey: textOf(row.workflowKey),
          title: bound ? textOf(view?.title) || textOf(row.workflowKey) : textOf(row.workflowKey),
          status,
          input: '',
          createdAt: textOf(row.createdAt),
        };
      }),
    };
  },
  run: async (id: string): Promise<RunView> => {
    const payload = await api<Row>(`/api/runs/${encodeURIComponent(id)}`);
    if (!Array.isArray(payload.nodes)) {
      return { id, title: '运行准备中', lifecycle: 'RUNNING', nodes: [] };
    }
    const view = toView(parseView(payload), {});
    // The b-side API addresses runs by control id; keep it as the product id.
    return { ...view, id };
  },
  runCards: async (id: string, signal?: AbortSignal): Promise<WorkflowCard[]> => {
    const payload = await api<{ cards: unknown[] }>(`/api/runs/${encodeURIComponent(id)}/cards`, { signal });
    if (!Array.isArray(payload.cards)) throw new Error('WORKFLOW_CARD_CONTRACT_INVALID');
    return payload.cards.map(value => {
      const entry = recordOf(value);
      if (!entry.nodeId || !entry.interactionId) throw new Error('WORKFLOW_CARD_CONTRACT_INVALID');
      return { nodeId: textOf(entry.nodeId), interactionId: textOf(entry.interactionId), toolCallId: textOf(entry.toolCallId), card: chatCardOf(entry.card) };
    });
  },
  runCardAction: async (id: string, entry: WorkflowCard, requestId: string, actionName: string, inputs: Record<string, unknown>): Promise<ChatActionResponse> => {
    const response = await api<{ card: unknown; effects?: ComposerDraftEffect[] }>(
      `/api/runs/${encodeURIComponent(id)}/cards/${encodeURIComponent(entry.card.cardId)}/actions`,
      body({ requestId, nodeId: entry.nodeId, interactionId: entry.interactionId, actionName, inputs }));
    return { card: chatCardOf(response.card), effects: response.effects ?? [] };
  },
  attachRun: (conversationId: string, runId: string) => api(`/api/conversations/${encodeURIComponent(conversationId)}/run-refs`, body({ runId })),
  startRun: async (workflowKey: string, input: string): Promise<{ runId: string }> => {
    const payload = await api<{ controlRequestId?: unknown }>('/api/runs', body({ workflowKey, input }));
    return { runId: textOf(payload.controlRequestId) };
  },
  runAction: async (id: string, nodeId: string, interactionId: string, actionName: string, value: string, confirmed: boolean, onSurface: (view: RunView) => void) => {
    const response = await fetch(`/api/runs/${encodeURIComponent(id)}/actions`, {
      ...body({ nodeId, interactionId, actionName, inputs: { optionId: value, ...(confirmed ? { confirmed: true } : {}) } }),
      headers: { 'Content-Type': 'application/json' },
    });
    if (!response.ok) {
      const error = new Error('操作失败') as ApiError;
      error.code = 'REQUEST_FAILED';
      try {
        const payload = JSON.parse(await response.text()) as { error?: { code?: string } };
        if (payload?.error?.code) error.code = payload.error.code;
      } catch {
        /* non-JSON body */
      }
      throw error;
    }
    await readSurfaceStream(response, (view) => onSurface({ ...view, id }));
  },
  subscribeSurface: async (id: string, onSurface: (view: RunView) => void, signal?: AbortSignal) => {
    const response = await fetch(`/api/runs/${encodeURIComponent(id)}/surface`, {
      credentials: 'same-origin', cache: 'no-store', signal,
    });
    if (!response.ok) {
      const error = new Error('订阅失败') as ApiError;
      error.code = 'REQUEST_FAILED';
      throw error;
    }
    await readSurfaceStream(response, (view) => onSurface({ ...view, id }));
  },
  stopRun: (id: string) => api(`/api/runs/${encodeURIComponent(id)}/stop`, body({})),
  schedules: async (): Promise<{ items: Schedule[] }> => {
    const payload = await api<{ schedules?: Row[] }>('/api/schedules');
    return {
      items: (payload.schedules ?? []).map((row) => ({
        id: idOf(row.id),
        workflowKey: textOf(row.workflowKey),
        workflowName: textOf(row.workflowKey),
        input: textOf(row.inputText),
        cadence: cadenceOf(row),
        enabled: row.enabled === true,
        nextRunAt: textOf(row.nextRunAt),
      })),
    };
  },
  createSchedule: (value: { workflowKey: string; input: string; ruleType: string; ruleJson: Record<string, string>; timezone: string }) => api<Schedule>('/api/schedules', body({ workflowKey: value.workflowKey, inputText: value.input, ruleType: value.ruleType, ruleJson: value.ruleJson, timezone: value.timezone })),
  toggleSchedule: (id: string, enabled: boolean) => api<Schedule>(`/api/schedules/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify({ enabled }), headers: { 'Content-Type': 'application/json' } }),
  deleteSchedule: (id: string) => api(`/api/schedules/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  notifications: async (): Promise<{ items: Notification[] }> => {
    const payload = await api<{ notifications?: Row[] }>('/api/notifications');
    return {
      items: (payload.notifications ?? []).map((row) => ({
        id: idOf(row.id),
        type: textOf(row.kind) || 'SYSTEM',
        title: textOf(row.title),
        relatedType: textOf(row.refType) || undefined,
        relatedId: textOf(row.refId) || undefined,
        read: row.read === true,
        createdAt: textOf(row.createdAt),
      })),
    };
  },
  readNotification: (id: string) => api(`/api/notifications/${encodeURIComponent(id)}/read`, body({})),
};

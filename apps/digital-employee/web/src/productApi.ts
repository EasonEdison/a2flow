import type { RunView } from './presentation';

export type Session = { userId: string; username: string; role: string };
export type Conversation = { id: string; title: string; updatedAt: string };
export type ChatEvent = { type: 'workflow_confirm'; workflowKey: string; title: string } | { type: 'interaction_required'; runId: string };
export type Message = { id: string; role: 'user' | 'assistant'; text: string; createdAt: string; event?: ChatEvent };
export type Workflow = { key: string; name: string; description: string; inputHint: string };
export type RunItem = { id: string; workflowKey: string; title: string; status: string; input: string; createdAt: string };
export type Schedule = { id: string; workflowKey: string; workflowName: string; input: string; cadence: string; enabled: boolean; nextRunAt: string };
export type Notification = { id: string; type: string; title: string; relatedType?: string; relatedId?: string; read: boolean; createdAt: string };

export type ApiError = Error & { code: string };

const friendlyMessages: Record<string, string> = {
  INVALID_USERNAME: '用户名需为 3–32 位字母、数字、下划线或连字符',
  INVALID_PASSWORD: '密码至少需要 8 位',
  USERNAME_TAKEN: '该用户名已被注册',
  INVALID_CREDENTIALS: '用户名或密码错误',
  AUTHENTICATION_REQUIRED: '登录已过期，请重新登录',
  UNAUTHENTICATED: '登录已过期，请重新登录',
  REQUEST_FAILED: '请求失败，请稍后再试',
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

export const productApi = {
  session: () => api<Session>('/api/auth/session'),
  login: (username: string, password: string) => api<Session>('/api/auth/login', body({ username, password })),
  register: (username: string, password: string) => api<Session>('/api/auth/register', body({ username, password })),
  logout: () => api('/api/auth/logout', body({})),
  conversations: () => api<{ items: Conversation[] }>('/api/conversations'),
  createConversation: () => api<Conversation>('/api/conversations', body({})),
  messages: (id: string) => api<{ items: Message[] }>(`/api/conversations/${encodeURIComponent(id)}/messages`),
  sendMessage: async (id: string, text: string, onText: (text: string) => void) => {
    const response = await fetch(`/api/conversations/${encodeURIComponent(id)}/messages`, { ...body({ text }), headers: { 'Content-Type': 'application/json' } });
    if (!response.ok) {
      const error = new Error('发送失败') as ApiError;
      error.code = 'REQUEST_FAILED';
      throw error;
    }
    const raw = await response.text();
    let event: ChatEvent | undefined;
    for (const block of raw.split('\n\n')) {
      const line = block.split('\n').find((item) => item.startsWith('data:'));
      if (!line) continue;
      const item = JSON.parse(line.slice(5).trim()) as { type: string; text?: string; workflowKey?: string; title?: string; runId?: string };
      if (item.type === 'text' && item.text) onText(item.text);
      if (item.type === 'workflow_confirm' && item.workflowKey && item.title) event = { type: 'workflow_confirm', workflowKey: item.workflowKey, title: item.title };
      if (item.type === 'interaction_required' && item.runId) event = { type: 'interaction_required', runId: item.runId };
    }
    return event;
  },
  workflows: () => api<{ items: Workflow[] }>('/api/workflows'),
  runs: () => api<{ items: RunItem[] }>('/api/runs'),
  run: (id: string) => api<RunView>(`/api/runs/${encodeURIComponent(id)}`),
  startRun: (workflowKey: string, input: string) => api<{ runId: string }>('/api/runs', body({ workflowKey, input })),
  runAction: (id: string, interactionId: string, actionName: string, value: string, confirmed: boolean) => api(`/api/runs/${encodeURIComponent(id)}/actions`, body({ interactionId, actionName, input: { optionId: value, ...(confirmed ? { confirmed: true } : {}) } })),
  stopRun: (id: string) => api(`/api/runs/${encodeURIComponent(id)}/stop`, body({})),
  schedules: () => api<{ items: Schedule[] }>('/api/schedules'),
  createSchedule: (value: { workflowKey: string; input: string; cadence: string }) => api<Schedule>('/api/schedules', body(value)),
  toggleSchedule: (id: string, enabled: boolean) => api<Schedule>(`/api/schedules/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify({ enabled }), headers: { 'Content-Type': 'application/json' } }),
  deleteSchedule: (id: string) => api(`/api/schedules/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  notifications: () => api<{ items: Notification[] }>('/api/notifications'),
  readNotification: (id: string) => api(`/api/notifications/${encodeURIComponent(id)}/read`, body({})),
};

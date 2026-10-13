import { managementFetch, ManagementSessionError } from './shared/managementSession';

export type AgentTurnStatus = 'RUNNING' | 'COMPLETED' | 'FAILED' | 'UNKNOWN';
export type AgentConversation = { id: string; title: string; createdAt: string; updatedAt: string };
export type AgentTurn = { turnId: string; requestId: string; status: AgentTurnStatus; message: string; finalText: string; errorCode: string };
export type AgentAsset = { assetType: string; assetKey: string; displayName?: string; detail?: { skillCode?: string; draftId?: string; id?: string; workflowCode?: string }; publication?: { environment: 'PRT'; status: string; version?: string; sourceId?: string; deploymentId?: string; digest?: string } };
export type AgentEvent = { sequence: number; turnId: string; type: string; payload: Record<string, unknown>; assets: AgentAsset[] };
export type AgentHistory = { conversation: AgentConversation; turns: AgentTurn[]; events: AgentEvent[]; nextEventSeq: number; hasMore: boolean; canSend: boolean; mutationsBlocked: boolean };
export type AgentSendResult = { conversationId: string; turnId: string; requestId: string; status: AgentTurnStatus; errorCode: string };

export class ManagementChatError extends Error {
  constructor(public readonly code: string, public readonly rejected = false) { super(code); }
}
const invalid = (): never => { throw new ManagementChatError('RESPONSE_INVALID'); };
const object = (value: unknown): Record<string, unknown> => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return invalid();
  return value as Record<string, unknown>;
};
const text = (value: unknown): string => typeof value === 'string' ? value : invalid();
const optionalText = (value: unknown): string => value == null ? '' : text(value);
const rows = (value: unknown): unknown[] => Array.isArray(value) ? value : invalid();
const sequence = (value: unknown): number => Number.isSafeInteger(value) && Number(value) >= 0 ? Number(value) : invalid();
const status = (value: unknown): AgentTurnStatus => {
  if (!['RUNNING', 'COMPLETED', 'FAILED', 'UNKNOWN'].includes(text(value))) return invalid();
  return value as AgentTurnStatus;
};
const conversation = (value: unknown): AgentConversation => {
  const row = object(value);
  return { id: text(row.id), title: text(row.title), createdAt: text(row.createdAt), updatedAt: text(row.updatedAt) };
};

function asset(value: unknown): AgentAsset {
  const row = object(value);
  const result: AgentAsset = { assetType: text(row.assetType), assetKey: text(row.assetKey), displayName: optionalText(row.displayName) };
  if (row.detail != null) {
    const detail = object(row.detail);
    result.detail = { skillCode: optionalText(detail.skillCode), draftId: optionalText(detail.draftId), id: optionalText(detail.id), workflowCode: optionalText(detail.workflowCode) };
  }
  if (row.publication != null) {
    const publication = object(row.publication);
    if (publication.environment !== 'PRT') return invalid();
    result.publication = { environment: 'PRT', status: text(publication.status), version: optionalText(publication.version), sourceId: optionalText(publication.sourceId), deploymentId: optionalText(publication.deploymentId), digest: optionalText(publication.digest) };
  }
  return result;
}

async function request(path: string, body: object, signal?: AbortSignal): Promise<Record<string, unknown>> {
  const response = await managementFetch(`/api/management/v2/agent/conversations/${path}`, {
    method: 'POST', credentials: 'same-origin', cache: 'no-store', signal,
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }).catch(error => {
    if (error instanceof ManagementSessionError) throw new ManagementChatError(error.status === 401 ? 'ACCOUNT_AUTHENTICATION_REQUIRED' : 'PERMISSION_DENIED', true);
    throw error;
  });
  let envelope: Record<string, unknown>;
  try { envelope = object(await response.json()); }
  catch { throw new ManagementChatError('RESPONSE_INVALID'); }
  if (!response.ok || envelope.result !== 1) {
    const code = typeof envelope.errorCode === 'string' && /^[A-Z][A-Z0-9_]{0,159}$/.test(envelope.errorCode)
      ? envelope.errorCode : 'REQUEST_FAILED';
    throw new ManagementChatError(code, ['INVALID_MANAGEMENT_AGENT_REQUEST', 'ACCOUNT_AUTHENTICATION_REQUIRED', 'ADMIN_REQUIRED', 'CLIENT_IDENTITY_FIELDS_NOT_ALLOWED', 'ACCOUNT_ORIGIN_REQUIRED', 'MANAGEMENT_AGENT_ROUTE_NOT_FOUND', 'CONVERSATION_NOT_FOUND', 'REQUEST_ID_CONFLICT', 'CONVERSATION_BUSY', 'CONVERSATION_TURN_LIMIT', 'MANAGEMENT_AGENT_BUSY'].includes(code));
  }
  return object(envelope.data);
}

export const managementChatApi = {
  async list(pageToken?: string, signal?: AbortSignal) {
    const data = await request('list', { ...(pageToken ? { pageToken } : {}), limit: 50 }, signal);
    return { items: rows(data.items).map(conversation), nextPageToken: optionalText(data.nextPageToken) };
  },
  async create(requestId: string) {
    const data = await request('create', { requestId });
    return conversation(data.conversation);
  },
  async read(conversationId: string, afterEventSeq: number, signal?: AbortSignal): Promise<AgentHistory> {
    const data = await request('read', { conversationId, afterEventSeq, limit: 100 }, signal);
    if (typeof data.hasMore !== 'boolean' || typeof data.canSend !== 'boolean' || typeof data.mutationsBlocked !== 'boolean') return invalid();
    return {
      conversation: conversation(data.conversation),
      turns: rows(data.turns).map(value => {
        const row = object(value);
        return { turnId: text(row.turnId), requestId: text(row.requestId), status: status(row.status), message: text(row.message), finalText: optionalText(row.finalText), errorCode: optionalText(row.errorCode) };
      }),
      events: rows(data.events).map(value => {
        const row = object(value);
        const payload = object(row.payload);
        const result = row.type === 'TOOL_COMPLETED' && payload.result != null ? object(payload.result) : null;
        const assets = result?.assets == null ? [] : rows(result.assets).map(asset);
        return { sequence: sequence(row.sequence), turnId: text(row.turnId), type: text(row.type), payload, assets };
      }),
      nextEventSeq: sequence(data.nextEventSeq), hasMore: data.hasMore, canSend: data.canSend, mutationsBlocked: data.mutationsBlocked,
    };
  },
  async send(conversationId: string, requestId: string, message: string): Promise<AgentSendResult> {
    const data = await request('send', { conversationId, requestId, message });
    return { conversationId: text(data.conversationId), turnId: text(data.turnId), requestId: text(data.requestId), status: status(data.status), errorCode: optionalText(data.errorCode) };
  },
};

export function newManagementChatRequestId(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
}

import type {
  AssetKind,
  AssetSummary,
  JsonObject,
  ManagedDraft,
  ManagementSession,
  PublicationPlan,
  ValidationReport,
} from './contracts';

export class ManagementApiError extends Error {
  constructor(readonly code: string, readonly status: number) {
    super(code);
    this.name = 'ManagementApiError';
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(path, {
    ...init,
    signal,
    credentials: 'same-origin',
    headers: {
      Accept: 'application/json',
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...init.headers,
    },
  });
  const payload = (await response.json().catch(() => null)) as
    | { error?: { code?: string } }
    | T
    | null;
  if (!response.ok) {
    const code =
      payload && typeof payload === 'object' && 'error' in payload
        ? payload.error?.code
        : undefined;
    throw new ManagementApiError(code ?? 'REQUEST_FAILED', response.status);
  }
  return payload as T;
}

function assetPath(kind: AssetKind, key?: string): string {
  const root = '/management/assets/' + encodeURIComponent(kind);
  return key === undefined ? root : root + '/' + encodeURIComponent(key);
}

export const managementApi = {
  session(signal?: AbortSignal) {
    return request<ManagementSession>('/management/session', {}, signal);
  },
  list(kind: AssetKind, signal?: AbortSignal) {
    return request<AssetSummary[]>(assetPath(kind), {}, signal);
  },
  detail(kind: AssetKind, key: string, signal?: AbortSignal) {
    return request<JsonObject>(assetPath(kind, key), {}, signal);
  },
  draft(kind: AssetKind, key: string, signal?: AbortSignal) {
    return request<ManagedDraft>(assetPath(kind, key) + '/draft', {}, signal);
  },
  saveDraft(kind: AssetKind, key: string, expectedRevision: number, document: JsonObject) {
    return request<ManagedDraft>(assetPath(kind, key) + '/draft', {
      method: 'PUT',
      body: JSON.stringify({ expectedRevision, document }),
    });
  },
  validate(kind: AssetKind, key: string) {
    return request<ValidationReport>(assetPath(kind, key) + '/validate', {
      method: 'POST',
    });
  },
  prepare(
    kind: AssetKind,
    key: string,
    expectedRevision: number,
    target: {
      environment: string;
      versionId: string;
      channel: string;
      grayUserIds: string[];
    },
  ) {
    return request<PublicationPlan>(assetPath(kind, key) + '/publication-plans', {
      method: 'POST',
      body: JSON.stringify({ expectedRevision, target }),
    });
  },
};

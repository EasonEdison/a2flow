import type {
  AssetKind,
  AssetSummary,
  DependencyGraph,
  JsonObject,
  ManagedDraft,
  ManagementSession,
  PublicationCheck,
  PublicationHistory,
  PublicationPlan,
  PublicationResult,
  PublicationTarget,
  RetainedVersion,
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
  logout() {
    return request<{ ok: boolean }>('/private-preview/logout', { method: 'POST' });
  },
  list(kind: AssetKind, signal?: AbortSignal) {
    return request<AssetSummary[]>(assetPath(kind), {}, signal);
  },
  detail(kind: AssetKind, key: string, signal?: AbortSignal) {
    return request<JsonObject>(assetPath(kind, key), {}, signal);
  },
  dependencies(kind: AssetKind, key: string, signal?: AbortSignal) {
    return request<DependencyGraph>(assetPath(kind, key) + '/dependencies', {}, signal);
  },
  draft(kind: AssetKind, key: string, signal?: AbortSignal) {
    return request<ManagedDraft>(assetPath(kind, key) + '/draft', {}, signal);
  },
  createDraft(kind: AssetKind, key: string) {
    return request<ManagedDraft>(assetPath(kind, key) + '/draft', { method: 'POST' });
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
  comparisonDocument(kind: AssetKind, key: string, document: JsonObject, signal?: AbortSignal) {
    return request<JsonObject>(assetPath(kind, key) + '/comparison-documents', {
      method: 'POST', body: JSON.stringify({ document }),
    }, signal);
  },
  history(kind: AssetKind, key: string, signal?: AbortSignal) {
    return request<PublicationHistory>(assetPath(kind, key) + '/versions', {}, signal);
  },
  version(kind: AssetKind, key: string, versionId: string, signal?: AbortSignal) {
    return request<RetainedVersion>(assetPath(kind, key) + '/versions/' + encodeURIComponent(versionId), {}, signal);
  },
  publish(kind: AssetKind, key: string, plan: PublicationPlan, expectedServingDigest: string) {
    return request<PublicationResult>(assetPath(kind, key) + '/publications', {
      method: 'POST',
      body: JSON.stringify({ expectedServingDigest, candidate: plan.candidate, target: plan.target }),
    });
  },
  rollback(kind: AssetKind, key: string, target: PublicationTarget, expectedServingDigest: string) {
    return request<PublicationResult>(assetPath(kind, key) + '/rollbacks', {
      method: 'POST',
      body: JSON.stringify({ expectedServingDigest, target }),
    });
  },
  publicationCheck(
    kind: AssetKind,
    key: string,
    expectedRevision: number,
    target: PublicationTarget,
  ) {
    return request<PublicationCheck>(assetPath(kind, key) + '/publication-checks', {
      method: 'POST', body: JSON.stringify({ expectedRevision, target }),
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

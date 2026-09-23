export type JsonPatchOperation = {
  op: 'add' | 'replace' | 'remove';
  path: string;
  value?: unknown;
};

export type FormPatchIssue = {
  path?: string;
  message: string;
};

export interface AuthoringFormAdapter<TForm> {
  formKey: string;
  entityId: string;
  revision: number;
  schema: Record<string, unknown>;
  allowedPaths: readonly string[];
  isPathAllowed?: (path: string) => boolean;
  snapshot: () => TForm;
  normalize: (value: unknown) => TForm;
  validateOperation: (operation: JsonPatchOperation) => FormPatchIssue[];
  describePath: (path: string) => { label: string; section?: string };
  apply: (next: TForm) => void;
}

export interface FormPatchProposal {
  formKey: string;
  entityId: string;
  baseRevision: number;
  baseFingerprint: string;
  operations: JsonPatchOperation[];
  summary?: string;
}

export interface FormPatchBaseline<TForm> {
  formKey: string;
  entityId: string;
  revision: number;
  fingerprint: string;
  snapshot: TForm;
}

export type FormPatchConflictChoice = 'user' | 'ai';

export interface FormPatchReviewChange {
  id: string;
  path: string;
  label: string;
  section: string;
  status: 'safe' | 'conflict';
  operation: JsonPatchOperation;
  baseValue: unknown;
  currentValue: unknown;
  aiValue: unknown;
}

export interface FormPatchReview<TForm> {
  proposal: FormPatchProposal;
  baseline: FormPatchBaseline<TForm>;
  changes: FormPatchReviewChange[];
}

const allowedOperations = new Set(['add', 'replace', 'remove']);
const forbiddenPointerSegments = new Set(['__proto__', 'prototype', 'constructor']);

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function deepClone<T>(value: T): T {
  if (value === undefined) return value;
  return JSON.parse(JSON.stringify(value)) as T;
}

function stableValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stableValue);
  if (!isRecord(value)) return value;
  return Object.keys(value)
    ?.sort()
    ?.reduce?.<Record<string, unknown>>((result, key) => {
      result[key] = stableValue(value[key]);
      return result;
    }, {});
}

function equals(left: unknown, right: unknown): boolean {
  return JSON.stringify(stableValue(left)) === JSON.stringify(stableValue(right));
}

function pointerTokens(path: string): string[] {
  if (!path.startsWith('/') || path === '/') {
    throw new Error(`表单修改 path 必须是非根节点 JSON Pointer：${path || '(empty)'}`);
  }
  const tokens = path
    ?.slice(1)
    ?.split?.('/')
    ?.map?.((token) => token?.replace(/~1/g, '/')?.replace?.(/~0/g, '~'));
  const forbidden = tokens.find((token) => forbiddenPointerSegments.has(token));
  if (forbidden) throw new Error(`表单修改 path 包含禁止字段：${forbidden}`);
  return tokens;
}

function valueAtPath(root: unknown, path: string): unknown {
  return pointerTokens(path)?.reduce?.<unknown>((value, token) => {
    if (Array.isArray(value)) {
      const index = Number(token);
      return Number.isInteger(index) ? value[index] : undefined;
    }
    return isRecord(value) ? value[token] : undefined;
  }, root);
}

function applyOperation<TForm>(draft: TForm, operation: JsonPatchOperation): TForm {
  const next = deepClone(draft) as unknown;
  const tokens = pointerTokens(operation.path);
  let parent = next;
  tokens?.slice(0, -1)?.forEach?.((token) => {
    if (Array.isArray(parent)) {
      const index = Number(token);
      if (!Number.isInteger(index) || parent[index] === undefined) {
        throw new Error(`表单修改目标不存在：${operation.path}`);
      }
      parent = parent[index];
      return;
    }
    if (!isRecord(parent)) throw new Error(`表单修改父节点不是对象：${operation.path}`);
    if (!isRecord(parent[token]) && !Array.isArray(parent[token])) parent[token] = {};
    parent = parent[token];
  });
  const leaf = tokens[tokens.length - 1];
  if (Array.isArray(parent)) {
    const index = leaf === '-' ? parent.length : Number(leaf);
    if (!Number.isInteger(index)) throw new Error(`表单数组索引非法：${operation.path}`);
    if (operation.op === 'remove') parent.splice(index, 1);
    else if (operation.op === 'add') parent.splice(index, 0, deepClone(operation.value));
    else parent[index] = deepClone(operation.value);
    return next as TForm;
  }
  if (!isRecord(parent)) throw new Error(`表单修改父节点不是对象：${operation.path}`);
  if (operation.op === 'remove') delete parent[leaf];
  else parent[leaf] = deepClone(operation.value);
  return next as TForm;
}

export function authoringFormFingerprint(value: unknown): string {
  const text = JSON.stringify(stableValue(value));
  let hash = 0x811c9dc5;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return `fnv1a32:${(hash >>> 0).toString(16).padStart(8, '0')}`;
}

export class AuthoringFormAdapterRegistry {
  private readonly adapters = new Map<string, AuthoringFormAdapter<unknown>>();

  register<TForm>(adapter: AuthoringFormAdapter<TForm>): this {
    if (this.adapters.has(adapter.formKey)) {
      throw new Error(`Authoring formKey 重复注册：${adapter.formKey}`);
    }
    this.adapters.set(adapter.formKey, adapter as AuthoringFormAdapter<unknown>);
    return this;
  }

  resolve<TForm>(formKey: string): AuthoringFormAdapter<TForm> {
    const adapter = this.adapters.get(formKey);
    if (!adapter) throw new Error(`未注册的 Authoring formKey：${formKey}`);
    return adapter as AuthoringFormAdapter<TForm>;
  }
}

export function captureFormPatchBaseline<TForm>(
  adapter: AuthoringFormAdapter<TForm>,
): FormPatchBaseline<TForm> {
  const snapshot = adapter.normalize(adapter.snapshot());
  return {
    formKey: adapter.formKey,
    entityId: adapter.entityId,
    revision: adapter.revision,
    fingerprint: authoringFormFingerprint(snapshot),
    snapshot: deepClone(snapshot),
  };
}

export function resolveFormPatchBaseline<TForm>(
  adapter: AuthoringFormAdapter<TForm>,
  baselines: ReadonlyMap<string, FormPatchBaseline<TForm>>,
  proposal: FormPatchProposal,
): FormPatchBaseline<TForm> | null {
  const recordedBaseline = baselines.get(proposal.baseFingerprint);
  if (recordedBaseline) return recordedBaseline;

  const currentBaseline = captureFormPatchBaseline(adapter);
  if (
    currentBaseline.formKey !== proposal.formKey ||
    currentBaseline.entityId !== proposal.entityId ||
    currentBaseline.revision !== proposal.baseRevision ||
    currentBaseline.fingerprint !== proposal.baseFingerprint
  ) {
    return null;
  }
  return currentBaseline;
}

function normalizedFormFingerprint(value: unknown): string {
  const fingerprint = String(value || '');
  return /^[0-9a-f]{8}$/i.test(fingerprint) ? `fnv1a32:${fingerprint.toLowerCase()}` : fingerprint;
}

export function formPatchProposalOf(value: unknown): FormPatchProposal | null {
  if (!isRecord(value)) return null;
  const snapshotPaths = Array.isArray(value.changedPaths)
    ? value.changedPaths?.filter?.(
        (path): path is string => typeof path === 'string' && path.startsWith('/'),
      )
    : [];
  const operationValues = Array.isArray(value.operations)
    ? value.operations
    : isRecord(value.draft)
    ? snapshotPaths.length
      ? snapshotPaths.map((path) => ({
          op: 'replace',
          path,
          value: valueAtPath(value.draft, path),
        }))
      : Object.entries(value.draft).map(([key, draftValue]) => ({
          op: 'replace',
          path: `/${key?.replace(/~/g, '~0')?.replace?.(/\//g, '~1')}`,
          value: draftValue,
        }))
    : [];
  const operations = operationValues.map((item) => {
    if (!isRecord(item)) return null;
    const op = String(item.op || '') as JsonPatchOperation['op'];
    const path = String(item.path || '');
    if (!allowedOperations.has(op) || !path) return null;
    return { op, path, ...(op === 'remove' ? {} : { value: item.value }) };
  });
  if (!operations.length || operations.some((operation) => !operation)) return null;
  const baseRevision = Number(value.baseRevision);
  const proposal: FormPatchProposal = {
    formKey: String(value.formKey || ''),
    entityId: String(value.entityId || ''),
    baseRevision,
    baseFingerprint: normalizedFormFingerprint(value.baseFingerprint || value.baseDraftFingerprint),
    operations: operations as JsonPatchOperation[],
    summary: String(value.summary || '').trim() || undefined,
  };
  if (
    !proposal.formKey ||
    !proposal.entityId ||
    !Number.isSafeInteger(baseRevision) ||
    baseRevision <= 0 ||
    !proposal.baseFingerprint
  )
    return null;
  return proposal;
}

export function buildFormPatchReview<TForm>(
  adapter: AuthoringFormAdapter<TForm>,
  baseline: FormPatchBaseline<TForm>,
  currentDraft: TForm,
  proposal: FormPatchProposal,
): FormPatchReview<TForm> {
  if (proposal.formKey !== adapter.formKey || proposal.formKey !== baseline.formKey) {
    throw new Error('AI 修改建议与当前表单类型不匹配');
  }
  if (proposal.entityId !== adapter.entityId || proposal.entityId !== baseline.entityId) {
    throw new Error('AI 修改建议与当前编辑对象不匹配');
  }
  if (
    proposal.baseRevision !== baseline.revision ||
    proposal.baseFingerprint !== baseline.fingerprint ||
    authoringFormFingerprint(baseline.snapshot) !== baseline.fingerprint
  ) {
    throw new Error('AI 修改建议的 revision 或 fingerprint 已过期');
  }
  const duplicatePaths = new Set<string>();
  let aiDraft = deepClone(baseline.snapshot);
  proposal.operations?.forEach?.((operation) => {
    if (duplicatePaths.has(operation.path))
      throw new Error(`AI 重复修改同一字段：${operation.path}`);
    duplicatePaths.add(operation.path);
    if (
      !adapter.allowedPaths.includes(operation.path) &&
      !adapter.isPathAllowed?.(operation.path)
    ) {
      throw new Error(`AI 修改字段不在当前表单允许范围：${operation.path}`);
    }
    const issues = adapter.validateOperation(operation);
    if (issues.length) throw new Error(issues?.map((issue) => issue.message)?.join?.('；'));
    aiDraft = adapter.normalize(applyOperation(aiDraft, operation));
  });
  const changes = proposal?.operations
    ?.map?.<FormPatchReviewChange | null>((operation) => {
      const baseValue = valueAtPath(baseline.snapshot, operation.path);
      const currentValue = valueAtPath(currentDraft, operation.path);
      const aiValue = valueAtPath(aiDraft, operation.path);
      if (equals(currentValue, aiValue)) return null;
      const description = adapter.describePath(operation.path);
      return {
        id: operation.path,
        path: operation.path,
        label: description.label,
        section: description.section || '表单字段',
        status: equals(baseValue, currentValue) ? 'safe' : 'conflict',
        operation: {
          ...operation,
          ...(operation.op === 'remove' ? {} : { value: deepClone(aiValue) }),
        },
        baseValue: deepClone(baseValue),
        currentValue: deepClone(currentValue),
        aiValue: deepClone(aiValue),
      };
    })
    ?.filter?.((change): change is FormPatchReviewChange => Boolean(change));
  return { proposal, baseline, changes };
}

export function applyFormPatchReview<TForm>(
  adapter: AuthoringFormAdapter<TForm>,
  review: FormPatchReview<TForm>,
  selectedChangeIds: Set<string>,
  conflictChoices: Record<string, FormPatchConflictChoice>,
): TForm {
  let next = adapter.normalize(adapter.snapshot());
  review.changes?.forEach?.((change) => {
    const useAi =
      change.status === 'conflict'
        ? conflictChoices[change.id] === 'ai'
        : selectedChangeIds.has(change.id);
    if (useAi) next = adapter.normalize(applyOperation(next, change.operation));
  });
  return next;
}

import type { CapabilityActionDraftData } from './api';

export type CapabilityAuthoringStage =
  | 'basic'
  | 'contract'
  | 'binding'
  | 'components'
  | 'validation'
  | 'publish';

export type CapabilityDraftConflictChoice = 'user' | 'ai';

type DraftPathToken =
  | { kind: 'property'; key: string }
  | { kind: 'item'; collectionPath: string; identity: string };

export interface CapabilityDraftReviewChange {
  id: string;
  path: string;
  label: string;
  stage: CapabilityAuthoringStage;
  status: 'safe' | 'conflict';
  baseValue: unknown;
  currentValue: unknown;
  aiValue: unknown;
  tokens: DraftPathToken[];
}

const stageLabels: Record<CapabilityAuthoringStage, string> = {
  basic: '基础信息',
  contract: '参数契约',
  binding: '执行绑定',
  components: '包装组件',
  validation: '校验',
  publish: '发布',
};

const systemOwnedFields = new Set([
  'technicalOutputSchema',
  'observedType',
  'modelSummaryTemplate',
  'interaction',
  'requiredReviews',
]);

const fieldLabels: Record<string, string> = {
  actionCode: 'actionCode',
  nameCn: '中文名',
  businessDomain: '业务域',
  description: '说明',
  technicalOwner: '技术负责人',
  sourceType: '导入方式',
  inputFields: '入参字段',
  inputExampleJson: '入参 Demo JSON',
  keyOutputFields: '关键出参字段',
  responseDemoJson: '响应 Demo JSON',
  technicalOutputSchema: '技术输出 Schema',
  observedType: '识别类型',
  toolField: '字段名',
  type: '类型',
  businessMeaning: '业务含义',
  unit: '单位',
  allowedValues: '可选值（枚举）',
  source: '来源',
  required: '是否必填',
  constantValue: '常量值',
  systemVariable: '系统变量',
  valueMapping: '系统变量值映射',
  examples: '字段示例',
  bindingType: '绑定类型',
  methodName: '方法',
  serviceName: '完整 RPC 服务名',
  targetKey: '业务服务配置键',
  descriptorSetBase64: '协议描述文件',
  contextField: '身份上下文字段',
  maxResponseBytes: '最大响应字节',
  timeoutMs: '超时毫秒',
  idempotency: '幂等策略',
  requestMappings: '请求字段映射',
  contextMappings: '上下文 / 身份注入',
  constantMappings: '固定字段',
  errorMappings: '错误映射',
  presentationComponents: '包装组件',
  sideEffectLevel: '副作用',

  publishBlockers: '发布阻塞项',
};

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

export function capabilityDraftFingerprint(value: unknown): string {
  const text = JSON.stringify(stableValue(value));
  let hash = 0x811c9dc5;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, '0');
}

function equals(left: unknown, right: unknown): boolean {
  return JSON.stringify(stableValue(left)) === JSON.stringify(stableValue(right));
}

function propertyKeys(tokens: DraftPathToken[]): string[] {
  return tokens
    ?.filter(
      (token): token is Extract<DraftPathToken, { kind: 'property' }> => token.kind === 'property',
    )
    ?.map?.((token) => token.key);
}

function pointerOf(tokens: DraftPathToken[]): string {
  return tokens
    ?.map((token) =>
      token.kind === 'property'
        ? `/${token?.key?.replace?.(/~/g, '~0')?.replace?.(/\//g, '~1')}`
        : `/@${encodeURIComponent(token.identity)}`,
    )
    ?.join?.('');
}

function collectionPathOf(tokens: DraftPathToken[]): string {
  return `/${propertyKeys(tokens)?.join?.('/')}`;
}

function arrayIdentity(collectionPath: string, item: unknown, index: number): string | undefined {
  if (!isRecord(item)) return undefined;
  if (collectionPath === '/modelContract/inputFields') {
    const identity = String(item.toolField || '').trim();
    return identity || `index-${index}`;
  }
  if (collectionPath === '/resultContract/keyOutputFields') {
    const identity = String(item.path || '').trim();
    return identity || `index-${index}`;
  }
  if (collectionPath === '/resultContract/presentationComponents') {
    const componentName = String(item.componentName || '').trim();
    const usage = String(item.usage || '').trim();
    return componentName ? `${componentName}::${usage}` : `index-${index}`;
  }
  return undefined;
}

function keyedArray(value: unknown[], collectionPath: string): Map<string, unknown> | null {
  const entries = value.map(
    (item, index) => [arrayIdentity(collectionPath, item, index), item] as const,
  );
  if (entries.some(([identity]) => !identity)) return null;
  const result = new Map<string, unknown>();
  for (const [identity, item] of entries) {
    if (!identity || result.has(identity)) return null;
    result.set(identity, item);
  }
  return result;
}

function stageOf(tokens: DraftPathToken[]): CapabilityAuthoringStage {
  const keys = propertyKeys(tokens);
  if (keys?.[0] === 'basicInfo' || keys?.[0] === 'apiSource') return 'basic';
  if (keys?.[0] === 'modelContract') return 'contract';
  if (keys?.[0] === 'executionBinding') return 'binding';
  if (keys?.[0] === 'resultContract' && keys?.[1] === 'presentationComponents') return 'components';
  if (
    keys?.[0] === 'resultContract' &&
    ['keyOutputFields', 'responseDemoJson', 'technicalOutputSchema'].includes(keys[1])
  ) {
    return 'contract';
  }
  return 'validation';
}

function labelOf(tokens: DraftPathToken[]): string {
  const labels: string[] = [];
  tokens.forEach((token) => {
    if (token.kind === 'item') {
      labels.push(token?.identity?.split?.('::')?.[0]);
      return;
    }
    if (
      [
        'basicInfo',
        'apiSource',
        'modelContract',
        'executionBinding',
        'resultContract',
        'governance',
        'target',
      ].includes(token.key)
    )
      return;
    labels.push(fieldLabels[token.key] || token.key);
  });
  return labels.join(' · ') || stageLabels[stageOf(tokens)];
}

function addAtomicChange(
  baseValue: unknown,
  currentValue: unknown,
  aiValue: unknown,
  tokens: DraftPathToken[],
  changes: CapabilityDraftReviewChange[],
) {
  if (equals(baseValue, aiValue) || equals(currentValue, aiValue)) return;
  const path = pointerOf(tokens);
  changes.push({
    id: path,
    path,
    label: labelOf(tokens),
    stage: stageOf(tokens),
    status: equals(baseValue, currentValue) ? 'safe' : 'conflict',
    baseValue: deepClone(baseValue),
    currentValue: deepClone(currentValue),
    aiValue: deepClone(aiValue),
    tokens,
  });
}

function collectChanges(
  baseValue: unknown,
  currentValue: unknown,
  aiValue: unknown,
  tokens: DraftPathToken[],
  changes: CapabilityDraftReviewChange[],
) {
  if (equals(baseValue, aiValue)) return;
  if (baseValue === undefined || aiValue === undefined) {
    addAtomicChange(baseValue, currentValue, aiValue, tokens, changes);
    return;
  }
  if (Array.isArray(baseValue) && Array.isArray(currentValue) && Array.isArray(aiValue)) {
    const collectionPath = collectionPathOf(tokens);
    const baseMap = keyedArray(baseValue, collectionPath);
    const currentMap = keyedArray(currentValue, collectionPath);
    const aiMap = keyedArray(aiValue, collectionPath);
    if (!baseMap || !currentMap || !aiMap) {
      addAtomicChange(baseValue, currentValue, aiValue, tokens, changes);
      return;
    }
    const identities = Array.from(
      new Set([...baseMap.keys(), ...currentMap.keys(), ...aiMap.keys()]),
    ).sort();
    identities.forEach((identity) => {
      const itemToken: DraftPathToken = { kind: 'item', collectionPath, identity };
      collectChanges(
        baseMap.get(identity),
        currentMap.get(identity),
        aiMap.get(identity),
        [...tokens, itemToken],
        changes,
      );
    });
    return;
  }
  if (isRecord(baseValue) && isRecord(currentValue) && isRecord(aiValue)) {
    const keys = Array.from(
      new Set([...Object.keys(baseValue), ...Object.keys(currentValue), ...Object.keys(aiValue)]),
    ).sort();
    keys
      ?.filter((key) => !systemOwnedFields.has(key))
      ?.forEach?.((key) =>
        collectChanges(
          baseValue[key],
          currentValue[key],
          aiValue[key],
          [...tokens, { kind: 'property', key }],
          changes,
        ),
      );
    return;
  }
  addAtomicChange(baseValue, currentValue, aiValue, tokens, changes);
}

export function buildCapabilityDraftReview(
  baseDraft: CapabilityActionDraftData,
  currentDraft: CapabilityActionDraftData,
  aiDraft: CapabilityActionDraftData,
): CapabilityDraftReviewChange[] {
  const changes: CapabilityDraftReviewChange[] = [];
  collectChanges(baseDraft, currentDraft, aiDraft, [], changes);
  return changes.sort((left, right) => {
    const stageOrder: CapabilityAuthoringStage[] = [
      'basic',
      'contract',
      'binding',
      'components',
      'validation',
      'publish',
    ];
    return (
      stageOrder.indexOf(left.stage) - stageOrder.indexOf(right.stage) ||
      left.path?.localeCompare?.(right.path)
    );
  });
}

function setAtPath(target: Record<string, unknown>, tokens: DraftPathToken[], value: unknown) {
  let cursor: unknown = target;
  tokens.forEach((token, index) => {
    const isLast = index === tokens.length - 1;
    if (token.kind === 'property') {
      if (!isRecord(cursor)) throw new Error(`AI 修改路径父节点不是对象: ${pointerOf(tokens)}`);
      if (isLast) {
        if (value === undefined) delete cursor[token.key];
        else cursor[token.key] = deepClone(value);
        return;
      }
      if (!(token.key in cursor)) {
        cursor[token.key] = tokens[index + 1]?.kind === 'item' ? [] : {};
      }
      cursor = cursor[token.key];
      return;
    }
    if (!Array.isArray(cursor)) throw new Error(`AI 修改路径父节点不是数组: ${pointerOf(tokens)}`);
    const itemIndex = cursor.findIndex(
      (item, itemPosition) =>
        arrayIdentity(token.collectionPath, item, itemPosition) === token.identity,
    );
    if (isLast) {
      if (value === undefined) {
        if (itemIndex >= 0) cursor.splice(itemIndex, 1);
      } else if (itemIndex >= 0) {
        cursor[itemIndex] = deepClone(value);
      } else {
        cursor.push(deepClone(value));
      }
      return;
    }
    if (itemIndex < 0) throw new Error(`AI 修改目标已不存在: ${token.identity}`);
    cursor = cursor[itemIndex];
  });
}

export function applyCapabilityDraftReview(
  currentDraft: CapabilityActionDraftData,
  changes: CapabilityDraftReviewChange[],
  selectedChangeIds: Set<string>,
  conflictChoices: Record<string, CapabilityDraftConflictChoice>,
): CapabilityActionDraftData {
  const next = deepClone(currentDraft) as unknown as Record<string, unknown>;
  changes.forEach((change) => {
    if (change.status === 'conflict') {
      if (conflictChoices[change.id] !== 'ai') return;
    } else if (!selectedChangeIds.has(change.id)) {
      return;
    }
    setAtPath(next, change.tokens, change.aiValue);
  });
  return next as unknown as CapabilityActionDraftData;
}

export function capabilityAuthoringStageLabel(stage: CapabilityAuthoringStage): string {
  return stageLabels[stage];
}

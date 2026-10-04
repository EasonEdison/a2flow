import type { A2uiApplicationDraft, A2uiMessage } from './a2uiApplicationContracts';
import { resolveA2uiShowMessages } from './a2uiApplicationEditorModel';

export const DIGITAL_EMPLOYEE_CATALOG_ID = 'a2flow.digital-employee.pc.v1';
export const OFFICIAL_BASIC_CATALOG_ID =
  'https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json';

export interface A2uiLocalPreviewResult {
  messages: A2uiMessage[];
  errors: string[];
  requiredLoadFixtureIds: string[];
}

export interface A2uiLocalActionEvent {
  name: string;
  surfaceId: string;
  sourceComponentId: string;
  context?: Record<string, unknown>;
}

export interface A2uiLocalActionSummary {
  eventName: string;
  capabilityActionCode?: string;
  arguments?: Record<string, unknown>;
  errors: string[];
}

function pointerSegments(path: string): string[] | undefined {
  if (!path.startsWith('/')) return undefined;
  if (path === '/') return [];
  return path
    .slice(1)
    .split('/')
    .map((segment) => segment.replace(/~1/g, '/').replace(/~0/g, '~'));
}

function readPointer(root: unknown, path: string): { found: boolean; value?: unknown } {
  const segments = pointerSegments(path);
  if (!segments) return { found: false };
  let cursor = root;
  for (const segment of segments) {
    if (!cursor || typeof cursor !== 'object' || Array.isArray(cursor) || !(segment in cursor)) {
      return { found: false };
    }
    cursor = (cursor as Record<string, unknown>)[segment];
  }
  return { found: true, value: cursor };
}

function writePointer(root: Record<string, unknown>, path: string, value: unknown): boolean {
  const segments = pointerSegments(path);
  if (!segments?.length) return false;
  let cursor = root;
  for (const segment of segments.slice(0, -1)) {
    const existing = cursor[segment];
    if (existing !== undefined && (!existing || typeof existing !== 'object' || Array.isArray(existing))) {
      return false;
    }
    if (!existing) cursor[segment] = {};
    cursor = cursor[segment] as Record<string, unknown>;
  }
  cursor[segments[segments.length - 1]] = JSON.parse(JSON.stringify(value)) as unknown;
  return true;
}

export function buildA2uiApplicationLocalPreview(
  application: A2uiApplicationDraft,
  params: Record<string, unknown>,
): A2uiLocalPreviewResult {
  const requiredLoadFixtureIds = application.loadBindings.map((binding) => binding.bindingId);
  if (requiredLoadFixtureIds.length) {
    return {
      messages: [],
      errors: [
        `当前 Application 依赖 LoadBinding 样例结果：${requiredLoadFixtureIds.join(', ')}。本地预览不会调用 Capability，也不会伪造返回值。`,
      ],
      requiredLoadFixtureIds,
    };
  }
  const resolved = resolveA2uiShowMessages(application.showTemplate, params);
  return {
    messages: resolved.issues.length ? [] : resolved.messages,
    errors: resolved.issues.map(
      (issue) => `InputBinding #${issue.bindingIndex + 1} ${issue.code}: ${issue.path}`,
    ),
    requiredLoadFixtureIds,
  };
}

export function buildA2uiSampleParams(
  schema: Record<string, unknown>,
): { params: Record<string, unknown>; generatedFields: string[]; missingRequired: string[] } {
  const properties =
    schema.properties && typeof schema.properties === 'object' && !Array.isArray(schema.properties)
      ? (schema.properties as Record<string, unknown>)
      : {};
  const required = new Set(Array.isArray(schema.required) ? schema.required.filter((item): item is string => typeof item === 'string') : []);
  const params: Record<string, unknown> = {};
  const generatedFields: string[] = [];
  Object.entries(properties).forEach(([name, raw]) => {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return;
    const property = raw as Record<string, unknown>;
    if (Array.isArray(property.examples) && property.examples.length) params[name] = property.examples[0];
    else if (property.default !== undefined) params[name] = property.default;
    else if (required.has(name)) {
      const generated = sampleValue(property, name);
      if (generated.found) {
        params[name] = generated.value;
        generatedFields.push(name);
      }
    }
  });
  return {
    params,
    generatedFields,
    missingRequired: [...required].filter((name) => !(name in params)),
  };
}

const LOCAL_STRING_SAMPLES: Record<string, string> = {
  prompt: '请选择要保留的阅读要点',
  projectId: 'local-project-demo',
  artifactId: 'local-artifact-demo',
  id: 'local-item-demo',
  claim: '清晰的结构能帮助读者快速理解重点',
  evidenceQuote: '先给结论，再补充关键依据。',
  evidenceLocator: '本地样例第 1 段',
  explanation: '此内容仅用于验证 Application 的本地组件树与交互。',
  label: '保留这个阅读要点',
  value: 'point-demo-1',
  title: '本地预览选题',
  angle: '从读者决策成本切入',
  audience: '需要快速形成内容框架的创作者',
  rationale: '用于验证选题编辑与确认事件参数。',
  draftTitle: '本地预览稿件',
  savedTitle: '本地预览稿件',
  draftMarkdown: '# 本地预览稿件\n\n这是用于验证编辑与 Markdown 预览的样例内容。',
  savedMarkdown: '# 本地预览稿件\n\n这是用于验证编辑与 Markdown 预览的样例内容。',
  savedArtifactId: 'local-manuscript-demo',
  kind: 'ARTIFACT',
  referenceKind: 'ARTIFACT',
  referenceId: 'local-source-demo',
};

function sampleValue(
  schema: Record<string, unknown>,
  fieldName: string,
): { found: boolean; value?: unknown } {
  if (Array.isArray(schema.enum) && schema.enum.length) return { found: true, value: schema.enum[0] };
  if (schema.type === 'string') {
    return { found: true, value: LOCAL_STRING_SAMPLES[fieldName] || `local-${fieldName}-demo` };
  }
  if (schema.type === 'integer' || schema.type === 'number') return { found: true, value: 1 };
  if (schema.type === 'boolean') return { found: true, value: false };
  if (schema.type === 'array') {
    if (!schema.items || typeof schema.items !== 'object' || Array.isArray(schema.items)) {
      return { found: true, value: [] };
    }
    const item = sampleValue(schema.items as Record<string, unknown>, fieldName.replace(/s$/, ''));
    if (item.found && item.value && typeof item.value === 'object' && !Array.isArray(item.value)) {
      if (fieldName === 'points' && 'id' in item.value) item.value.id = 'point-demo-1';
      if (fieldName === 'topics' && 'id' in item.value) item.value.id = 'topic-demo-1';
    }
    return { found: true, value: item.found ? [item.value] : [] };
  }
  if (schema.type === 'object') {
    const nestedProperties =
      schema.properties && typeof schema.properties === 'object' && !Array.isArray(schema.properties)
        ? (schema.properties as Record<string, unknown>)
        : {};
    const nestedRequired = new Set(
      Array.isArray(schema.required)
        ? schema.required.filter((item): item is string => typeof item === 'string')
        : Object.keys(nestedProperties),
    );
    const value: Record<string, unknown> = {};
    for (const [name, raw] of Object.entries(nestedProperties)) {
      if (!nestedRequired.has(name) || !raw || typeof raw !== 'object' || Array.isArray(raw)) continue;
      const nested = sampleValue(raw as Record<string, unknown>, name);
      if (nested.found) value[name] = nested.value;
    }
    return { found: true, value };
  }
  return { found: false };
}

export function buildA2uiLocalActionSummary(
  application: A2uiApplicationDraft,
  params: Record<string, unknown>,
  event: A2uiLocalActionEvent,
): A2uiLocalActionSummary {
  const binding = application.actionBindings.find(
    (item) =>
      item.actionCode === event.name &&
      item.surfaceId === event.surfaceId &&
      item.sourceComponentId === event.sourceComponentId,
  );
  if (!binding) return { eventName: event.name, errors: ['当前事件没有匹配的 ActionBinding。'] };
  const argumentsValue: Record<string, unknown> = {};
  const errors: string[] = [];
  binding.requestMappings.forEach((mapping) => {
    const source =
      mapping.source === 'ACTION_CONTEXT'
        ? readPointer(event.context || {}, mapping.sourcePath)
        : mapping.source === 'APP_PARAMS'
        ? readPointer(params, mapping.sourcePath)
        : mapping.source === 'CONSTANT'
        ? { found: mapping.constantValue !== undefined, value: mapping.constantValue }
        : { found: false };
    if (!source.found) {
      errors.push(`${mapping.source} ${mapping.sourcePath} 需要显式本地样例，未生成业务参数。`);
      return;
    }
    if (!writePointer(argumentsValue, mapping.targetPath, source.value)) {
      errors.push(`目标参数路径无效：${mapping.targetPath}`);
    }
  });
  return {
    eventName: event.name,
    capabilityActionCode: binding.capability.actionCode,
    arguments: errors.length ? undefined : argumentsValue,
    errors,
  };
}

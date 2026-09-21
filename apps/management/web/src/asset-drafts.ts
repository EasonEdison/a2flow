import type { AssetKind, JsonObject } from './contracts';

export interface DraftStructureIssue {
  path: string;
  message: string;
}

export type DraftParseResult<TDocument extends JsonObject> =
  | { ok: true; document: TDocument }
  | { ok: false; issue: DraftStructureIssue };

export interface SkillMetadata extends JsonObject {
  name: string;
  description: string;
}

export interface SkillDraftDocument extends JsonObject {
  metadata: SkillMetadata;
  skillMd: string;
  requiredToolNames: string[];
  abilityBindings: string[];
  applicationBindings: string[];
  resources: unknown[];
}

export interface AbilityInputBinding extends JsonObject {
  targetPath: string;
  source: string;
  sourcePath: string;
}

export interface AbilityCredentialRequirement extends JsonObject {
  slotId: string;
  required: boolean;
}

export interface AbilityDraftDocument extends JsonObject {
  abilityKey: string;
  adapterOperationRef: string;
  defaultSuccessPolicyRef: string;
  inputBindings: AbilityInputBinding[];
  credentialRequirements: AbilityCredentialRequirement[];
  modelArgumentSchema: JsonObject;
  resolvedInputSchema: JsonObject;
  outputSchema: JsonObject;
  resultInterpretationPolicies: unknown[];
}

export interface ComponentCatalogDefinition extends JsonObject {
  catalogKey: string;
  protocolProfileRef: string;
  components: string[];
}

export interface ComponentDraftDocument extends JsonObject {
  definition: ComponentCatalogDefinition;
  dependencies: unknown[];
}

export interface ApplicationDependency extends JsonObject {
  kind: 'ABILITY' | 'COMPONENT';
  key: string;
}

export interface ApplicationDraftDocument extends JsonObject {
  definition: JsonObject;
  dependencies: ApplicationDependency[];
}

export interface WorkflowNode extends JsonObject {
  nodeId: string;
  skillKey: string;
}

export interface WorkflowDraftDocument extends JsonObject {
  definitionKey: string;
  topology: string;
  nodes: WorkflowNode[];
}

function fail<TDocument extends JsonObject>(path: string, message: string): DraftParseResult<TDocument> {
  return { ok: false, issue: { path, message } };
}

function isRecord(value: unknown): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string');
}

function stringField(value: JsonObject, key: string): boolean {
  return typeof value[key] === 'string';
}

function recordArray(value: unknown, fields: readonly string[]): value is JsonObject[] {
  return Array.isArray(value) && value.every((item) =>
    isRecord(item) && fields.every((field) => typeof item[field] === 'string'));
}

export function parseSkillDraft(document: JsonObject): DraftParseResult<SkillDraftDocument> {
  if (!isRecord(document.metadata)) return fail('/metadata', '基础信息必须是对象。');
  if (!stringField(document.metadata, 'name')) return fail('/metadata/name', '名称必须是字符串。');
  if (!stringField(document.metadata, 'description')) return fail('/metadata/description', '描述必须是字符串。');
  if (typeof document.skillMd !== 'string') return fail('/skillMd', 'SKILL.md 必须是文本。');
  if (!isStringArray(document.requiredToolNames)) return fail('/requiredToolNames', '平台派生的工具列表结构异常。');
  if (!isStringArray(document.abilityBindings)) return fail('/abilityBindings', '业务能力绑定必须是字符串数组。');
  if (!isStringArray(document.applicationBindings)) return fail('/applicationBindings', '渲染应用绑定必须是字符串数组。');
  if (!Array.isArray(document.resources)) return fail('/resources', '资源清单必须是数组。');
  return { ok: true, document: document as SkillDraftDocument };
}

export function parseAbilityDraft(document: JsonObject): DraftParseResult<AbilityDraftDocument> {
  for (const key of ['abilityKey', 'adapterOperationRef', 'defaultSuccessPolicyRef']) {
    if (!stringField(document, key)) return fail(`/${key}`, `${key} 必须是字符串。`);
  }
  if (!recordArray(document.inputBindings, ['targetPath', 'source', 'sourcePath'])) {
    return fail('/inputBindings', '输入绑定必须由 targetPath、source、sourcePath 字符串组成。');
  }
  if (!Array.isArray(document.credentialRequirements) || !document.credentialRequirements.every((item) =>
    isRecord(item) && typeof item.slotId === 'string' && typeof item.required === 'boolean')) {
    return fail('/credentialRequirements', '凭据声明必须包含 slotId 字符串和 required 布尔值。');
  }
  for (const key of ['modelArgumentSchema', 'resolvedInputSchema', 'outputSchema']) {
    if (!isRecord(document[key])) return fail(`/${key}`, `${key} 必须是对象。`);
  }
  if (!Array.isArray(document.resultInterpretationPolicies)) {
    return fail('/resultInterpretationPolicies', '结果解释策略必须是数组。');
  }
  return { ok: true, document: document as AbilityDraftDocument };
}

export function parseComponentDraft(document: JsonObject): DraftParseResult<ComponentDraftDocument> {
  if (!isRecord(document.definition)) return fail('/definition', '组件目录定义必须是对象。');
  for (const key of ['catalogKey', 'protocolProfileRef']) {
    if (!stringField(document.definition, key)) return fail(`/definition/${key}`, `${key} 必须是字符串。`);
  }
  if (!isStringArray(document.definition.components)) {
    return fail('/definition/components', '组件成员必须是字符串数组。');
  }
  if (!Array.isArray(document.dependencies)) return fail('/dependencies', '依赖必须是数组。');
  return { ok: true, document: document as ComponentDraftDocument };
}

export function parseApplicationDraft(document: JsonObject): DraftParseResult<ApplicationDraftDocument> {
  if (!isRecord(document.definition)) return fail('/definition', 'Application 定义必须是对象。');
  if (!Array.isArray(document.dependencies) || !document.dependencies.every((item) =>
    isRecord(item) && (item.kind === 'ABILITY' || item.kind === 'COMPONENT') && typeof item.key === 'string')) {
    return fail('/dependencies', '依赖必须包含 ABILITY 或 COMPONENT 类型以及字符串 key。');
  }
  return { ok: true, document: document as ApplicationDraftDocument };
}

export function parseWorkflowDraft(document: JsonObject): DraftParseResult<WorkflowDraftDocument> {
  if (!stringField(document, 'definitionKey')) return fail('/definitionKey', 'Workflow key 必须是字符串。');
  if (!stringField(document, 'topology')) return fail('/topology', '拓扑类型必须是字符串。');
  if (!recordArray(document.nodes, ['nodeId', 'skillKey'])) {
    return fail('/nodes', '节点必须包含 nodeId 和 skillKey 字符串。');
  }
  return { ok: true, document: document as WorkflowDraftDocument };
}

export function draftStructureIssue(kind: AssetKind, document: JsonObject): DraftStructureIssue | null {
  const parsed = kind === 'SKILL'
    ? parseSkillDraft(document)
    : kind === 'ABILITY'
      ? parseAbilityDraft(document)
      : kind === 'APPLICATION'
        ? parseApplicationDraft(document)
        : kind === 'WORKFLOW'
          ? parseWorkflowDraft(document)
          : parseComponentDraft(document);
  return parsed.ok ? null : parsed.issue;
}

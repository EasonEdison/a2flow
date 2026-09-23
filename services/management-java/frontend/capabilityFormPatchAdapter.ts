import type { CapabilityActionDraftData } from './api';
import type {
  AuthoringFormAdapter,
  FormPatchIssue,
  JsonPatchOperation,
} from './shared/authoringFormPatch';

export const CAPABILITY_ACTION_FORM_KEY = 'capability-center.action.v1';

const editableRoots = [
  '/basicInfo',
  '/supportedClients',
  '/clientVariants',
  '/governance',
] as const;
const supportedClientVariants = new Set(['PC', 'APP', 'COMMON']);
const clientTechnicalSections = new Set([
  'apiSource',
  'modelContract',
  'executionBinding',
  'resultContract',
]);
const forbiddenSegments = new Set([
  'technicalOutputSchema',
  'observedType',
  'modelSummaryTemplate',
  'interaction',
  'requiredReviews',
  'businessDomain',
  'capabilityDomain',
  'specialistIds',
]);
const sectionLabels: Record<string, string> = {
  basicInfo: '基础信息',
  supportedClients: '支持端',
  clientVariants: '端侧技术配置',
  apiSource: 'API 来源',
  modelContract: '参数契约',
  executionBinding: '执行绑定',
  resultContract: '结果契约',
  governance: '治理策略',
};

function pathTokens(path: string): string[] {
  return path
    ?.split('/')
    ?.slice?.(1)
    ?.map?.((token) => token?.replace(/~1/g, '/')?.replace?.(/~0/g, '~'));
}

function isPathAllowed(path: string): boolean {
  const tokens = pathTokens(path);
  if (
    !path.startsWith('/') ||
    path.endsWith('/') ||
    tokens.some((token) => forbiddenSegments.has(token))
  ) {
    return false;
  }
  if (path === '/supportedClients' || path === '/clientVariants') return true;
  if (
    path === '/basicInfo' ||
    path.startsWith('/basicInfo/') ||
    path === '/governance' ||
    path.startsWith('/governance/')
  )
    return true;
  if (tokens?.[0] !== 'clientVariants' || !supportedClientVariants.has(tokens?.[1])) return false;
  return tokens.length === 2 || clientTechnicalSections.has(tokens?.[2]);
}

function validateOperation(operation: JsonPatchOperation): FormPatchIssue[] {
  if (!isPathAllowed(operation.path)) {
    return [{ path: operation.path, message: `字段不允许由 AI 修改：${operation.path}` }];
  }
  return [];
}

function describePath(path: string): { label: string; section: string } {
  const tokens = pathTokens(path);
  const client =
    tokens?.[0] === 'clientVariants' && supportedClientVariants.has(tokens[1]) ? tokens?.[1] : '';
  const sectionKey = client ? tokens?.[2] : tokens?.[0];
  const section = sectionLabels[sectionKey] || sectionLabels[tokens[0]] || '能力表单';
  const field = tokens[tokens.length - 1] || tokens?.[0] || path;
  return {
    label: client ? `${client} · ${field}` : field,
    section,
  };
}

export function createCapabilityFormPatchAdapter(options: {
  draft: CapabilityActionDraftData;
  draftId: string;
  revision: number;
  normalize: (value: CapabilityActionDraftData) => CapabilityActionDraftData;
  apply: (next: CapabilityActionDraftData) => void;
}): AuthoringFormAdapter<CapabilityActionDraftData> {
  return {
    formKey: CAPABILITY_ACTION_FORM_KEY,
    entityId: `capability-draft:${options.draftId}`,
    revision: options.revision,
    schema: {
      $id: 'capabilityActionDraft.v1',
      type: 'object',
    },
    allowedPaths: editableRoots,
    isPathAllowed,
    snapshot: () => options.draft,
    normalize: (value) => options.normalize(value as CapabilityActionDraftData),
    validateOperation,
    describePath,
    apply: options.apply,
  };
}

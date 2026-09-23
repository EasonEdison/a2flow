import {
  buildA2uiContractPreview,
  type A2uiActionBinding,
  type A2uiApplicationDraft,
  type A2uiContractPreview,
  type A2uiLoadBinding,
  type A2uiMappingSource,
  type A2uiRequestMapping,
} from './a2uiApplicationContracts';
import { extractShowComponents } from './a2uiApplicationShowAst';

export interface A2uiPreviewActionContext {
  eventName: string;
  actionCode: string;
  sourceComponentId: string;
  surfaceId: string;
  actionPayload: '<untrusted-action-payload>';
  trustedContext: '<injected-by-runtime>';
}

export interface A2uiPreviewRequestMapping extends A2uiRequestMapping {
  previewValue: string;
}

export interface A2uiPreviewMappedRequest {
  actionCode: string;
  capabilityActionCode: string;
  mappings: A2uiPreviewRequestMapping[];
}

export interface A2uiPreviewCapabilityData {
  actionCode: string;
  capabilityActionCode: string;
  rootValue: '<sanitized-original-business-response>';
}

export interface A2uiPreviewCapabilityMeta {
  actionCode: string;
  capabilityActionCode: string;
  success: true;
  status: 'SUCCEEDED';
  error: null;
}

export interface A2uiExpectedFinalSurface {
  surfaceId: string;
  rootComponentId: string;
  componentCount: number;
  componentIds: string[];
  dataModel: Record<string, unknown>;
  deleted: boolean;
}

export interface A2uiDetailedContractPreview extends A2uiContractPreview {
  showInputBindings: A2uiRequestMapping[];
  loadBindings: A2uiLoadBinding[];
  actionContexts: A2uiPreviewActionContext[];
  redactedMappedRequests: A2uiPreviewMappedRequest[];
  capabilityDataFixtures: A2uiPreviewCapabilityData[];
  capabilityMetaFixtures: A2uiPreviewCapabilityMeta[];
  expectedFinalSurface: A2uiExpectedFinalSurface;
}

function previewValue(source: A2uiMappingSource): string {
  switch (source) {
    case 'ACTION_CONTEXT':
      return '<action-payload>';
    case 'TRUSTED_CONTEXT':
      return '<trusted-context-injected-by-runtime>';
    case 'CONSTANT':
      return '<redacted-constant>';
    case 'CAPABILITY_PREVIOUS_RESULT':
      return '<controlled-previous-result>';
    default:
      return '<unavailable>';
  }
}

function objectValue(value: unknown): Record<string, unknown> | undefined {
  return value && !Array.isArray(value) && typeof value === 'object'
    ? (value as Record<string, unknown>)
    : undefined;
}

function setJsonPointer(target: Record<string, unknown>, path: string, value: unknown): void {
  const segments = path
    ?.split('/')
    ?.slice?.(1)
    ?.map?.((item) => item?.replace(/~1/g, '/')?.replace?.(/~0/g, '~'));
  if (!segments.length || (segments.length === 1 && !segments[0])) {
    if (objectValue(value)) Object.assign(target, value);
    return;
  }
  let cursor = target;
  segments?.slice(0, -1)?.forEach?.((segment) => {
    const next = objectValue(cursor[segment]) || {};
    cursor[segment] = next;
    cursor = next;
  });
  cursor[segments[segments.length - 1] || ''] = value;
}

function expectedSurface(application: A2uiApplicationDraft): A2uiExpectedFinalSurface {
  const declaration = application.showTemplate?.surfaceDeclarations?.[0];
  const surfaceId = declaration?.surfaceId || '';
  const components = new Map<string, Record<string, unknown>>();
  extractShowComponents(application.showTemplate)
    ?.filter?.((item) => item.surfaceId === surfaceId)
    ?.forEach?.((item) => components.set(item.definition?.id, item.definition));
  const dataModel: Record<string, unknown> = {};
  let deleted = false;
  application.showTemplate?.messageTemplates?.forEach?.((message) => {
    const update = objectValue(message.updateDataModel);
    if (update?.surfaceId === surfaceId && typeof update.path === 'string') {
      setJsonPointer(dataModel, update.path, update.value);
    }
    const deletion = objectValue(message.deleteSurface);
    if (deletion?.surfaceId === surfaceId) deleted = true;
  });
  return {
    surfaceId,
    rootComponentId: declaration?.rootComponentId || '',
    componentCount: components.size,
    componentIds: [...components.keys()],
    dataModel,
    deleted,
  };
}

function previewMappings(binding: A2uiActionBinding): A2uiPreviewMappedRequest {
  return {
    actionCode: binding.actionCode,
    capabilityActionCode: binding.capability?.actionCode,
    mappings: binding.requestMappings?.map?.((mapping) => ({
      source: mapping.source,
      sourcePath: mapping.sourcePath,
      targetPath: mapping.targetPath,
      previewValue: previewValue(mapping.source),
    })),
  };
}

export function buildDetailedA2uiContractPreview(
  application: A2uiApplicationDraft,
): A2uiDetailedContractPreview {
  const base = buildA2uiContractPreview(application);
  return {
    ...base,
    showInputBindings: application.showTemplate?.inputBindings?.map?.((binding) => ({
      source: binding.source === 'APP_PARAMS' ? 'ACTION_CONTEXT' : binding.source,
      sourcePath: binding.sourcePath,
      targetPath: binding.targetPath,
      constantValue: binding.constantValue,
    })),
    loadBindings: application.loadBindings?.map?.((binding) => ({
      ...binding,
      capability: { ...binding.capability },
      requestMappings: binding.requestMappings?.map?.((mapping) => ({ ...mapping })),
      resultAdapters: [...binding.resultAdapters],
      failureResultAdapters: [...binding.failureResultAdapters],
    })),
    actionContexts: base.actionDeclarations?.map?.((declaration) => ({
      ...declaration,
      actionPayload: '<untrusted-action-payload>',
      trustedContext: '<injected-by-runtime>',
    })),
    redactedMappedRequests: base.actionBindings?.map?.(previewMappings),
    capabilityDataFixtures: base.actionBindings?.map?.((binding) => ({
      actionCode: binding.actionCode,
      capabilityActionCode: binding.capability?.actionCode,
      rootValue: '<sanitized-original-business-response>',
    })),
    capabilityMetaFixtures: base.actionBindings?.map?.((binding) => ({
      actionCode: binding.actionCode,
      capabilityActionCode: binding.capability?.actionCode,
      success: true,
      status: 'SUCCEEDED',
      error: null,
    })),
    expectedFinalSurface: expectedSurface(application),
  };
}

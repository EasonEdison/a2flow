import {
  hasForbiddenMappingField,
  isProtectedAuthorityTarget,
  validateA2uiApplicationBuild,
  type A2uiApplicationDraft,
  type A2uiRequestMapping,
} from './a2uiApplicationContracts';
import type { A2uiCatalogComponentRecord } from './a2uiCatalogContracts';

export interface A2uiApplicationValidationIssue {
  code: string;
  path: string;
}

const DEFAULT_PATHS: Record<string, string> = {
  A2UI_APPLICATION_IDENTITY_REQUIRED: '$.appCode',
  A2UI_PROTOCOL_UNSUPPORTED: '$.protocolVersion',
  A2UI_APPLICATION_INTERACTION_MODE_INVALID: '$.interactionMode',
  A2UI_INTERACTIVE_COMPLETION_ACTION_REQUIRED: '$.actionBindings',
  A2UI_DISPLAY_ONLY_COMPLETION_ACTION_FORBIDDEN: '$.actionBindings',
  A2UI_CATALOG_REF_INVALID: '$.catalog',
  A2UI_APPLICATION_CATALOG_PREPROD_NOT_PUBLISHED: '$.catalog.releases.PRT',
  A2UI_APPLICATION_CATALOG_ONLINE_NOT_PUBLISHED: '$.catalog.releases.ONLINE',
  A2UI_CATALOG_ENVIRONMENT_MISMATCH: '$.catalog.releases',
  A2UI_SHOW_TEMPLATE_CONTRACT_INVALID: '$.showTemplate',
  A2UI_SHOW_MESSAGE_VERSION_INVALID: '$.showTemplate.messageTemplates',
  A2UI_SHOW_MESSAGE_TYPE_INVALID: '$.showTemplate.messageTemplates',
  A2UI_SHOW_MESSAGE_FIELD_INVALID: '$.showTemplate.messageTemplates',
  A2UI_SHOW_MESSAGE_SURFACE_REQUIRED: '$.showTemplate.messageTemplates',
  A2UI_SHOW_SURFACE_CREATE_DUPLICATE: '$.showTemplate.messageTemplates',
  A2UI_SHOW_CATALOG_MISMATCH: '$.showTemplate.messageTemplates',
  A2UI_SHOW_SURFACE_ORDER_INVALID: '$.showTemplate.messageTemplates',
  A2UI_SHOW_COMPONENTS_INVALID: '$.showTemplate.messageTemplates',
  A2UI_SHOW_COMPONENT_INVALID: '$.showTemplate.messageTemplates',
  A2UI_SHOW_ACTION_INVALID: '$.showTemplate.messageTemplates',
  A2UI_SHOW_DATA_MODEL_PATH_INVALID: '$.showTemplate.messageTemplates',
  A2UI_SHOW_COMPONENT_ID_DUPLICATE: '$.showTemplate.messageTemplates',
  A2UI_SHOW_ROOT_NOT_FOUND: '$.showTemplate.surfaceDeclarations',
  A2UI_SHOW_CHILD_NOT_FOUND: '$.showTemplate.messageTemplates',
  A2UI_SHOW_INPUT_BINDING_INVALID: '$.showTemplate.inputBindings',
  A2UI_COMPONENT_NOT_AVAILABLE: '$.showTemplate.messageTemplates',
  A2UI_ACTION_DECLARATION_DUPLICATE: '$.showTemplate.messageTemplates',
  A2UI_ACTION_BINDING_MISSING: '$.actionBindings',
  A2UI_ACTION_BINDING_DUPLICATE: '$.actionBindings',
  A2UI_ACTION_BINDING_ORPHAN: '$.actionBindings',
  A2UI_WORKFLOW_ACTION_RESERVED: '$.actionBindings',
  A2UI_CAPABILITY_ACTION_CODE_REQUIRED: '$.actionBindings[*].capability.actionCode',
  A2UI_ACTION_BINDING_CLOSURE_INVALID: '$.actionBindings[*]',
  A2UI_ACTION_BINDING_COMPLETION_FLAG_INVALID:
    '$.actionBindings[*].completeWorkflowInteractionOnSuccess',
  A2UI_MAPPING_SOURCE_INVALID: '$.actionBindings[*].requestMappings[*].source',
  A2UI_LOAD_MAPPING_SOURCE_INVALID: '$.loadBindings[*].requestMappings[*].source',
  A2UI_LOAD_BINDING_INVALID: '$.loadBindings',
  A2UI_FAILURE_RESULT_ADAPTER_REQUIRED: '$.actionBindings[*].failureOutcome',
  A2UI_RESULT_OUTCOME_REQUIRED: '$.actionBindings[*]',
  A2UI_NO_UI_MESSAGES_ADAPTER_CONFLICT: '$.actionBindings[*]',
  A2UI_RESULT_ADAPTER_REQUIRED: '$.actionBindings[*].resultAdapters',
  A2UI_RESULT_ADAPTER_ORDER_INVALID: '$.actionBindings[*].resultAdapters[*].order',
  A2UI_RESULT_ADAPTER_ORDER_DUPLICATE: '$.actionBindings[*].resultAdapters[*].order',
  A2UI_MESSAGE_TEMPLATE_REQUIRED: '$.actionBindings[*].resultAdapters',
  A2UI_MESSAGE_TEMPLATE_CLOSURE_REQUIRED: '$.actionBindings[*].resultAdapters',
  A2UI_MESSAGE_TEMPLATE_BINDING_INVALID: '$.actionBindings[*].resultAdapters[*].bindings',
  A2UI_PASSTHROUGH_SOURCE_ROOT_INVALID: '$.actionBindings[*].resultAdapters[*].source',
  A2UI_PASSTHROUGH_SOURCE_REQUIRED: '$.actionBindings[*].resultAdapters[*].sourcePath',
  A2UI_PASSTHROUGH_CARDINALITY_REQUIRED: '$.actionBindings[*].resultAdapters[*].cardinality',
  A2UI_PASSTHROUGH_REQUIRED_INVALID: '$.actionBindings[*].resultAdapters[*].required',
};

function locateMapping(
  application: A2uiApplicationDraft,
  predicate: (mapping: A2uiRequestMapping) => boolean,
  field?: string,
): string | undefined {
  for (let loadIndex = 0; loadIndex < application.loadBindings?.length; loadIndex += 1) {
    const mappingIndex =
      application.loadBindings?.[loadIndex]?.requestMappings?.findIndex?.(predicate) ?? -1;
    if (mappingIndex >= 0) {
      const base = `$.loadBindings[${loadIndex}].requestMappings[${mappingIndex}]`;
      return field ? `${base}.${field}` : base;
    }
  }
  for (let bindingIndex = 0; bindingIndex < application.actionBindings?.length; bindingIndex += 1) {
    const mappingIndex =
      application.actionBindings?.[bindingIndex]?.requestMappings?.findIndex?.(predicate) ?? -1;
    if (mappingIndex >= 0) {
      const base = `$.actionBindings[${bindingIndex}].requestMappings[${mappingIndex}]`;
      return field ? `${base}.${field}` : base;
    }
  }
  return undefined;
}

function locateIssue(code: string, application: A2uiApplicationDraft): string {
  if (code === 'A2UI_AUTHORITY_MAPPING_FORBIDDEN') {
    return (
      locateMapping(
        application,
        (mapping) =>
          mapping.source !== 'TRUSTED_CONTEXT' && isProtectedAuthorityTarget(mapping.targetPath),
        'targetPath',
      ) || '$.actionBindings[*].requestMappings[*].targetPath'
    );
  }
  if (code === 'A2UI_MAPPING_FIELD_FORBIDDEN') {
    return (
      locateMapping(application, hasForbiddenMappingField) ||
      '$.actionBindings[*].requestMappings[*]'
    );
  }
  return DEFAULT_PATHS[code] || '$';
}

export function validateA2uiApplicationBuildIssues(
  application: A2uiApplicationDraft,
  catalogComponents: A2uiCatalogComponentRecord[],
): A2uiApplicationValidationIssue[] {
  return validateA2uiApplicationBuild(application, catalogComponents)?.map?.((code) => ({
    code,
    path: locateIssue(code, application),
  }));
}

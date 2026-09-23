import {
  normalizeA2uiApplicationDraft,
  type A2uiActionBinding,
  type A2uiApplicationCatalogRef,
  type A2uiApplicationDraft,
  type A2uiInteractionMode,
  type A2uiLoadBinding,
  type A2uiShowTemplate,
} from './a2uiApplicationContracts';
import type { A2uiApplicationEditableStage } from './a2uiApplicationEditorModel';

export interface A2uiApplicationFormValues {
  appCode: string;
  nameCn: string;
  description: string;
  interactionMode: A2uiInteractionMode;
  catalogId: string;
  sampleParamsJson: string;
  showTemplateJson: string;
  loadBindingsJson: string;
  actionBindingsJson: string;
}

export type A2uiApplicationFormParseResult =
  | { ok: true; application: A2uiApplicationDraft }
  | { ok: false; errors: string[] };

export interface A2uiApplicationStageParseOptions {
  baseApplication: A2uiApplicationDraft;
  stage: A2uiApplicationEditableStage;
}

export const A2UI_APPLICATION_STAGE_FORM_FIELDS: Record<
  A2uiApplicationEditableStage,
  Array<keyof A2uiApplicationFormValues>
> = {
  basic: ['appCode', 'nameCn', 'description', 'interactionMode', 'catalogId'],
  show: ['showTemplateJson'],
  actions: ['loadBindingsJson', 'actionBindingsJson'],
};

function jsonText(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

export function toA2uiApplicationFormValues(
  application: A2uiApplicationDraft,
): A2uiApplicationFormValues {
  return {
    appCode: application.appCode,
    nameCn: application.nameCn,
    description: application.description,
    interactionMode: application.interactionMode || 'DISPLAY_ONLY',
    catalogId: application.catalog?.catalogId || '',
    sampleParamsJson: '{}',
    showTemplateJson: jsonText(application.showTemplate),
    loadBindingsJson: jsonText(application.loadBindings),
    actionBindingsJson: jsonText(application.actionBindings),
  };
}

function parseJson(text: string, errorCode: string, errors: string[]): unknown {
  try {
    return JSON.parse(text);
  } catch {
    errors.push(errorCode);
    return undefined;
  }
}

function parseObject(
  text: string,
  errorCode: string,
  errors: string[],
): Record<string, unknown> | undefined {
  const parsed = parseJson(text, errorCode, errors);
  if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
    if (!errors.includes(errorCode)) errors.push(errorCode);
    return undefined;
  }
  return parsed as Record<string, unknown>;
}

function parseCatalogId(value: string, errors: string[]): string | undefined {
  if (typeof value !== 'string' || !value.trim()) {
    errors.push('A2UI_CATALOG_ID_REQUIRED');
    return undefined;
  }
  return value.trim();
}

function parseInteractionMode(value: unknown, errors: string[]): A2uiInteractionMode | undefined {
  if (value === 'DISPLAY_ONLY' || value === 'INTERACTIVE') return value;
  errors.push('A2UI_APPLICATION_INTERACTION_MODE_INVALID');
  return undefined;
}

function normalizeApplication(
  application: A2uiApplicationDraft,
  errors: string[],
): A2uiApplicationDraft | undefined {
  try {
    return normalizeA2uiApplicationDraft(application);
  } catch (reason) {
    errors.push(reason instanceof Error ? reason.message : 'A2UI_APPLICATION_DRAFT_INVALID');
    return undefined;
  }
}

function catalogSelection(
  catalogId: string,
  baseCatalog?: A2uiApplicationCatalogRef,
): A2uiApplicationCatalogRef {
  if (baseCatalog?.catalogId === catalogId) return { ...baseCatalog };
  return { catalogId, revision: '', digest: '' };
}

function parseArray(text: string, errorCode: string, errors: string[]): unknown[] | undefined {
  const parsed = parseJson(text, errorCode, errors);
  if (!Array.isArray(parsed)) {
    if (!errors.includes(errorCode)) errors.push(errorCode);
    return undefined;
  }
  return parsed;
}

export function parseA2uiApplicationForm(
  values: A2uiApplicationFormValues,
  options?: A2uiApplicationStageParseOptions,
): A2uiApplicationFormParseResult {
  if (options?.stage === 'basic') {
    const errors: string[] = [];
    const catalogId = parseCatalogId(values.catalogId, errors);
    const interactionMode = parseInteractionMode(values.interactionMode, errors);
    if (!catalogId || !interactionMode) return { ok: false, errors: [...new Set(errors)] };
    return {
      ok: true,
      application: {
        ...options.baseApplication,
        appCode: values.appCode,
        nameCn: values.nameCn,
        description: values.description,
        interactionMode,
        catalog: catalogSelection(catalogId, options.baseApplication?.catalog),
      },
    };
  }

  const errors: string[] = [];
  if (options?.stage === 'show') {
    const showTemplate = parseObject(
      values.showTemplateJson,
      'A2UI_SHOW_TEMPLATE_JSON_INVALID',
      errors,
    );
    if (!showTemplate || errors.length) return { ok: false, errors: [...new Set(errors)] };
    return {
      ok: true,
      application: {
        ...options.baseApplication,
        showTemplate: showTemplate as unknown as A2uiShowTemplate,
      },
    };
  }

  const loadBindings = parseArray(
    values.loadBindingsJson,
    'A2UI_LOAD_BINDINGS_JSON_INVALID',
    errors,
  );
  const actionBindings = parseArray(
    values.actionBindingsJson,
    'A2UI_ACTION_BINDINGS_JSON_INVALID',
    errors,
  );
  if (options?.stage === 'actions') {
    if (!loadBindings || !actionBindings || errors.length) {
      return { ok: false, errors: [...new Set(errors)] };
    }
    const application = normalizeApplication(
      {
        ...options.baseApplication,
        loadBindings: loadBindings as A2uiLoadBinding[],
        actionBindings: actionBindings as A2uiActionBinding[],
      },
      errors,
    );
    if (!application || errors.length) {
      return { ok: false, errors: [...new Set(errors)] };
    }
    return {
      ok: true,
      application,
    };
  }

  const showTemplate = parseObject(
    values.showTemplateJson,
    'A2UI_SHOW_TEMPLATE_JSON_INVALID',
    errors,
  );
  const catalogId = parseCatalogId(values.catalogId, errors);
  const interactionMode = parseInteractionMode(values.interactionMode, errors);
  if (
    !showTemplate ||
    !loadBindings ||
    !actionBindings ||
    !catalogId ||
    !interactionMode ||
    errors.length
  ) {
    return { ok: false, errors: [...new Set(errors)] };
  }
  const application = normalizeApplication(
    {
      appCode: values.appCode,
      nameCn: values.nameCn,
      description: values.description,
      interactionMode,
      protocolVersion: 'v0.9.1',
      protocolStatus: 'CURRENT_PRODUCTION',
      catalog: catalogSelection(catalogId),
      showTemplate: showTemplate as unknown as A2uiShowTemplate,
      loadBindings: loadBindings as A2uiLoadBinding[],
      actionBindings: actionBindings as A2uiActionBinding[],
    },
    errors,
  );
  if (!application || errors.length) {
    return { ok: false, errors: [...new Set(errors)] };
  }
  return {
    ok: true,
    application,
  };
}

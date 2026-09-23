export interface A2uiMessage extends Record<string, unknown> {
  version: 'v0.9.1';
}

export type A2uiShowInputSource = 'APP_PARAMS' | 'TRUSTED_CONTEXT' | 'CONSTANT';

export interface A2uiShowInputBinding {
  targetMessageIndex: number;
  targetPath: string;
  source: A2uiShowInputSource;
  sourcePath: string;
  required: boolean;
  constantValue?: unknown;
}

export interface A2uiSurfaceDeclaration {
  surfaceId: string;
  rootComponentId: string;
  /** Workflow 同排操作区：引用根容器的直接子组件。 */
  footerComponentIds?: string[];
}

export interface A2uiShowTemplate {
  templateCode: string;
  paramsSchema: Record<string, unknown>;
  surfaceDeclarations: A2uiSurfaceDeclaration[];
  messageTemplates: A2uiMessage[];
  inputBindings: A2uiShowInputBinding[];
}

export interface A2uiFlatComponent extends Record<string, unknown> {
  id: string;
  component: string;
  children?: string[];
}

export interface A2uiExtractedComponent {
  surfaceId: string;
  definition: A2uiFlatComponent;
}

export interface A2uiExtractedAction {
  eventName: string;
  actionCode: string;
  sourceComponentId: string;
  surfaceId: string;
  contextTemplate: Record<string, unknown>;
}

const SERVER_MESSAGE_KEYS = [
  'createSurface',
  'updateComponents',
  'updateDataModel',
  'deleteSurface',
] as const;

function objectValue(value: unknown): Record<string, unknown> | undefined {
  return value && !Array.isArray(value) && typeof value === 'object'
    ? (value as Record<string, unknown>)
    : undefined;
}

function stringValue(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value : undefined;
}

export function serverMessageKey(message: A2uiMessage): string | undefined {
  const keys = SERVER_MESSAGE_KEYS.filter((key) => objectValue(message[key]));
  return keys.length === 1 ? keys?.[0] : undefined;
}

export function extractShowComponents(show: A2uiShowTemplate): A2uiExtractedComponent[] {
  return show.messageTemplates?.flatMap?.((message) => {
    const update = objectValue(message.updateComponents);
    const surfaceId = stringValue(update?.surfaceId);
    const components = Array.isArray(update?.components) ? update.components : [];
    if (!surfaceId) return [];
    return components.flatMap((candidate) => {
      const component = objectValue(candidate);
      const id = stringValue(component?.id);
      const type = stringValue(component?.component);
      return id && type ? [{ surfaceId, definition: component as A2uiFlatComponent }] : [];
    });
  });
}

export function extractShowActions(show: A2uiShowTemplate): A2uiExtractedAction[] {
  return extractShowComponents(show)?.flatMap?.(({ surfaceId, definition }) => {
    const action = objectValue(definition.action);
    const event = objectValue(action?.event);
    const actionCode = stringValue(event?.name);
    if (!actionCode) return [];
    return [
      {
        eventName: actionCode,
        actionCode,
        sourceComponentId: definition.id,
        surfaceId,
        contextTemplate: objectValue(event?.context) || {},
      },
    ];
  });
}

export function validateShowAst(show: A2uiShowTemplate, catalogId: string): string[] {
  const errors: string[] = [];
  if (!stringValue(show.templateCode) || objectValue(show.paramsSchema)?.type !== 'object') {
    errors.push('A2UI_SHOW_TEMPLATE_CONTRACT_INVALID');
  }
  const created = new Set<string>();
  const deleted = new Set<string>();
  show.messageTemplates?.forEach?.((message) => {
    if (message.version !== 'v0.9.1') errors.push('A2UI_SHOW_MESSAGE_VERSION_INVALID');
    const key = serverMessageKey(message);
    if (!key) {
      errors.push('A2UI_SHOW_MESSAGE_TYPE_INVALID');
      return;
    }
    if (Object.keys(message).some((field) => field !== 'version' && field !== key)) {
      errors.push('A2UI_SHOW_MESSAGE_FIELD_INVALID');
    }
    const payload = objectValue(message[key]);
    const surfaceId = stringValue(payload?.surfaceId);
    if (!surfaceId) {
      errors.push('A2UI_SHOW_MESSAGE_SURFACE_REQUIRED');
      return;
    }
    if (key === 'createSurface') {
      if (created.has(surfaceId) && !deleted.has(surfaceId)) {
        errors.push('A2UI_SHOW_SURFACE_CREATE_DUPLICATE');
      }
      if (payload?.catalogId !== catalogId) errors.push('A2UI_SHOW_CATALOG_MISMATCH');
      created.add(surfaceId);
      deleted.delete(surfaceId);
      return;
    }
    if (!created.has(surfaceId) || deleted.has(surfaceId)) {
      errors.push('A2UI_SHOW_SURFACE_ORDER_INVALID');
    }
    if (key === 'updateComponents' && !Array.isArray(payload?.components)) {
      errors.push('A2UI_SHOW_COMPONENTS_INVALID');
    }
    if (key === 'updateComponents' && Array.isArray(payload?.components)) {
      payload.components?.forEach?.((candidate) => {
        const component = objectValue(candidate);
        if (!stringValue(component?.id) || !stringValue(component?.component)) {
          errors.push('A2UI_SHOW_COMPONENT_INVALID');
        }
        if (component?.action !== undefined) {
          const event = objectValue(objectValue(component.action)?.event);
          if (!stringValue(event?.name)) errors.push('A2UI_SHOW_ACTION_INVALID');
        }
      });
    }
    if (key === 'updateDataModel' && !stringValue(payload?.path)) {
      errors.push('A2UI_SHOW_DATA_MODEL_PATH_INVALID');
    }
    if (key === 'deleteSurface') deleted.add(surfaceId);
  });

  const components = extractShowComponents(show);
  const componentKeys = components.map(
    ({ surfaceId, definition }) => `${surfaceId}:${definition.id}`,
  );
  if (new Set(componentKeys).size !== componentKeys.length) {
    errors.push('A2UI_SHOW_COMPONENT_ID_DUPLICATE');
  }
  const componentKeySet = new Set(componentKeys);
  show.surfaceDeclarations?.forEach?.((surface) => {
    if (!componentKeySet.has(`${surface.surfaceId}:${surface.rootComponentId}`)) {
      errors.push('A2UI_SHOW_ROOT_NOT_FOUND');
    }
    const footerIds = surface.footerComponentIds || [];
    const root = components.find(({ surfaceId, definition }) =>
      surfaceId === surface.surfaceId && definition.id === surface.rootComponentId)?.definition;
    if (!Array.isArray(footerIds) || new Set(footerIds).size !== footerIds.length
      || footerIds.some((id) => !stringValue(id) || id === surface.rootComponentId
        || !componentKeySet.has(`${surface.surfaceId}:${id}`) || !root?.children?.includes(id)
        || components.find((value) => value.surfaceId === surface.surfaceId
          && value.definition.id === id)?.definition.component !== 'Container')) {
      errors.push('A2UI_SHOW_FOOTER_INVALID');
    }
  });
  components.forEach(({ surfaceId, definition }) => {
    if ((definition.children || []).some((id) => !componentKeySet.has(`${surfaceId}:${id}`))) {
      errors.push('A2UI_SHOW_CHILD_NOT_FOUND');
    }
  });
  show.inputBindings?.forEach?.((binding) => {
    if (
      !Number.isInteger(binding.targetMessageIndex) ||
      binding.targetMessageIndex < 0 ||
      binding.targetMessageIndex >= show.messageTemplates?.length ||
      !stringValue(binding.targetPath)
    ) {
      errors.push('A2UI_SHOW_INPUT_BINDING_INVALID');
    }
  });
  return [...new Set(errors)];
}

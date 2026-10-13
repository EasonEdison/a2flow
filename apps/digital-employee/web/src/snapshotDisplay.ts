import type { ChatCard } from './productApi';
import { A2uiMessageListSchema } from '@a2ui/web_core/v0_9';

export const TEMPORARY_PROFILE = 'a2flow.temporary.v1';
type Row = Record<string, unknown>;
const recordOf = (value: unknown): Row => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('CHAT_CONTRACT_INVALID');
  return value as Row;
};
const textOf = (value: unknown): string => typeof value === 'string' ? value : '';
const optionalString = (value: unknown): string | undefined => typeof value === 'string' && value ? value : undefined;

/** Shared persisted snapshot contract for Chat and Workflow cards. */
export function parseSnapshotDisplay(value: unknown): ChatCard['display'] {
  const display = recordOf(value);
  const catalog = recordOf(display.catalog);
  const actions = Array.isArray(display.actions) ? display.actions.map((value) => {
    const action = recordOf(value);
    return {
      actionName: textOf(action.actionName),
      surfaceId: textOf(action.surfaceId),
      componentId: textOf(action.componentId),
      inputSchema: recordOf(action.inputSchema),
    };
  }) : [];
  if (!display.applicationKey || !display.protocolProfile
    || !catalog.protocolVersion || !catalog.catalogId || !catalog.catalogDigest
    || !Array.isArray(display.snapshotMessages)) {
    throw new Error('CHAT_CONTRACT_INVALID');
  }
  if (display.protocolProfile === TEMPORARY_PROFILE) {
    if (display.definitionSource !== 'TEMPORARY'
      || !['DISPLAY_ONLY', 'INTERACTIVE'].includes(textOf(display.mode))
      || typeof display.title !== 'string'
      || !['v0.9.1', '0.9.1'].includes(textOf(catalog.protocolVersion))
      || typeof catalog.catalogId !== 'string' || typeof catalog.catalogDigest !== 'string'
      || !((typeof catalog.catalogRevision === 'string' && catalog.catalogRevision.length > 0)
        || typeof catalog.catalogRevision === 'number')
      || !Array.isArray(display.actions)) throw new Error('CHAT_CONTRACT_INVALID');
    recordOf(display.inputSchema);
    const messages = A2uiMessageListSchema.parse(display.snapshotMessages);
    if (!messages.length || messages.length > 1000 || messages.some(message =>
      message.version !== 'v0.9.1'
      || ('createSurface' in message && message.createSurface.catalogId !== catalog.catalogId))) {
      throw new Error('CHAT_CONTRACT_INVALID');
    }
    if (actions.some(action => !action.actionName || !action.surfaceId || !action.componentId)) {
      throw new Error('CHAT_CONTRACT_INVALID');
    }
  }
  return {
    applicationKey: textOf(display.applicationKey),
    ...(typeof display.applicationVersion === 'string' || typeof display.applicationVersion === 'number'
      ? { applicationVersion: display.applicationVersion } : {}),
    protocolProfile: textOf(display.protocolProfile),
    ...(display.definitionSource === 'GENERATED' || display.definitionSource === 'PUBLISHED' || display.definitionSource === 'TEMPORARY'
      ? { definitionSource: display.definitionSource } : {}),
    ...(typeof display.title === 'string' ? { title: display.title } : {}),
    ...(display.mode === 'DISPLAY_ONLY' || display.mode === 'INTERACTIVE' ? { mode: display.mode } : {}),
    ...(display.inputSchema ? { inputSchema: recordOf(display.inputSchema) } : {}),
    snapshotMessages: display.snapshotMessages.map(recordOf),
    catalog: {
      protocolVersion: textOf(catalog.protocolVersion),
      catalogId: textOf(catalog.catalogId),
      catalogRevision: typeof catalog.catalogRevision === 'number'
        ? catalog.catalogRevision : textOf(catalog.catalogRevision),
      catalogDigest: textOf(catalog.catalogDigest),
    },
    ...(optionalString(display.rootId) ? { rootId: textOf(display.rootId) } : {}),
    ...(Array.isArray(display.components) ? { components: display.components.map(recordOf) } : {}),
    ...(display.data && typeof display.data === 'object' && !Array.isArray(display.data)
      ? { data: recordOf(display.data) } : {}),
    actions,
  };
}

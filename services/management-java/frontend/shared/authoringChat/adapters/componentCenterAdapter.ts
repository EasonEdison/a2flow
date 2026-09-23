import type { SkillFactoryAuthoringDomainAdapter } from '../types';
import { SKILL_FACTORY_CHAT_BIZ_KEYS, type SkillFactoryCodingEvent } from '../../../api';

const SIDE_PANEL_PAYLOAD_TYPES = new Set([
  'COMPONENT_ASSET_SCHEMA_REFERENCE',
  'COMPONENT_ASSET_EXISTING_ASSETS',
  'COMPONENT_ASSET_VALIDATION',
  'COMPONENT_ASSET_VALIDATION_RESULT',
  'COMPONENT_ASSET_PREVIEW',
  'COMPONENT_ASSET_PREVIEW_RESULT',
  'COMPONENT_ASSET_SAVE_PREPARE',
  'COMPONENT_ASSET_SAVE_PREPARED',
]);

export interface ComponentCenterAuthoringAdapterOptions<TDraft = unknown> {
  assetType: string;
  assetId?: string | null;
  draftId: string;
  formKey: string;
  entityId: string;
  revision: number;
  baseFingerprint: string;
  componentCode?: string;
  disabledReason?: string;
  agentId?: string;
  ownerId?: string;
  onEvent?: (event: SkillFactoryCodingEvent) => void;
}

function recordOf(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function parseRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value !== 'string') return null;
  try {
    return recordOf(JSON.parse(value));
  } catch {
    return null;
  }
}

function payloadTypeOf(event: SkillFactoryCodingEvent): string {
  const payload = recordOf(event.payload) || parseRecord(event.payloadJson);
  const content = recordOf(payload?.content);
  return String(
    event.payloadType ||
      payload?.payloadType ||
      content?.payloadType ||
      payload?.type ||
      event.eventCode ||
      event.eventType ||
      '',
  );
}

export function createComponentCenterAuthoringAdapter<TDraft = unknown>({
  assetType,
  assetId,
  draftId,
  formKey,
  entityId,
  revision,
  baseFingerprint,
  componentCode,
  disabledReason,
  agentId,
  ownerId,
  onEvent,
}: ComponentCenterAuthoringAdapterOptions<TDraft>): SkillFactoryAuthoringDomainAdapter<TDraft> {
  // 会话和提案身份绑定稳定 entityId，不能随用户编辑组件 code 而切换。
  const scopeId = entityId;
  return {
    domain: 'COMPONENT_CENTER',
    sessionScope: {
      bizKey: SKILL_FACTORY_CHAT_BIZ_KEYS.COMPONENT_CENTER_AUTHORING,
      scopeType: 'COMPONENT',
      scopeId,
      workspaceId: scopeId,
      componentCode: componentCode || scopeId,
      assetId: assetId || undefined,
      draftId,
      authoringDomain: 'COMPONENT_CENTER',
      disabledReason,
    },
    buildRequest: ({ message, currentDraft, sessionId, messageId, runId }) => ({
      bizKey: SKILL_FACTORY_CHAT_BIZ_KEYS.COMPONENT_CENTER_AUTHORING,
      authoringDomain: 'COMPONENT_CENTER',
      assetType,
      assetId,
      draftId,
      formKey,
      entityId,
      revision,
      baseFingerprint,
      agentId,
      ownerId,
      componentCode: componentCode || scopeId,
      scopeType: 'COMPONENT',
      scopeId,
      message,
      currentDraft,
      sessionId,
      messageId,
      runId,
    }),
    isBusinessEventVisible: (event) => !SIDE_PANEL_PAYLOAD_TYPES.has(payloadTypeOf(event)),
    onEvent,
  };
}

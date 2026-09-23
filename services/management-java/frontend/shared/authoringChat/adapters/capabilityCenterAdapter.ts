import type { SkillFactoryAuthoringDomainAdapter } from '../types';
import { SKILL_FACTORY_CHAT_BIZ_KEYS, type SkillFactoryCodingEvent } from '../../../api';

const SIDE_PANEL_PAYLOAD_TYPES = new Set([
  'CAPABILITY_API_SOURCE_DETAIL',
  'CAPABILITY_VALIDATION_REPORT',
  'CAPABILITY_PUBLISH_PREPARE',
]);

export interface CapabilityCenterAuthoringProfile {
  domain: 'CAPABILITY_CENTER';
  bizKey: typeof SKILL_FACTORY_CHAT_BIZ_KEYS.CAPABILITY_CENTER_AUTHORING;
  scopeType: 'CAPABILITY';
  draftSchemaId: 'capabilityActionDraft.v1';
  formTemplateId: 'capability_action_editor.v1';
  deltaEvent: 'FORM_PATCH_PROPOSED';
  validationEvent: 'CAPABILITY_VALIDATION_REPORT';
  commands: Array<'SAVE_DRAFT' | 'VALIDATE' | 'PUBLISH' | 'CREATE_VERSION'>;
}

export const CAPABILITY_CENTER_AUTHORING_PROFILE: CapabilityCenterAuthoringProfile = {
  domain: 'CAPABILITY_CENTER',
  bizKey: SKILL_FACTORY_CHAT_BIZ_KEYS.CAPABILITY_CENTER_AUTHORING,
  scopeType: 'CAPABILITY',
  draftSchemaId: 'capabilityActionDraft.v1',
  formTemplateId: 'capability_action_editor.v1',
  deltaEvent: 'FORM_PATCH_PROPOSED',
  validationEvent: 'CAPABILITY_VALIDATION_REPORT',
  commands: ['SAVE_DRAFT', 'VALIDATE', 'PUBLISH', 'CREATE_VERSION'],
};

export interface CapabilityCenterAuthoringAdapterOptions<TDraft = unknown> {
  draftId: string;
  actionCode?: string;
  revision?: number;
  formKey?: string;
  entityId?: string;
  baseFingerprint?: string;
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
  return String(
    event.payloadType ||
      payload?.payloadType ||
      payload?.type ||
      event.eventCode ||
      event.eventType ||
      '',
  );
}

export function createCapabilityCenterAuthoringAdapter<TDraft = unknown>({
  draftId,
  actionCode,
  revision,
  formKey,
  entityId,
  baseFingerprint,
  disabledReason,
  agentId,
  ownerId,
  onEvent,
}: CapabilityCenterAuthoringAdapterOptions<TDraft>): SkillFactoryAuthoringDomainAdapter<TDraft> {
  // actionCode 在草稿期允许编辑，会话身份必须使用稳定的 draftId，避免输入过程中切换历史会话。
  const scopeId = draftId;
  return {
    domain: CAPABILITY_CENTER_AUTHORING_PROFILE.domain,
    sessionScope: {
      bizKey: CAPABILITY_CENTER_AUTHORING_PROFILE.bizKey,
      scopeType: CAPABILITY_CENTER_AUTHORING_PROFILE.scopeType,
      scopeId,
      workspaceId: scopeId,
      draftId,
      authoringDomain: CAPABILITY_CENTER_AUTHORING_PROFILE.domain,
      disabledReason,
    },
    buildRequest: ({ message, currentDraft, sessionId, messageId, runId }) => ({
      bizKey: CAPABILITY_CENTER_AUTHORING_PROFILE.bizKey,
      authoringDomain: CAPABILITY_CENTER_AUTHORING_PROFILE.domain,
      scopeType: CAPABILITY_CENTER_AUTHORING_PROFILE.scopeType,
      scopeId,
      draftId,
      actionCode,
      revision,
      formKey,
      entityId,
      baseFingerprint,
      agentId,
      ownerId,
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

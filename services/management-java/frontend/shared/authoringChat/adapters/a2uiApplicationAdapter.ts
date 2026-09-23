import type { AuthoringSessionScopeParams, SkillFactoryCodingEvent } from '../../../api';
import { SKILL_FACTORY_CHAT_BIZ_KEYS } from '../../../api';
import type { SkillFactoryAuthoringDomainAdapter } from '../types';

export interface A2uiApplicationAuthoringAdapterOptions<TDraft = unknown> {
  applicationId?: string | null;
  draftId: string;
  appCode?: string;
  revision?: number;
  baseFingerprint?: string;
  agentId?: string;
  ownerId?: string;
  disabledReason?: string;
  onEvent?: (event: SkillFactoryCodingEvent) => void;
}

export function createA2uiApplicationAuthoringAdapter<TDraft = unknown>({
  applicationId,
  draftId,
  appCode,
  revision,
  baseFingerprint,
  agentId,
  ownerId,
  disabledReason,
  onEvent,
}: A2uiApplicationAuthoringAdapterOptions<TDraft>): SkillFactoryAuthoringDomainAdapter<TDraft> {
  const scopeId = applicationId || draftId;
  const sessionScope = {
    bizKey: SKILL_FACTORY_CHAT_BIZ_KEYS.A2UI_COMPONENT_AUTHORING,
    scopeType: 'A2UI_APPLICATION',
    scopeId,
    workspaceId: scopeId,
    assetId: applicationId || undefined,
    draftId,
    appCode: appCode || undefined,
    authoringDomain: 'A2UI_APPLICATION',
    disabledReason,
  } as AuthoringSessionScopeParams & { appCode?: string; disabledReason?: string };

  return {
    domain: 'A2UI_APPLICATION',
    sessionScope,
    buildRequest: ({ message, currentDraft, sessionId, messageId, runId }) => ({
      bizKey: SKILL_FACTORY_CHAT_BIZ_KEYS.A2UI_COMPONENT_AUTHORING,
      authoringDomain: 'A2UI_APPLICATION',
      scopeType: 'A2UI_APPLICATION',
      scopeId,
      workspaceId: scopeId,
      applicationId: applicationId || undefined,
      draftId,
      appCode: appCode || undefined,
      revision,
      baseFingerprint,
      agentId,
      ownerId,
      message,
      currentDraft,
      sessionId,
      messageId,
      runId,
    }),
    onEvent,
  };
}

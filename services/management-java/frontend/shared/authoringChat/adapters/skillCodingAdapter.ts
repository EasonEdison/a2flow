import type { SkillFactoryAuthoringDomainAdapter } from '../types';
import type { AuthoringSessionScopeParams, SkillFactoryCodingEvent } from '../../../api';

export interface SkillCodingAuthoringAdapterOptions<TDraft = unknown> {
  sessionScope: AuthoringSessionScopeParams & { disabledReason?: string };
  buildRequest: SkillFactoryAuthoringDomainAdapter<TDraft>['buildRequest'];
  onEvent?: (event: SkillFactoryCodingEvent) => void;
}

export function createSkillCodingAuthoringAdapter<TDraft = unknown>({
  sessionScope,
  buildRequest,
  onEvent,
}: SkillCodingAuthoringAdapterOptions<TDraft>): SkillFactoryAuthoringDomainAdapter<TDraft> {
  return {
    domain: 'SKILL_CODING',
    sessionScope,
    buildRequest,
    onEvent,
  };
}

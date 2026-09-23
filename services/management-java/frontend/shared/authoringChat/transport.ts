import { streamSkillFactoryEvents } from '../../api';
import type { SkillFactoryCodingEvent } from '../../api';

export interface SkillFactoryAuthoringTransportOptions {
  signal?: AbortSignal;
}

export type SkillFactoryAuthoringTransport = (
  params: Record<string, unknown>,
  onEvent: (event: SkillFactoryCodingEvent) => void,
  options?: SkillFactoryAuthoringTransportOptions,
) => Promise<void>;

export const skillFactorySseTransport: SkillFactoryAuthoringTransport = (
  params,
  onEvent,
  options,
) => streamSkillFactoryEvents(params, onEvent, options);

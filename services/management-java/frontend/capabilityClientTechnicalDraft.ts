import type { CapabilityActionDraftData, CapabilityClientTechnicalVariant } from './api';
import {
  capabilityClientModeOf,
  capabilityClientsForMode,
  type CapabilityClient,
  type CapabilityClientMode,
} from './capabilityClientVariantLayout';

export type CapabilityTechnicalSection =
  | 'apiSource'
  | 'modelContract'
  | 'executionBinding'
  | 'resultContract';

export type CapabilityClientTechnicalDrafts = {
  canonicalDraft: CapabilityActionDraftData;
  appPreviewDraft: CapabilityActionDraftData;
  commonPreviewDraft: CapabilityActionDraftData;
};

export type SplitCapabilityClientDrafts = {
  canonicalDraft: CapabilityActionDraftData;
  appDraft: CapabilityActionDraftData;
  commonDraft: CapabilityActionDraftData;
  clientMode: CapabilityClientMode;
};

export function capabilityTechnicalVariant(
  draft: CapabilityActionDraftData,
): CapabilityClientTechnicalVariant {
  return {
    apiSource: draft.apiSource,
    modelContract: draft.modelContract,
    executionBinding: draft.executionBinding,
    resultContract: draft.resultContract,
  };
}

export function applyCapabilityTechnicalVariant(
  commonDraft: CapabilityActionDraftData,
  variant?: Partial<CapabilityClientTechnicalVariant>,
): CapabilityActionDraftData {
  return {
    ...commonDraft,
    apiSource: { ...(variant?.apiSource || {}) },
    modelContract: { ...(variant?.modelContract || {}) },
    executionBinding: {
      ...(variant?.executionBinding || {}),
      target: { ...(variant?.executionBinding?.target || {}) },
    },
    resultContract: { ...(variant?.resultContract || {}) },
  };
}

/** 保存边界只输出公共字段和完整端契约，绝不携带旧根级技术字段。 */
export function buildCapabilityClientCanonicalDraft(
  canonicalDraft: CapabilityActionDraftData,
  appDraft: CapabilityActionDraftData,
  commonClientDraft: CapabilityActionDraftData,
  supportedClients: CapabilityClient[],
): CapabilityActionDraftData {
  const {
    apiSource: _apiSource,
    modelContract: _modelContract,
    executionBinding: _executionBinding,
    resultContract: _resultContract,
    supportedClients: _supportedClients,
    clientVariants: _clientVariants,
    ...commonDraft
  } = canonicalDraft;
  const variants: Partial<Record<CapabilityClient, CapabilityClientTechnicalVariant>> = {};
  supportedClients.forEach((client) => {
    const selectedDraft =
      client === 'APP' ? appDraft : client === 'COMMON' ? commonClientDraft : canonicalDraft;
    variants[client] = capabilityTechnicalVariant(selectedDraft);
  });
  return {
    ...commonDraft,
    supportedClients,
    clientVariants: variants,
  } as CapabilityActionDraftData;
}

/** 将完整端契约恢复为页面三份独立技术草稿；声明端与 variant 必须精确一致。 */
export function splitCapabilityClientCanonicalDraft(
  value: Partial<CapabilityActionDraftData> | null | undefined,
  emptyDraft: CapabilityActionDraftData,
): SplitCapabilityClientDrafts {
  const commonDraft = { ...emptyDraft, ...(value || {}) } as CapabilityActionDraftData;
  const variants = value?.clientVariants || {};
  const variantKeys = Object.keys(variants) as CapabilityClient[];
  const hasClientContract = Array.isArray(value?.supportedClients) || variantKeys.length > 0;
  const hasLegacyContract = ['apiSource', 'modelContract', 'executionBinding', 'resultContract']
    .some((field) => Object.prototype.hasOwnProperty.call(value || {}, field));
  const clientMode = hasClientContract
    ? capabilityClientModeOf(value?.supportedClients || variantKeys)
    : hasLegacyContract ? 'PC_ONLY' : 'PC_APP_COMMON';
  if (!clientMode) {
    throw new Error('草稿支持端配置不合法，请选择仅 PC、仅 APP、PC 与 APP 不同或 PC 与 APP 通用');
  }
  if (hasClientContract) {
    const expectedClients = capabilityClientsForMode(clientMode);
    const exactVariants =
      variantKeys.length === expectedClients.length &&
      expectedClients.every((client) => variantKeys.includes(client));
    if (!exactVariants) {
      throw new Error('草稿支持端与端侧技术契约不一致，请重新生成完整修改建议');
    }
  }
  const emptyVariant = capabilityTechnicalVariant(emptyDraft);
  return {
    canonicalDraft: applyCapabilityTechnicalVariant(
      commonDraft,
      hasClientContract ? variants.PC || emptyVariant : capabilityTechnicalVariant(commonDraft),
    ),
    appDraft: applyCapabilityTechnicalVariant(
      commonDraft,
      hasClientContract ? variants.APP || emptyVariant : emptyVariant,
    ),
    commonDraft: applyCapabilityTechnicalVariant(
      commonDraft,
      hasClientContract ? variants.COMMON || emptyVariant : emptyVariant,
    ),
    clientMode,
  };
}

export function selectCapabilityClientTechnicalDraft(
  activeClient: CapabilityClient,
  canonicalDraft: CapabilityActionDraftData,
  appPreviewDraft: CapabilityActionDraftData,
  commonPreviewDraft: CapabilityActionDraftData,
): CapabilityActionDraftData {
  if (activeClient === 'APP') return appPreviewDraft;
  if (activeClient === 'COMMON') return commonPreviewDraft;
  return canonicalDraft;
}

export function updateCapabilityClientTechnicalSection<Section extends CapabilityTechnicalSection>(
  activeClient: CapabilityClient,
  canonicalDraft: CapabilityActionDraftData,
  appPreviewDraft: CapabilityActionDraftData,
  commonPreviewDraft: CapabilityActionDraftData,
  section: Section,
  patch: Partial<CapabilityActionDraftData[Section]>,
): CapabilityClientTechnicalDrafts {
  const selectedDraft = selectCapabilityClientTechnicalDraft(
    activeClient,
    canonicalDraft,
    appPreviewDraft,
    commonPreviewDraft,
  );
  const nextDraft = {
    ...selectedDraft,
    [section]: {
      ...selectedDraft[section],
      ...patch,
    },
  };
  if (activeClient === 'APP') {
    return { canonicalDraft, appPreviewDraft: nextDraft, commonPreviewDraft };
  }
  if (activeClient === 'COMMON') {
    return { canonicalDraft, appPreviewDraft, commonPreviewDraft: nextDraft };
  }
  return { canonicalDraft: nextDraft, appPreviewDraft, commonPreviewDraft };
}

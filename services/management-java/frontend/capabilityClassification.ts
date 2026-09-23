import type { CapabilityClassificationSelection } from './api';

export function normalizeCapabilityClassification(
  value: Partial<CapabilityClassificationSelection>,
): CapabilityClassificationSelection {
  return {
    businessDomain: String(value.businessDomain || '').trim(),
    capabilityDomain: String(value.capabilityDomain || '').trim(),
    specialistIds: Array.from(
      new Set((value.specialistIds || []).map((item) => String(item).trim()).filter(Boolean)),
    ),
  };
}

export function capabilityClassificationError(
  value: Partial<CapabilityClassificationSelection>,
): string {
  const normalized = normalizeCapabilityClassification(value);
  if (!normalized.businessDomain) return '请选择业务域';
  if (!normalized.capabilityDomain) return '请选择能力域';
  if (!normalized.specialistIds?.length) return '请选择所属专员';
  return '';
}

export function encodeSpecialistIds(value: Partial<CapabilityClassificationSelection>): string {
  return normalizeCapabilityClassification(value)?.specialistIds?.join?.(',');
}

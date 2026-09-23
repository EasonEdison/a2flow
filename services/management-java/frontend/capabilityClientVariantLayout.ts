export type CapabilityClient = 'PC' | 'APP' | 'COMMON';

export type CapabilityClientMode = 'PC_ONLY' | 'APP_ONLY' | 'PC_APP_DIFFERENT' | 'PC_APP_COMMON';

export const CAPABILITY_CLIENT_MODE_OPTIONS: Array<{
  value: CapabilityClientMode;
  label: string;
}> = [
  { value: 'PC_ONLY', label: '仅 PC' },
  { value: 'APP_ONLY', label: '仅 APP' },
  { value: 'PC_APP_DIFFERENT', label: 'PC 与 APP 不同' },
  { value: 'PC_APP_COMMON', label: 'PC 与 APP 通用' },
];

const CAPABILITY_CLIENTS_BY_MODE: Record<CapabilityClientMode, CapabilityClient[]> = {
  PC_ONLY: ['PC'],
  APP_ONLY: ['APP'],
  PC_APP_DIFFERENT: ['PC', 'APP'],
  PC_APP_COMMON: ['COMMON'],
};

export type CapabilityClientVariantView = {
  mode: CapabilityClientMode;
  supportedClients: CapabilityClient[];
  activeClient: CapabilityClient;
  showClientSwitch: boolean;
  singleClientLabel: string;
};

export function capabilityClientsForMode(mode: CapabilityClientMode): CapabilityClient[] {
  return [...CAPABILITY_CLIENTS_BY_MODE[mode]];
}

export function capabilityClientModeOf(
  values: readonly string[],
): CapabilityClientMode | undefined {
  if (values.length === 1 && values?.[0] === 'PC') return 'PC_ONLY';
  if (values.length === 1 && values?.[0] === 'APP') return 'APP_ONLY';
  if (values.length === 2 && values?.[0] === 'PC' && values?.[1] === 'APP') {
    return 'PC_APP_DIFFERENT';
  }
  if (values.length === 1 && values?.[0] === 'COMMON') return 'PC_APP_COMMON';
  return undefined;
}

export function resolveCapabilityClientVariantView(
  mode: CapabilityClientMode,
  requestedActiveClient: CapabilityClient,
): CapabilityClientVariantView {
  const supportedClients = capabilityClientsForMode(mode);
  const activeClient = supportedClients.includes(requestedActiveClient)
    ? requestedActiveClient
    : supportedClients?.[0];
  const showClientSwitch = mode === 'PC_APP_DIFFERENT';
  return {
    mode,
    supportedClients,
    activeClient,
    showClientSwitch,
    singleClientLabel: showClientSwitch
      ? ''
      : CAPABILITY_CLIENT_MODE_OPTIONS?.find((option) => option.value === mode)?.label || '',
  };
}

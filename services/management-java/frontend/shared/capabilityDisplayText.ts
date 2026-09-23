const CAPABILITY_STATUS_TEXT: Record<string, string> = {
  DRAFT: '草稿',
  PASSED: '校验通过',
  PARTIAL: '部分通过',
  FAILED: '校验失败',
};

const CAPABILITY_SOURCE_TEXT: Record<string, string> = {
  GRPC: 'gRPC 服务',
  API_CENTER: '不支持的旧来源',
  HTTP_REQUEST: '不支持的旧来源',
  LOCAL_METHOD: '不支持的旧来源',
  MANUAL: '手动维护',
};

const SIDE_EFFECT_TEXT: Record<string, string> = {
  READ: '只读',
  WRITE: '读写',
};

function normalized(value?: string): string {
  return String(value || '')
    ?.trim()
    ?.toUpperCase?.();
}

export function capabilityStatusText(status?: string): string {
  return CAPABILITY_STATUS_TEXT[normalized(status) || 'DRAFT'] || '状态待确认';
}

export function capabilitySourceText(sourceType?: string): string {
  return CAPABILITY_SOURCE_TEXT[normalized(sourceType) || 'MANUAL'] || '其他来源';
}

export function capabilitySideEffectText(sideEffectLevel?: string): string {
  return SIDE_EFFECT_TEXT[normalized(sideEffectLevel) || 'READ'] || '未配置';
}

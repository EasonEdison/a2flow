/** Only documented, safe progress fields enter presentation state. */
export type GenerationStage = 'preparing' | 'generating' | 'validating_loading' | 'saving' | 'completed' | 'failed';
export type GenerationProgress = {
  toolCallId: string;
  name: 'generate_a2ui';
  stage: GenerationStage;
  elapsedMs: number;
  errorCode?: string;
};

export const generationStageLabels: Record<GenerationStage, string> = {
  preparing: '准备生成界面',
  generating: '生成界面',
  validating_loading: '校验并加载界面',
  saving: '保存界面',
  completed: '界面生成完成',
  failed: '界面生成失败',
};

export function parseGenerationProgress(raw: unknown, toolCallId: string, name: string): GenerationProgress | undefined {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw) || name !== 'generate_a2ui') return undefined;
  const value = raw as Record<string, unknown>;
  if (value.toolCallId !== toolCallId || value.name !== name
    || typeof value.stage !== 'string' || !Object.hasOwn(generationStageLabels, value.stage)
    || !Number.isSafeInteger(value.elapsedMs) || Number(value.elapsedMs) < 0) return undefined;
  return {
    toolCallId, name, stage: value.stage as GenerationStage, elapsedMs: Number(value.elapsedMs),
    ...(typeof value.errorCode === 'string' && /^[A-Z][A-Z0-9_]{0,95}$/.test(value.errorCode)
      ? { errorCode: value.errorCode } : {}),
  };
}

export function generationFailureDescription(code?: string): string {
  switch (code) {
    case 'A2UI_GENERATION_SOURCE_COMPONENT_UNSUPPORTED':
      return '当前卡片包含暂不支持重新排版的组件，尚未调用模型；未自动改用其他布局。';
    case 'RPC_TIMEOUT_OUTCOME_UNKNOWN':
      return '界面加载超时，结果尚未确认；未自动重试。';
    case 'RPC_EXECUTION_FAILED':
      return '界面加载未能完成；未自动重试。';
    case 'RPC_AUTHENTICATION_FAILED':
      return '当前无法验证界面加载权限；未自动重试。';
    case 'A2UI_GENERATION_RESULT_INVALID':
    case 'A2UI_GENERATION_ANCHOR_MISSING':
    case 'A2UI_GENERATION_DATA_PATH_NOT_ALLOWED':
    case 'A2UI_GENERATION_ACTION_NOT_ALLOWED':
    case 'A2UI_GENERATION_COMPONENT_NOT_ALLOWED':
      return '生成的界面未通过校验；未自动重试。';
    case 'A2UI_GENERATION_RESULT_TOO_LARGE':
    case 'A2UI_GENERATION_SIZE_LIMIT':
      return '生成的界面内容超出限制；未自动重试。';
    case 'A2UI_GENERATION_CALL_LIMIT':
      return '本轮界面生成次数已达上限。';
    default:
      return '本次未能完成界面生成；未自动重试。';
  }
}

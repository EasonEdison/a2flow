/** This delivery enables manual authoring only. Re-enable Agent authoring in a separate release. */
export const MANAGEMENT_AI_PAUSE_REASON = 'M 端 AI 辅助生成暂缓，请手动填写并保存';

export function assertManualManagementMethod(method: string): void {
  if (method.startsWith('CODING_') || method.startsWith('AUTHORING_') ||
      method === 'CAPABILITY_SKILL_CREATOR_CONTEXT') {
    throw new Error(MANAGEMENT_AI_PAUSE_REASON);
  }
}

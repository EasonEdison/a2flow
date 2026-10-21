import { generationFailureDescription } from './generationProgress';

/** Safe user-facing descriptions for persisted Chat failure codes. */
export function persistedChatErrorCode(content: unknown): string | undefined {
  if (!content || typeof content !== 'object' || Array.isArray(content)) return undefined;
  const code = (content as { errorCode?: unknown }).errorCode;
  return typeof code === 'string' && code ? code : undefined;
}

export function chatErrorPresentation(code: string | undefined): string {
  if (code && /^TEMPORARY_INTERACTION_[A-Z0-9_]+$/.test(code)) {
    return generationFailureDescription(code);
  }
  switch (code) {
    case 'CONVERSATION_BUSY':
      return '会话中已有执行，本次执行未启动；不会自动重试';
    case 'CHAT_REQUIRES_REVIEW':
    case 'CONVERSATION_REQUIRES_REVIEW':
      return '上次执行结果尚未确认，本次未继续；不会自动重试';
    case 'CHAT_CONTINUATION_UNCONFIRMED':
      return '交互已保存，助手续轮状态未确认；不会自动重试';
    case 'ARGUMENT_INVALID':
      return '工具执行被拒：参数无效';
    case 'TRANSPORT_ERROR':
      return '能力调用失败，请查看已保存状态；未自动重试';
    case 'DUPLICATE_TOOL_ARGUMENT':
      return '模型返回协议异常';
    default:
      return '其他失败';
  }
}

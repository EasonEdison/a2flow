/** Safe user-facing descriptions for persisted Chat failure codes. */
export function persistedChatErrorCode(content: unknown): string | undefined {
  if (!content || typeof content !== 'object' || Array.isArray(content)) return undefined;
  const code = (content as { errorCode?: unknown }).errorCode;
  return typeof code === 'string' && code ? code : undefined;
}

export function chatErrorPresentation(code: string | undefined): string {
  switch (code) {
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

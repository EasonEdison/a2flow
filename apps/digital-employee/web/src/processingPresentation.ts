import type { ProcessingTask, ProcessingTaskSummary } from './productApi';

export const processingStatus: Record<string, string> = {
  OPEN: '待继续处理', WAITING_INPUT: '等待补参', RESULT_RECORDED: '已有结果，待确认',
  FAILED: '执行失败', UNKNOWN: '结果待核实', RESOLVED: '本次任务已确认',
  RUNNING: '执行中', INTERRUPTED: '执行中断', RETURNED: '已返回结果',
};
export function taskState(task: ProcessingTaskSummary): string {
  if (['RESOLVED', 'UNKNOWN', 'FAILED', 'WAITING_INPUT'].includes(task.status)) return task.status;
  if (task.deliveryStatus === 'running') return 'RUNNING';
  if (task.deliveryStatus === 'failed') return 'INTERRUPTED';
  return task.status;
}
export const stateGuidance: Record<string, string> = {
  OPEN: '可回到原会话，补充下一步处理要求。',
  RUNNING: '助手正在执行或等待返回。请等待状态更新，不要重复提交。',
  WAITING_INPUT: '请在原会话填写表单，提交后自动继续同一次处理。',
  RESULT_RECORDED: '结果已保存，请核对后确认本次任务的实际完成范围。',
  INTERRUPTED: '本轮对话已中断。已保存的结果仍保留，请先核对；系统不会自动重试。',
  FAILED: '本次执行失败，请查看已保存的错误和原会话。',
  UNKNOWN: '操作可能已产生结果，当前无法确认。请先核实业务记录，不要重复提交。',
  RESOLVED: '已保存人工确认说明。原异常是否解决，以具体业务复核结论为准。',
};
type Operation = ProcessingTask['operations'][number];
const labels: Record<string, [string, string]> = {
  'content.project.create': ['创建内容项目', '已创建内容项目'],
  'content.project.get': ['查看内容项目', '已读取内容项目'],
  'content.source.save': ['保存原始素材', '已保存原始素材'],
  'content.source.get': ['核对原始素材', '已回读原始素材'],
  'content.artifact.save': ['保存内容草稿', '已保存内容草稿'],
  'content.artifact.get': ['核对内容草稿', '已回读内容草稿'],
};
const object = (value: unknown): Record<string, unknown> => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
const text = (value: unknown): string => typeof value === 'string' ? value : '';
export function operationPresentation(operation: Operation) {
  const envelope = object(operation.result);
  const output = object(envelope.output);
  const body = object(output.body);
  const returned = operation.status === 'RETURNED' && envelope.success === true;
  const label = labels[operation.abilityKey];
  const kind = text(output.kind);
  const title = text(output.title) || text(body.title) || text(object(body.manuscript).title);
  const markdown = text(output.bodyMarkdown) || text(output.body);
  const artifact = operation.abilityKey.startsWith('content.artifact.');
  const name = artifact && kind === 'MANUSCRIPT'
    ? (operation.abilityKey.endsWith('.save') ? (returned ? '已保存稿件草稿' : '保存稿件草稿') : (returned ? '已回读稿件草稿' : '核对稿件草稿'))
    : label?.[returned ? 1 : 0] || '业务操作';
  const id = text(output.id);
  const idLabel = artifact ? '稿件编号' : operation.abilityKey.startsWith('content.source.') ? '素材编号' : operation.abilityKey.startsWith('content.project.') ? '项目编号' : '结果编号';
  return { name, title, markdown, id, idLabel, audience: text(output.audience),
    revision: typeof output.revision === 'number' ? output.revision : undefined,
    returned, projectId: text(output.projectId) };
}

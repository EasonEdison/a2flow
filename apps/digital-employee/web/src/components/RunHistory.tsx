import { useState } from 'react';
import type { RunItem, Workflow } from '../productApi';

const labels: Record<string, string> = {
  PENDING: '准备中', RUNNING: '运行中', WAITING: '等待确认', SUCCEEDED: '已完成',
  FAILED: '失败', STOPPED: '已停止', SUBMITTED: '已提交', UNKNOWN: '待核对', SKIPPED: '已跳过',
};
export function displayTime(value: string): string {
  const date = new Date(value);
  return value && Number.isFinite(date.getTime())
    ? date.toLocaleString('zh-CN', { hour12: false, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : '未记录';
}
export function runDisplayName(run: RunItem, workflows: Workflow[]): string {
  return workflows.find(workflow => workflow.key === run.workflowKey)?.name
    || (run.title && run.title !== run.workflowKey ? run.title : '工作流暂不可用');
}
export function RunHistory({ runs, workflows, onOpen, hasError }: {
  runs: RunItem[]; workflows: Workflow[]; onOpen: (id: string) => void; hasError: boolean;
}) {
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('');
  const term = query.trim().toLocaleLowerCase();
  const filtered = runs.filter(run => (!status || run.status === status)
    && [runDisplayName(run, workflows), run.input, run.workflowKey].some(value => value.toLocaleLowerCase().includes(term)));
  return <section className="run-history" aria-label="运行历史">
    <div className="list-toolbar">
      <label className="search-field"><span>查找运行</span><input type="search" placeholder="工作流名称或运行内容" value={query} onChange={event => setQuery(event.target.value)} /></label>
      <label className="status-field"><span>状态</span><select value={status} onChange={event => setStatus(event.target.value)}><option value="">全部状态</option>{Object.entries(labels).map(([key, label]) => <option value={key} key={key}>{label}</option>)}</select></label>
      <span className="list-count" role="status">{filtered.length} 条记录</span>
    </div>
    <div className="history-table-wrap"><table className="history-table">
      <thead><tr><th scope="col">工作流</th><th scope="col">运行发起时间 <small>本地时间</small></th><th scope="col">状态</th><th scope="col">操作</th></tr></thead>
      <tbody>{filtered.map(run => <tr key={run.id}>
        <td data-label="工作流"><strong>{runDisplayName(run, workflows)}</strong>{run.input ? <p className="history-requirement">{run.input}</p> : null}
          <details className="history-identifiers"><summary>运行标识</summary><div>工作流：<code>{run.workflowKey}</code><br />运行记录：<code>{run.id}</code></div></details></td>
        <td data-label="运行发起时间"><time dateTime={run.createdAt || undefined}>{displayTime(run.createdAt)}</time></td>
        <td data-label="状态"><span className={'status ' + run.status.toLowerCase()}>{labels[run.status] ?? '待核对'}</span></td>
        <td data-label="操作"><button className="quiet" onClick={() => onOpen(run.id)} aria-label={'查看 ' + runDisplayName(run, workflows) + ' ' + displayTime(run.createdAt) + ' 的运行详情'}>查看详情</button></td>
      </tr>)}</tbody>
    </table></div>
    {!filtered.length && !hasError ? <div className="empty-card"><h2>{runs.length ? '没有匹配的运行' : '还没有运行记录'}</h2><p>{runs.length ? '试试其他名称或状态。' : '运行一个工作流后，可以在这里查看进展与结果。'}</p></div> : null}
  </section>;
}

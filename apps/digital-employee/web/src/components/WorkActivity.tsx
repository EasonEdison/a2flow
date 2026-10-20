import { processingStatus, taskState } from '../processingPresentation';
import { useCallback, useEffect, useRef, useState } from 'react';
import { apiErrorMessage, productApi, type ProcessingTaskSummary, type ActivityGroup, type RunReference, type WorkActivity, type WorkActivityPage } from '../productApi';
import { displayTime } from './RunHistory';
import { Icon } from './Icon';

const groups: { key: ActivityGroup; label: string; empty: string }[] = [
  { key: 'attention', label: '待你处理', empty: '暂无待处理事项' },
  { key: 'running', label: '正在运行', empty: '暂无正在运行的工作流' },
  { key: 'completed', label: '最近完成', empty: '暂无结束的运行' },
];
const statusLabels: Record<string, string> = { WAITING: '等待处理', RUNNING: '运行中', PENDING: '准备中', SUBMITTED: '已提交', SUCCEEDED: '已完成', FAILED: '失败', STOPPED: '已停止', SKIPPED: '已跳过', UNKNOWN: '待核对', UNCONFIRMED: '待核对' };
const sourceLabels = { chat: '对话发起', manual: '手动运行', scheduled: '定时触发', unknown: '来源未记录' };
type GroupState = { page: WorkActivityPage | null; cursor: string | null; previous: (string | null)[]; error: string; loading: boolean };
const initialGroup = (): GroupState => ({ page: null, cursor: null, previous: [], error: '', loading: true });

export function useWorkActivities(enabled: boolean) {
  const [state, setState] = useState<Record<ActivityGroup, GroupState>>({ attention: initialGroup(), running: initialGroup(), completed: initialGroup() });
  const [revision, setRevision] = useState(0);
  const [cursors, setCursors] = useState<Record<ActivityGroup, string | null>>({ attention: null, running: null, completed: null });
  const refresh = useCallback(() => setRevision(value => value + 1), []);
  useEffect(() => {
    if (!enabled) return;
    const abort = new AbortController();
    let inFlight = false;
    const load = async () => {
      if (document.hidden || inFlight || abort.signal.aborted) return;
      inFlight = true;
      await Promise.all(groups.map(async ({ key }) => {
        try {
          const page = await productApi.workActivities(key, cursors[key], abort.signal);
          if (!abort.signal.aborted) setState(current => ({ ...current, [key]: { ...current[key], page, cursor: cursors[key], error: '', loading: false } }));
        } catch (error) {
          if (!abort.signal.aborted) setState(current => ({ ...current, [key]: { ...current[key], error: apiErrorMessage(error, '更新失败，保留上次读取的工作动态'), loading: false } }));
        }
      }));
      inFlight = false;
    };
    void load();
    const interval = window.setInterval(() => void load(), 5000);
    const focus = () => void load();
    document.addEventListener('visibilitychange', focus);
    window.addEventListener('focus', focus);
    return () => { abort.abort(); clearInterval(interval); document.removeEventListener('visibilitychange', focus); window.removeEventListener('focus', focus); };
  }, [enabled, cursors, revision]);
  const changePage = (group: ActivityGroup, direction: 'next' | 'previous') => {
    const current = state[group];
    const cursor = direction === 'next' ? current.page?.nextCursor : current.previous.at(-1);
    if (cursor === undefined || (direction === 'next' && !cursor)) return;
    setState(all => ({ ...all, [group]: { ...all[group], loading: true,
      previous: direction === 'next' ? [...all[group].previous, all[group].cursor] : all[group].previous.slice(0, -1) } }));
    setCursors(all => ({ ...all, [group]: cursor ?? null }));
  };
  return { state, refresh, changePage, attentionCount: state.attention.page?.counts.attention ?? 0 };
}

export function ActivityDialog({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    const focused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialog?.showModal();
    return () => { dialog?.close(); if (focused?.isConnected) focused.focus(); };
  }, []);
  return <dialog ref={ref} className="activity-dialog" aria-label={title} onCancel={event => { event.preventDefault(); onClose(); }} onClick={event => { if (event.target === event.currentTarget) onClose(); }}>
    <header className="activity-dialog-header"><h2>{title}</h2><button className="quiet activity-icon-button" aria-label="关闭工作详情" onClick={onClose}><Icon name="close" /></button></header>
    <div className="activity-dialog-body">{children}</div>
  </dialog>;
}

export function WorkActivitySidebar({ state, refresh, changePage, onClose, onOpen, onReference, onProcess, onProcessingTask }: ReturnType<typeof useWorkActivities> & {
  onClose: () => void; onOpen: (item: WorkActivity) => void; onReference: (item: WorkActivity) => void; onProcess: (item: WorkActivity, attentionId: string, title: string) => void; onProcessingTask: (task: ProcessingTaskSummary) => void;
}) {
  const [acknowledging, setAcknowledging] = useState('');
  const [ackError, setAckError] = useState('');
  return <aside className="work-activity-rail" aria-label="工作动态">
    <header className="work-activity-heading"><h2>工作动态</h2><button className="quiet activity-icon-button" aria-label="收起工作动态" onClick={onClose}><Icon name="close" size={18} /></button></header>
    <div className="work-activity-scroll">
      {ackError ? <p className="inline-error" role="alert">{ackError}</p> : null}
      {groups.map(({ key, label, empty }) => {
        const group = state[key];
        return <section className={`activity-group ${key}`} key={key} aria-labelledby={`activity-group-${key}`}>
          <h3 id={`activity-group-${key}`}>{label}<span>{group.page?.counts[key] ?? '—'}</span></h3>
          {group.loading && !group.page ? <p className="activity-empty" role="status">正在读取…</p> : null}
          {group.error ? <div className="activity-sync-error" role="status"><p>{group.error}</p>{group.page?.updatedAt ? <small>上次更新 {displayTime(group.page.updatedAt)}</small> : null}<button className="quiet" onClick={refresh}>重新读取</button></div> : null}
          {group.page && !group.page.items.length && !group.error ? <p className="activity-empty">{empty}</p> : null}
          {group.page?.items.map(item => {
            const waiting = item.attentionItems.some(attention => attention.kind === 'waiting');
            const notices = item.attentionItems.filter(attention => !attention.acknowledged || attention.kind === 'business');
            return <article className="activity-row" key={item.activityId}>
              <div className="activity-row-title"><button onClick={() => onOpen(item)}>{item.workflowName || '未命名工作流'}</button><span className={`status ${item.runStatus.toLowerCase()}`}>{statusLabels[item.runStatus] ?? item.runStatus}</span></div>
              <p className="activity-meta"><span>{sourceLabels[item.sourceType] ?? '来源未记录'}</span><time dateTime={item.createdAt} title="运行发起时间（本地时间）">{displayTime(item.createdAt)}</time></p>
              {item.scheduleName ? <p className="activity-meta">计划：{item.scheduleName}</p> : null}
              {item.scheduledAt ? <p className="activity-meta">计划时间：{displayTime(item.scheduledAt)}</p> : null}
              {item.currentNode ? <p className="activity-current">当前步骤：{item.currentNode.title}</p> : null}
              {item.summary ? <p className="activity-summary">{item.summary}</p> : null}
              {notices.map(attention => <div className={`activity-attention ${attention.kind}`} key={attention.attentionId}>
                <strong>{attention.title}</strong>{attention.summary && attention.summary !== attention.title ? <p>{attention.summary}</p> : null}
                {attention.kind === 'business' ? <div className="activity-processing-actions">
                  {!attention.processingTasks?.length ? <><span className="processing-state open">待处理</span><button className="quiet" onClick={() => onProcess(item, attention.attentionId, attention.title)}>处理此异常</button></> : <>
                    {attention.processingTasks.map(task => <button className="activity-processing-task" key={task.taskId} onClick={() => onProcessingTask(task)} aria-label={`查看处理记录：${processingStatus[taskState(task)] || '状态待核实'}`}>
                      <span className={`processing-state ${taskState(task).toLowerCase()}`}>{processingStatus[taskState(task)] || '状态待核实'}</span>
                      <span className="processing-task-caption">{task.resolutionSummary || '查看进展与处理结果'}</span>
                      <small>{displayTime(task.updatedAt)} · {taskState(task) === 'WAITING_INPUT' ? '去补参 →' : '查看处理 →'}</small>
                    </button>)}
                    <button className="quiet" onClick={() => onProcess(item, attention.attentionId, attention.title)}>发起另一项处理</button>
                  </>}
                </div> : null}
                {attention.acknowledged ? <small>已查看 · 不代表业务已处理</small> : attention.kind !== 'waiting' ? <button className="quiet" disabled={Boolean(acknowledging)} onClick={async () => {
                  setAcknowledging(attention.attentionId); setAckError('');
                  try { await productApi.acknowledgeActivity(item.activityId, attention.attentionId); refresh(); }
                  catch (error) { setAckError(apiErrorMessage(error, '标记未成功，请重新读取确认状态')); }
                  finally { setAcknowledging(''); }
                }}>{acknowledging === attention.attentionId ? '正在保存…' : '已查看'}</button> : null}
              </div>)}
              <div className="activity-actions"><button className={waiting ? 'primary' : 'secondary'} onClick={() => onOpen(item)}>{waiting ? '去处理' : key === 'running' ? '查看进度' : '查看结果'}</button><button className="quiet" onClick={() => onReference(item)}>在对话中继续</button></div>
            </article>;
          })}
          {group.previous.length || group.page?.nextCursor ? <nav className="activity-pagination" aria-label={`${label}分页`}><button className="quiet" disabled={!group.previous.length || group.loading} onClick={() => changePage(key, 'previous')}>上一页</button><span>第 {group.previous.length + 1} 页</span><button className="quiet" disabled={!group.page?.nextCursor || group.loading} onClick={() => changePage(key, 'next')}>下一页</button></nav> : null}
        </section>;
      })}
    </div>
  </aside>;
}

export function RunReferenceChips({ references, onRemove, onOpen }: { references: RunReference[]; onRemove?: (id: string) => void; onOpen?: (id: string) => void }) {
  if (!references.length) return null;
  return <div className="run-reference-chips" aria-label={onRemove ? '待发送的运行引用' : '本条消息引用的运行'}>{references.map(reference => <span className="run-reference-chip" key={reference.activityId}>
    <Icon name="workflow" size={15} />
    <button type="button" className="reference-label" onClick={() => onOpen?.(reference.activityId)} disabled={!onOpen} title={`${reference.workflowName} · ${displayTime(reference.createdAt)}`}><span>已引用：{reference.workflowName}</span><small>{displayTime(reference.createdAt)}</small></button>
    {onRemove ? <button type="button" className="reference-remove" aria-label={`移除引用 ${reference.workflowName}`} onClick={() => onRemove(reference.activityId)}><Icon name="close" size={14} /></button> : null}
  </span>)}</div>;
}

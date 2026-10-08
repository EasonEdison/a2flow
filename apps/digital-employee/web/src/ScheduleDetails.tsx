import { useEffect, useState } from 'react';
import './schedule-details.css';
import { apiErrorMessage, productApi, type Schedule, type ScheduleRun } from './productApi';

const lifecycleLabels: Record<string, string> = {
  PENDING: '准备执行', RUNNING: '运行中', WAITING: '等待确认', SUCCEEDED: '已完成',
  FAILED: '执行失败', STOPPED: '已停止', UNKNOWN: '执行状态待确认', SKIPPED: '已跳过',
};
const deliveryLabels: Record<string, string> = {
  pending: '等待投递', published: '等待消费', dispatching: '启动中',
  completed: '已接纳，等待运行关联', unknown: '投递结果待确认',
};

export function scheduleRunLabel(run: ScheduleRun): string {
  if (run.lifecycle) return lifecycleLabels[run.lifecycle] ?? '执行状态待确认';
  return deliveryLabels[run.deliveryState] ?? '投递状态待确认';
}

export function scheduleTime(value: string, timezone: string): string {
  return value ? new Date(value).toLocaleString('zh-CN', { timeZone: timezone, hour12: false }) : '暂无';
}

export function ScheduleEditor({ item, onSave, onCancel }: {
  item: Schedule; onSave: () => Promise<void>; onCancel: () => void;
}) {
  const [expression, setExpression] = useState(item.expression);
  const [timezone, setTimezone] = useState(item.timezone);
  const [input, setInput] = useState(item.input);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  return <section className="schedule-editor" aria-label="编辑定时任务">
    <h3>编辑定时任务</h3>
    <p>仅影响后续触发，不修改已入队或已启动运行的输入；保存不会自动启用任务。</p>
    <form onSubmit={(event) => {
      event.preventDefault();
      if (saving) return;
      if (expression.trim().split(/\s+/).length !== 5) { setError('Cron 需要五个字段：分 时 日 月 周。'); return; }
      setSaving(true); setError('');
      void productApi.updateSchedule(item.id, { expression: expression.trim(), timezone: timezone.trim(), input })
        .then(onSave).catch((reason) => setError(apiErrorMessage(reason, '保存失败，请检查 Cron 和时区。')))
        .finally(() => setSaving(false));
    }}>
      <label>Cron 表达式<input required maxLength={128} value={expression} onChange={(event) => setExpression(event.target.value)} /></label>
      <label>时区<input required maxLength={64} value={timezone} onChange={(event) => setTimezone(event.target.value)} /></label>
      <label>执行输入<textarea required maxLength={4000} value={input} onChange={(event) => setInput(event.target.value)} /></label>
      {error ? <p role="alert" className="inline-error">{error}</p> : null}
      <div className="schedule-actions"><button className="primary" disabled={saving}>{saving ? '正在保存…' : '保存修改'}</button><button type="button" className="secondary" disabled={saving} onClick={onCancel}>取消</button></div>
    </form>
  </section>;
}

export function ScheduleHistory({ item, onRun }: { item: Schedule; onRun: (id: string) => void }) {
  const [runs, setRuns] = useState<ScheduleRun[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    void productApi.scheduleRuns(item.id).then((result) => {
      if (active) { setRuns(result.runs); setCursor(result.nextCursor); }
    }).catch((reason) => { if (active) setError(apiErrorMessage(reason, '运行记录加载失败。')); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [item.id]);
  return <section className="schedule-history" aria-label="关联运行">
    <h3>关联运行</h3><p>按触发时间倒序。消息投递完成不代表工作流执行成功。</p>
    {runs.map((run) => <div className="schedule-history-item" key={run.controlId}>
      <div><strong>{scheduleTime(run.scheduledAt, item.timezone)}</strong> <span>{scheduleRunLabel(run)}</span></div>
      <details><summary>本次执行输入</summary><p className="schedule-snapshot">{run.inputText}</p></details>
      {run.runId ? <button className="secondary" onClick={() => onRun(run.controlId)}>查看运行</button> : <small>尚未关联运行</small>}
    </div>)}
    {!loading && !error && !runs.length ? <p>尚未触发运行</p> : null}
    {error ? <p className="inline-error" role="alert">{error}</p> : null}
    {loading ? <p role="status">正在加载运行记录…</p> : null}
    {cursor ? <button className="secondary" disabled={loading} onClick={() => {
      setLoading(true); setError('');
      void productApi.scheduleRuns(item.id, cursor).then((result) => {
        setRuns((previous) => [...previous, ...result.runs]); setCursor(result.nextCursor);
      }).catch((reason) => setError(apiErrorMessage(reason, '运行记录加载失败。'))).finally(() => setLoading(false));
    }}>加载更早记录</button> : null}
  </section>;
}

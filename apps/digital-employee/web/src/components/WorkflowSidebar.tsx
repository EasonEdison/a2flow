import type { RunView } from '../presentation';
import { statusLabels } from '../presentation';
import { Icon } from './Icon';

export function WorkflowSidebar({ run, onNew, fixture = false }: {
  run: RunView | null;
  onNew: () => void;
  fixture?: boolean;
}) {
  const nodes = run?.nodes ?? [
    { id: 'planning', title: '活动策划', status: 'PENDING' as const },
    { id: 'copy', title: '宣传文案', status: 'PENDING' as const },
  ];
  return <aside className="workflow-sidebar">
    <div className="sidebar-heading"><Icon name="workflow" /><h2>本次 Workflow</h2></div>
    <p className="muted">活动策划 → 宣传文案</p>
    <ol className="timeline">{nodes.map((node, index) =>
      <li key={node.id} className={'state-' + node.status.toLowerCase()}>
        <a href={'#node-' + node.id}>
          <span className="step-number">{node.status === 'SUCCEEDED' ? <Icon name="check" size={16} /> : index + 1}</span>
          <span><strong>{node.title}</strong><small>{statusLabels[node.status]}</small></span>
        </a>
      </li>)}</ol>
    <div className="sidebar-note">
      <h3>{fixture ? '本地交互演示' : '每一步，都有记录'}</h3>
      <p>{fixture ? '选择方案只改变本地示例状态；刷新会重置，不会启动模型或业务调用。' : '活动方案确认后，继续生成宣传文案。刷新页面可查看原有进度与卡片。'}</p>
    </div>
    <button className="secondary full" onClick={onNew}>开始新的策划</button>
  </aside>;
}

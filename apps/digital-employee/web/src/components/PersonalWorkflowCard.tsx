import { useId, useState } from 'react';
import type { PersonalWorkflow } from '../personalWorkflow';

export function PersonalWorkflowSteps({ workflow }: { workflow: PersonalWorkflow }) {
  return <ol className="personal-workflow-steps">{workflow.nodes.map(node => <li key={node.nodeId}>
    <span>{node.displayName || (node.type === 'SKILL' ? node.skillKey : node.abilityKey)}</span>
    <small>{node.type === 'SKILL' ? '技能' : '业务能力'}</small>
  </li>)}<li><span>流程总结</span></li></ol>;
}

export function PersonalWorkflowCard({ workflow, disabled, onRun, onOpenWorkflows }: {
  workflow: PersonalWorkflow;
  disabled: boolean;
  onRun: (workflow: PersonalWorkflow, requirement: string) => Promise<void>;
  onOpenWorkflows: () => void;
}) {
  const inputId = useId();
  const [requirement, setRequirement] = useState(workflow.defaultRequirement);
  return <section className="personal-workflow-card" aria-label="已创建的工作流">
    <p className="personal-workflow-saved">已保存到我的工作流</p>
    <h3>{workflow.name}</h3>
    <PersonalWorkflowSteps workflow={workflow} />
    <p className="muted">创建不会自动启动运行。你可以修改本次要求后运行。</p>
    <label htmlFor={inputId}>本次运行要求</label>
    <textarea id={inputId} value={requirement} maxLength={2000} disabled={disabled}
      onChange={event => setRequirement(event.target.value)} />
    <div className="personal-workflow-actions">
      <button type="button" className="primary" disabled={disabled || !requirement.trim()}
        onClick={() => void onRun(workflow, requirement)}>运行工作流</button>
      <button type="button" className="secondary" onClick={onOpenWorkflows}>查看我的工作流</button>
    </div>
  </section>;
}

import React, { useMemo } from 'react';
import {
  Alert,
  Button,
  Checkbox,
  Empty,
  Input,
  Modal,
  Select,
  Space,
  Typography,
  message,
} from 'antd';
import {
  deleteWorkflowSkillNode,
  getWorkflowSkillNodeActionState,
  moveWorkflowSkillNode,
  updateWorkflowEdge,
  updateWorkflowNode,
  updateWorkflowSkillSelection,
  WORKFLOW_DETAIL_SUMMARY_PROMPT_MAX_LENGTH,
  WORKFLOW_QUICK_TRIGGER_MESSAGE_MAX_LENGTH,
  WORKFLOW_SUMMARY_ADVICE_MAX_COUNT,
  WORKFLOW_SUMMARY_ADVICE_TEXT_MAX_LENGTH,
  WORKFLOW_SUMMARY_TITLE,
} from './model';
import { ArrowDownOutlined, ArrowUpOutlined, DeleteOutlined } from '@ant-design/icons';
import RouterNodeInspector from './WorkflowRouterInspector';
import ParallelForkInspector from './WorkflowParallelInspector';
import type {
  WorkflowDraft,
  WorkflowEdge,
  WorkflowHandlingSuggestion,
  WorkflowNode,
  WorkflowSkillNode,
  WorkflowSkillOption,
  WorkflowValidationIssue,
} from './types';

const { Text } = Typography;
const { TextArea } = Input;

interface WorkflowInspectorProps {
  draft?: WorkflowDraft;
  selectedNodeCode?: string;
  specialistCode?: string;
  skills: WorkflowSkillOption[];
  issues: WorkflowValidationIssue[];
  readonly: boolean;
  onChange: (draft: WorkflowDraft) => void;
}

interface NodePanelProps {
  draft: WorkflowDraft;
  node: WorkflowNode;
  readonly: boolean;
  targetOptions: Array<{ value: string; label: string }>;
  onChange: (draft: WorkflowDraft) => void;
}

const nodeTitle: Record<WorkflowNode['nodeType'], string> = {
  SKILL: 'Skill 节点配置',
  ROUTER: 'Router 节点配置',
  PARALLEL_FORK: 'Parallel Fork 配置',
  PARALLEL_JOIN: 'Parallel Join 配置',
  SUMMARY: 'Summary 配置',
};

const STORE_MANAGER_SPECIALIST_CODE = '1';

const changeNode = (
  draft: WorkflowDraft,
  nodeCode: string,
  readonly: boolean,
  onChange: (draft: WorkflowDraft) => void,
  updater: (node: WorkflowNode) => WorkflowNode,
) => {
  if (!readonly) onChange(updateWorkflowNode(draft, nodeCode, updater));
};

const NodeNameField: React.FC<NodePanelProps> = ({ draft, node, readonly, onChange }) => (
  <label>
    <span>节点名称（可选）</span>
    <Input
      disabled={readonly}
      value={node.displayName || ''}
      onChange={(event) =>
        changeNode(draft, node.nodeCode, readonly, onChange, (current) => ({
          ...current,
          displayName: event.target.value,
        }))
      }
    />
  </label>
);

const NormalSuccessorField: React.FC<NodePanelProps> = ({
  draft,
  node,
  readonly,
  targetOptions,
  onChange,
}) => {
  const edge = draft.edges?.find?.(
    (item) => item.edgeType === 'NORMAL' && item.sourceNodeCode === node.nodeCode,
  );
  if (!edge) return null;
  const update = (current: WorkflowEdge): WorkflowEdge => ({
    ...current,
    targetNodeCode: edge.targetNodeCode,
  });
  return (
    <label>
      <span>固定后继</span>
      <Select
        disabled={readonly}
        value={edge.targetNodeCode || undefined}
        options={targetOptions}
        onChange={(value) => {
          if (!readonly) {
            onChange(
              updateWorkflowEdge(draft, edge.edgeId, (current) => ({
                ...update(current),
                targetNodeCode: value,
              })),
            );
          }
        }}
      />
    </label>
  );
};

const SkillNodeInspector: React.FC<
  NodePanelProps & {
    node: WorkflowSkillNode;
    skills: WorkflowSkillOption[];
    skillLabel: string;
  }
> = ({ draft, node, skills, skillLabel, readonly, targetOptions, onChange }) => {
  const selectedSkill = skills.find((skill) => skill.skillCode === node.skillCode);
  const actionState = useMemo(
    () => getWorkflowSkillNodeActionState(draft, node.nodeCode),
    [draft, node.nodeCode],
  );
  const update = (patch: Partial<WorkflowSkillNode>) =>
    changeNode(draft, node.nodeCode, readonly, onChange, (current) =>
      current.nodeType === 'SKILL' ? { ...current, ...patch } : current,
    );
  const move = (direction: 'UP' | 'DOWN') => {
    if (readonly) return;
    const result = moveWorkflowSkillNode(draft, node.nodeCode, direction);
    if (result.ok) onChange(result.draft);
    else message.warning(result.reason);
  };
  const confirmDelete = () => {
    if (readonly || !actionState.delete?.enabled) return;
    Modal.confirm({
      title: '删除 Skill 节点',
      content: `确认删除“${node.displayName || node.nodeCode}”并重新连接前后节点？`,
      okText: '确认删除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: () => {
        const result = deleteWorkflowSkillNode(draft, node.nodeCode);
        if (result.ok) onChange(result.draft);
        else message.warning(result.reason);
      },
    });
  };
  return (
    <>
      <NodeNameField {...{ draft, node, readonly, targetOptions, onChange }} />
      <Space wrap>
        <Button
          size="small"
          icon={<ArrowUpOutlined />}
          disabled={readonly || !actionState.moveUp?.enabled}
          title={actionState.moveUp?.reason}
          onClick={() => move('UP')}
        >
          上移
        </Button>
        <Button
          size="small"
          icon={<ArrowDownOutlined />}
          disabled={readonly || !actionState.moveDown?.enabled}
          title={actionState.moveDown?.reason}
          onClick={() => move('DOWN')}
        >
          下移
        </Button>
        <Button
          danger
          size="small"
          icon={<DeleteOutlined />}
          disabled={readonly || !actionState.delete?.enabled}
          title={actionState.delete?.reason}
          onClick={confirmDelete}
        >
          删除
        </Button>
      </Space>
      <label>
        <span>{skillLabel}</span>
        <Select
          disabled={readonly}
          showSearch
          optionFilterProp="label"
          value={node.skillCode || undefined}
          options={skills.map((skill) => ({
            value: skill.skillCode,
            label: `${skill.displayName} · ${skill.status} · ${skill.skillCode}`,
          }))}
          onChange={(value) => onChange(updateWorkflowSkillSelection(draft, node.nodeCode, value))}
        />
      </label>
      {selectedSkill ? (
        <Text type="secondary">
          {selectedSkill.status} · {selectedSkill.description || '暂无描述'}
        </Text>
      ) : null}
      <label>
        <span>一键触发 Skill（可选）</span>
        <TextArea
          disabled={readonly}
          rows={3}
          maxLength={WORKFLOW_QUICK_TRIGGER_MESSAGE_MAX_LENGTH}
          value={node.quickTriggerMessage || ''}
          placeholder="例如：查询当前店铺最近的处罚记录"
          onChange={(event) => update({ quickTriggerMessage: event.target.value || undefined })}
        />
        <Text type="secondary">
          点击后会作为普通消息发送到当前对话，由现有对话路由判断命中的 Skill；最多{' '}
          {WORKFLOW_QUICK_TRIGGER_MESSAGE_MAX_LENGTH} 个字符。
        </Text>
      </label>
      <label>
        <span>节点任务 Prompt</span>
        <TextArea
          disabled={readonly}
          rows={7}
          value={node.nodePrompt}
          placeholder="具体任务描述，不需要重复 Skill 名称"
          onChange={(event) => update({ nodePrompt: event.target.value })}
        />
      </label>
      <Checkbox
        disabled={readonly}
        checked={node.controlPolicy?.allowSkip}
        onChange={(event) => update({ controlPolicy: { allowSkip: event.target.checked } })}
      >
        是否允许跳过此节点
      </Checkbox>
      <NormalSuccessorField {...{ draft, node, readonly, targetOptions, onChange }} />
      <Alert type="info" showIcon message="仅保存稳定 skillCode，不保存 Skill 版本、包或内容。" />
    </>
  );
};

const JoinNodeInspector: React.FC<NodePanelProps> = (props) => {
  const { draft, node, readonly, onChange } = props;
  if (node.nodeType !== 'PARALLEL_JOIN') return null;
  const forkOptions = draft?.nodes
    ?.filter?.((item) => item.nodeType === 'PARALLEL_FORK')
    ?.map?.((item) => ({
      value: item.nodeCode,
      label: item.displayName || item.nodeCode,
    }));
  return (
    <>
      <NodeNameField {...props} />
      <label>
        <span>匹配 Fork</span>
        <Select
          disabled={readonly}
          value={node.matchingNodeCode || undefined}
          options={forkOptions}
          onChange={(value) =>
            changeNode(draft, node.nodeCode, readonly, onChange, (current) =>
              current.nodeType === 'PARALLEL_JOIN'
                ? { ...current, matchingNodeCode: value }
                : current,
            )
          }
        />
      </label>
      <Text type="secondary">joinPolicy（只读）：{node.joinPolicy}</Text>
      <NormalSuccessorField {...props} />
    </>
  );
};

const SummaryNodeInspector: React.FC<NodePanelProps> = (props) => {
  const { draft, node, readonly, onChange } = props;
  if (node.nodeType !== 'SUMMARY') return null;
  const suggestions = draft.summaryConfig?.handlingSuggestions;
  const updateSuggestions = (next: WorkflowHandlingSuggestion[]) => {
    if (readonly) return;
    onChange({
      ...draft,
      summaryConfig: {
        ...draft.summaryConfig,
        handlingSuggestions: next,
      },
    });
  };
  const updateSuggestion = (index: number, patch: Partial<WorkflowHandlingSuggestion>) =>
    updateSuggestions(
      suggestions.map((suggestion, suggestionIndex) =>
        suggestionIndex === index ? { ...suggestion, ...patch } : suggestion,
      ),
    );
  return (
    <>
      <label>
        <span>结论标题（固定）</span>
        <Input disabled value={WORKFLOW_SUMMARY_TITLE} />
      </label>
      <label>
        <span>Summary Prompt</span>
        <TextArea
          disabled={readonly}
          rows={10}
          value={node.prompt}
          placeholder="描述所有节点完成后要生成的最终总结"
          onChange={(event) =>
            changeNode(draft, node.nodeCode, readonly, onChange, (current) =>
              current.nodeType === 'SUMMARY' ? { ...current, prompt: event.target.value } : current,
            )
          }
        />
      </label>
      <label>
        <span>Detail Summary Prompt（可选）</span>
        <TextArea
          disabled={readonly}
          rows={8}
          maxLength={WORKFLOW_DETAIL_SUMMARY_PROMPT_MAX_LENGTH}
          value={draft.summaryConfig?.detailSummaryPrompt || ''}
          placeholder="生成供用户查看的完整诊断与详细建议"
          onChange={(event) => {
            if (readonly) return;
            onChange({
              ...draft,
              summaryConfig: {
                ...draft.summaryConfig,
                detailSummaryPrompt: event.target.value || undefined,
              },
            });
          }}
        />
        <Text type="secondary">配置后，运行到总结节点时会与简版总结并行生成。</Text>
      </label>
      <div>
        <Space>
          <Text strong>处理建议</Text>
          <Text type="secondary">最多 {WORKFLOW_SUMMARY_ADVICE_MAX_COUNT} 条</Text>
        </Space>
        {suggestions.map((suggestion, index) => (
          <div key={`${suggestion.suggestionId}-${index}`}>
            <label>
              <span>建议标识</span>
              <Input
                disabled={readonly}
                value={suggestion.suggestionId}
                onChange={(event) => updateSuggestion(index, { suggestionId: event.target.value })}
              />
            </label>
            <label>
              <span>图标 URL（可选）</span>
              <Input
                disabled={readonly}
                value={suggestion.iconUrl || ''}
                onChange={(event) =>
                  updateSuggestion(index, {
                    iconUrl: event.target.value || undefined,
                  })
                }
              />
            </label>
            <label>
              <span>展示文案</span>
              <TextArea
                disabled={readonly}
                rows={3}
                maxLength={WORKFLOW_SUMMARY_ADVICE_TEXT_MAX_LENGTH}
                value={suggestion.displayText}
                onChange={(event) => updateSuggestion(index, { displayText: event.target.value })}
              />
            </label>
            <label>
              <span>发送消息</span>
              <TextArea
                disabled={readonly}
                rows={3}
                maxLength={WORKFLOW_SUMMARY_ADVICE_TEXT_MAX_LENGTH}
                value={suggestion.sendMessageText}
                onChange={(event) =>
                  updateSuggestion(index, {
                    sendMessageText: event.target.value,
                  })
                }
              />
            </label>
            <Button
              danger
              size="small"
              disabled={readonly}
              onClick={() =>
                updateSuggestions(
                  suggestions.filter((_, suggestionIndex) => suggestionIndex !== index),
                )
              }
            >
              删除建议
            </Button>
          </div>
        ))}
        <Button
          disabled={readonly || suggestions.length >= WORKFLOW_SUMMARY_ADVICE_MAX_COUNT}
          onClick={() =>
            updateSuggestions([
              ...suggestions,
              {
                suggestionId: '',
                displayText: '',
                sendMessageText: '',
              },
            ])
          }
        >
          新增处理建议
        </Button>
      </div>
      <Text type="secondary">allowSkip（只读）：false</Text>
    </>
  );
};

const WorkflowInspector: React.FC<WorkflowInspectorProps> = ({
  draft,
  selectedNodeCode,
  specialistCode,
  skills,
  issues,
  readonly,
  onChange,
}) => {
  const skillLabel =
    specialistCode?.trim() === STORE_MANAGER_SPECIALIST_CODE ? '全部 Skill' : '同专员 Skill';
  const node = draft?.nodes.find((item) => item.nodeCode === selectedNodeCode);
  const targetOptions = useMemo(
    () =>
      (draft?.nodes || [])
        .filter((item) => item.nodeCode !== selectedNodeCode)
        .map((item) => ({
          value: item.nodeCode,
          label: `${item.displayName || item.nodeCode} · ${item.nodeType}`,
        })),
    [draft?.nodes, selectedNodeCode],
  );

  if (!draft || !node) {
    return (
      <aside className="workflow-inspector-panel">
        <Empty description="请选择节点" />
      </aside>
    );
  }
  const props = { draft, node, readonly, targetOptions, onChange };
  const nodeIssues = issues.filter(
    (issue) => issue.nodeCode === node.nodeCode || issue.path?.includes?.(node.nodeCode),
  );
  return (
    <aside className="workflow-inspector-panel">
      <div className="workflow-panel-heading inspector">
        <div>
          <Text strong>{nodeTitle[node.nodeType]}</Text>
          <Text type="secondary">{node.nodeCode}</Text>
        </div>
      </div>
      <div className="workflow-inspector-form">
        {node.nodeType === 'SKILL' ? (
          <SkillNodeInspector {...props} node={node} skills={skills} skillLabel={skillLabel} />
        ) : null}
        {node.nodeType === 'ROUTER' ? <RouterNodeInspector {...props} node={node} /> : null}
        {node.nodeType === 'PARALLEL_FORK' ? (
          <ParallelForkInspector {...props} node={node} />
        ) : null}
        {node.nodeType === 'PARALLEL_JOIN' ? <JoinNodeInspector {...props} /> : null}
        {node.nodeType === 'SUMMARY' ? <SummaryNodeInspector {...props} /> : null}
      </div>
      {nodeIssues.length ? (
        <div className="workflow-validation-panel">
          <strong>当前节点问题</strong>
          <ul>
            {nodeIssues.map((issue, index) => (
              <li key={`${issue.path}-${index}`}>{issue.message}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </aside>
  );
};

export default WorkflowInspector;

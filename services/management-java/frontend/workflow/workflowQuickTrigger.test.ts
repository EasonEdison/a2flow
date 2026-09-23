import { strict as assert } from 'assert';
import { readFileSync } from 'fs';
import { resolve } from 'path';
import { createWorkflowDraft, normalizeWorkflowDraft, updateWorkflowSkillSelection } from './model';
import type { WorkflowDraft, WorkflowSkillNode } from './types';
import { validateWorkflowDraft } from './workflowValidation';

const skillNode = (draft: WorkflowDraft): WorkflowSkillNode => {
  const node = draft.nodes?.find?.(
    (candidate): candidate is WorkflowSkillNode => candidate.nodeType === 'SKILL',
  );
  if (!node) throw new Error('expected a Skill node');
  return node;
};

const source = createWorkflowDraft('wf_quick_trigger_test');
assert.equal(source.snapshotContractVersion, 2, 'new drafts are v2-only');
assert.throws(
  () =>
    normalizeWorkflowDraft({
      ...source,
      snapshotContractVersion: 1,
    } as unknown as WorkflowDraft),
  /snapshotContractVersion仅支持v2/,
  'frontend reader fails closed for legacy Workflow drafts',
);

const withMessage = {
  ...source,
  nodes: source.nodes?.map?.((node) =>
    node.nodeType === 'SKILL' ? { ...node, quickTriggerMessage: '  查询最近处罚记录  ' } : node,
  ),
} as WorkflowDraft;
const normalized = normalizeWorkflowDraft(withMessage);
assert.equal(
  skillNode(normalized)?.quickTriggerMessage,
  '查询最近处罚记录',
  'normalization trims the optional message',
);

const blank = normalizeWorkflowDraft({
  ...withMessage,
  nodes: withMessage.nodes?.map?.((node) =>
    node.nodeType === 'SKILL' ? { ...node, quickTriggerMessage: '   ' } : node,
  ),
});
assert.equal(
  Object.prototype.hasOwnProperty.call(skillNode(blank), 'quickTriggerMessage'),
  false,
  'blank input is omitted instead of persisted',
);

const changedSkill = updateWorkflowSkillSelection(
  normalized,
  skillNode(normalized)?.nodeCode,
  'skill_changed',
);
assert.equal(skillNode(changedSkill)?.skillCode, 'skill_changed');
assert.equal(
  Object.prototype.hasOwnProperty.call(skillNode(changedSkill), 'quickTriggerMessage'),
  false,
  'changing skillCode clears the previous Skill wording',
);

const tooLong = normalizeWorkflowDraft({
  ...source,
  nodes: source.nodes?.map?.((node) =>
    node.nodeType === 'SKILL' ? { ...node, quickTriggerMessage: 'x'.repeat(4097) } : node,
  ),
} as WorkflowDraft);
assert.equal(
  validateWorkflowDraft(tooLong)?.some?.(
    (issue) => issue.path === `nodes.${skillNode(tooLong)?.nodeCode}.quickTriggerMessage`,
  ),
  true,
  'frontend reports the stable field path for overlong input',
);

const workflowRoot = resolve(process.cwd(), 'workflow');
const inspectorSource = readFileSync(resolve(workflowRoot, 'WorkflowInspector.tsx'), 'utf8');
assert.equal(inspectorSource.includes('一键触发 Skill'), true);
assert.equal(
  inspectorSource.includes('maxLength={WORKFLOW_QUICK_TRIGGER_MESSAGE_MAX_LENGTH}'),
  true,
);
assert.equal(
  inspectorSource.indexOf('一键触发 Skill') < inspectorSource.indexOf('节点任务 Prompt'),
  true,
  'quick trigger textarea appears before nodePrompt',
);
assert.equal(
  inspectorSource.includes('点击后会作为普通消息发送到当前对话'),
  true,
  'copy does not promise a hard-bound Skill invocation',
);

console.log('workflowQuickTrigger.test.ts PASS');

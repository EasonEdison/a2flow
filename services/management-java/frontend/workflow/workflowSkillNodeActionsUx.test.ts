import { strict as assert } from 'assert';
import { readFileSync } from 'fs';
import { resolve } from 'path';

const workflowRoot = resolve(process.cwd(), 'workflow');
const inspectorSource = readFileSync(resolve(workflowRoot, 'WorkflowInspector.tsx'), 'utf8');
const pageSource = readFileSync(resolve(workflowRoot, 'WorkflowOrchestrationPage.tsx'), 'utf8');

assert.equal(
  inspectorSource.includes('getWorkflowSkillNodeActionState'),
  true,
  'Skill inspector consumes fail-closed action availability',
);
assert.equal(
  inspectorSource.includes('moveWorkflowSkillNode'),
  true,
  'Skill inspector moves graph topology',
);
assert.equal(
  inspectorSource.includes('deleteWorkflowSkillNode'),
  true,
  'Skill inspector deletes through model',
);
assert.equal(inspectorSource.includes('上移'), true, 'Skill inspector renders move-up action');
assert.equal(inspectorSource.includes('下移'), true, 'Skill inspector renders move-down action');
assert.equal(inspectorSource.includes('删除'), true, 'Skill inspector renders delete action');
assert.equal(
  inspectorSource.includes('Modal.confirm'),
  true,
  'Skill deletion requires confirmation',
);
assert.equal(
  inspectorSource.includes('okButtonProps: { danger: true }'),
  true,
  'confirmation marks destructive action',
);
assert.equal(
  pageSource.includes('!draft.nodes.some((node) => node.nodeCode === selectedNodeCode)'),
  true,
  'page repairs selection after selected Skill deletion',
);

console.log('workflowSkillNodeActionsUx.test.ts PASS');

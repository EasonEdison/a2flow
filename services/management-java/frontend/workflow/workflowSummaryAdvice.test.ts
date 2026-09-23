import { strict as assert } from 'assert';
import { readFileSync } from 'fs';
import { resolve } from 'path';
import {
  createWorkflowDraft,
  normalizeWorkflowDraft,
  serializeWorkflowDraft,
  WORKFLOW_SUMMARY_ADVICE_MAX_COUNT,
  WORKFLOW_SUMMARY_ADVICE_TEXT_MAX_LENGTH,
} from './model';
import type { WorkflowDraft, WorkflowSummaryConfig, WorkflowSummaryNode } from './types';
import { validateWorkflowDraft } from './workflowValidation';

const summaryNode = (draft: WorkflowDraft): WorkflowSummaryNode => {
  const node = draft.nodes?.find?.(
    (candidate): candidate is WorkflowSummaryNode => candidate.nodeType === 'SUMMARY',
  );
  if (!node) throw new Error('expected a Summary node');
  return node;
};

const source = createWorkflowDraft('wf_summary_advice_test');
assert.equal(summaryNode(source)?.displayName, '经营问题结论');
assert.deepEqual(source.summaryConfig?.handlingSuggestions, []);

type DetailSummaryConfig = WorkflowSummaryConfig & {
  detailSummaryPrompt?: string;
};
const detailDraft = JSON.parse(JSON.stringify(source)) as WorkflowDraft;
(detailDraft.summaryConfig as DetailSummaryConfig).detailSummaryPrompt = '  生成完整诊断建议  ';
const normalizedDetail = normalizeWorkflowDraft(detailDraft);
assert.equal(
  (normalizedDetail.summaryConfig as DetailSummaryConfig)?.detailSummaryPrompt,
  '生成完整诊断建议',
  'optional detail Summary Prompt is trimmed and retained in V2',
);
const serializedDetail = JSON.parse(serializeWorkflowDraft(normalizedDetail));
assert.equal(
  serializedDetail.snapshotContractVersion,
  2,
  'detail Summary Prompt does not upgrade the snapshot contract',
);
assert.equal(serializedDetail.summaryConfig?.detailSummaryPrompt, '生成完整诊断建议');

const blankDetailDraft = JSON.parse(JSON.stringify(source)) as WorkflowDraft;
(blankDetailDraft.summaryConfig as DetailSummaryConfig).detailSummaryPrompt = '   ';
assert.equal(
  Object.prototype.hasOwnProperty.call(
    normalizeWorkflowDraft(blankDetailDraft)?.summaryConfig,
    'detailSummaryPrompt',
  ),
  false,
  'blank optional detail Summary Prompt is omitted',
);

const overlongDetailDraft = JSON.parse(JSON.stringify(source)) as WorkflowDraft;
(overlongDetailDraft.summaryConfig as DetailSummaryConfig).detailSummaryPrompt = 'x'.repeat(4097);
assert.equal(
  validateWorkflowDraft(overlongDetailDraft)?.some?.(
    (issue) => issue.path === 'summaryConfig.detailSummaryPrompt',
  ),
  true,
  'overlong detail Summary Prompt is rejected with a stable path',
);

const normalized = normalizeWorkflowDraft({
  ...source,
  summaryConfig: {
    ...source.summaryConfig,
    handlingSuggestions: [
      {
        suggestionId: '  consult_service  ',
        iconUrl: '  https://example.invalid/REQUIRES_CONFIGURATION  ',
        displayText: '  联系客服处理  ',
        sendMessageText: '  帮我联系人工客服处理这个经营问题  ',
      },
      {
        suggestionId: '  retry_analysis  ',
        iconUrl: '   ',
        displayText: '  重新分析  ',
        sendMessageText: '  请重新执行本次经营分析  ',
      },
    ],
  },
});
assert.deepEqual(normalized.summaryConfig?.handlingSuggestions, [
  {
    suggestionId: 'consult_service',
    iconUrl: 'https://example.invalid/REQUIRES_CONFIGURATION',
    displayText: '联系客服处理',
    sendMessageText: '帮我联系人工客服处理这个经营问题',
  },
  {
    suggestionId: 'retry_analysis',
    displayText: '重新分析',
    sendMessageText: '请重新执行本次经营分析',
  },
]);
assert.deepEqual(
  JSON.parse(serializeWorkflowDraft(normalized)).summaryConfig,
  normalized.summaryConfig,
  'serialized draft freezes the complete typed Summary config',
);

const invalid = normalizeWorkflowDraft({
  ...source,
  summaryConfig: {
    ...source.summaryConfig,
    handlingSuggestions: [
      {
        suggestionId: 'duplicate',
        displayText: 'x'.repeat(WORKFLOW_SUMMARY_ADVICE_TEXT_MAX_LENGTH + 1),
        sendMessageText: '',
      },
      {
        suggestionId: 'duplicate',
        displayText: '',
        sendMessageText: '继续处理',
      },
      ...Array.from({ length: WORKFLOW_SUMMARY_ADVICE_MAX_COUNT - 1 }, (_, index) => ({
        suggestionId: `extra_${index}`,
        displayText: `建议${index}`,
        sendMessageText: `执行建议${index}`,
      })),
    ],
  },
});
const issues = validateWorkflowDraft(invalid);
assert.equal(
  issues.some((issue) => issue.path === 'summaryConfig.handlingSuggestions'),
  true,
  'more than ten suggestions are rejected',
);
assert.equal(
  issues.some((issue) => issue.path === 'summaryConfig.handlingSuggestions[0].suggestionId'),
  true,
  'duplicate suggestion ids are rejected with a stable item path',
);
assert.equal(
  issues.some((issue) => issue.path === 'summaryConfig.handlingSuggestions[0].displayText'),
  true,
  'overlong display text is rejected',
);
assert.equal(
  issues.some((issue) => issue.path === 'summaryConfig.handlingSuggestions[0].sendMessageText'),
  true,
  'blank send message is rejected',
);
assert.equal(
  issues.some((issue) => issue.path === 'summaryConfig.handlingSuggestions[1].displayText'),
  true,
  'blank display text is rejected',
);

const inspectorSource = readFileSync(
  resolve(process.cwd(), 'workflow/WorkflowInspector.tsx'),
  'utf8',
);
assert.equal(inspectorSource.includes('WORKFLOW_SUMMARY_TITLE'), true);
assert.equal(inspectorSource.includes('处理建议'), true);
assert.equal(inspectorSource.includes('展示文案'), true);
assert.equal(inspectorSource.includes('发送消息'), true);
assert.equal(inspectorSource.includes('Detail Summary Prompt'), true);
assert.equal(inspectorSource.includes('WORKFLOW_SUMMARY_ADVICE_MAX_COUNT'), true);

console.log('workflowSummaryAdvice.test.ts PASS');

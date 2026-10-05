// @ts-check
export const CONTENT_SERVICE = 'a2flow.content.v1.ContentService';
export const CATALOG_ID = 'a2flow.digital-employee.pc.v1';
export const PROTOCOL_VERSION = 'v0.9.1';

const stringItem = { type: 'string' };
const integerItem = { type: 'integer' };
const field = (toolField, type, businessMeaning, extra = {}) => ({
  toolField, type, source: 'MODEL_INPUT', businessMeaning, required: true, ...extra,
});

export const capabilitySpecs = [
  {
    actionCode: 'content.people.list', methodName: 'ListPeople', nameCn: '分页列出演示人员', sideEffect: 'READ',
    description: '按页读取明确标注的虚构演示人员；可信执行上下文由运行边界注入。',
    fields: [field('page', 'integer', '从 1 开始的页码'), field('pageSize', 'integer', '每页数量')],
    mappings: { page: 'page', pageSize: 'pageSize' },
    outputs: [['items', '当前页虚构人员', 'array'], ['total', '虚构人员总数（uint64 ProtoJSON 字符串）', 'string'], ['page', '当前页码', 'integer'], ['pageSize', '每页数量', 'integer']],
    sample: { page: 1, pageSize: 5 },
  },
  {
    actionCode: 'content.people.resolve', methodName: 'ResolvePeople', nameCn: '解析已选演示人员', sideEffect: 'READ',
    description: '按稳定 personId 顺序解析权威虚构人员信息；重复 ID 保序去重，任一未知 ID 整次失败。',
    fields: [field('personIds', 'array', '已选择的 personId，1 到 15 个且不可重复', { items: stringItem })],
    mappings: { personIds: 'personIds' },
    outputs: [['items', '按请求顺序返回的权威虚构人员', 'array']],
    sample: { personIds: ['demo-person-001', 'demo-person-002'] },
  },
];

const ref = path => ({ path });
const call = (name, args) => ({ call: name, args, returnType: 'boolean' });
const formatText = value => ({ call: 'formatString', args: { value }, returnType: 'string' });
const buttonEnabled = (disabledPath, message) => [{
  condition: call('not', { value: ref(disabledPath) }), message,
}];
const nonEmptySelection = [{
  condition: call('length', { value: ref('/selectedPersonIds'), min: 1, max: 15 }),
  message: '请至少选择一名人员',
}];
const contextSchema = properties => ({
  type: 'object', properties, required: Object.keys(properties), additionalProperties: false,
});
const optionsTransform = {
  type: 'ARRAY_OBJECT_TO_OPTIONS', valuePath: '/personId',
  labelColumns: [
    { label: '姓名', sourcePath: '/name' }, { label: '电话', sourcePath: '/phone' },
    { label: '性别', sourcePath: '/gender' }, { label: '年龄', sourcePath: '/age' },
    { label: '爱好', sourcePath: '/hobbies' },
  ],
  labelSeparator: '｜',
};
const updateAdapter = (adapterId, order, path, value, bindings = []) => ({
  adapterId, order, type: 'MESSAGE_TEMPLATE',
  messageTemplate: { version: PROTOCOL_VERSION, updateDataModel: { surfaceId: 'main', path, value } },
  bindings,
});
const optionsAdapter = order => ({
  adapterId: 'options', order, type: 'MESSAGE_TEMPLATE',
  messageTemplate: { version: PROTOCOL_VERSION, updateComponents: { surfaceId: 'main', components: [{
    id: 'people', component: 'ChoicePicker', label: '人员列表', variant: 'multipleSelection',
    displayStyle: 'checkbox', options: [], value: ref('/selectedPersonIds'),
  }] } },
  bindings: [{
    targetPath: '/updateComponents/components/0/options', source: 'CAPABILITY_DATA', sourcePath: '/items', required: true,
    transform: optionsTransform,
  }],
});
const paginationAdapter = (order, page) => updateAdapter('pagination', order, '/pagination', {}, [{
  targetPath: '/updateDataModel/value', source: 'CAPABILITY_DATA', sourcePath: '/total', required: true,
  transform: { type: 'PAGINATION_STATE', pageSize: 5, ...(typeof page === 'number' ? { pageNumber: page } : { actionPagePath: '/page' }) },
}]);
const selectedIdsAdapter = order => updateAdapter('selected_ids', order, '/selectedPersonIds', [], [{
  targetPath: '/updateDataModel/value', source: 'ACTION_CONTEXT', sourcePath: '/selectedPersonIds', required: true,
}]);
const statusAdapter = (adapterId, order, text) => updateAdapter(adapterId, order, '/status', text);
const failureAdapter = statusAdapter('failure', 1, '人员读取失败，请保留当前选择并重试。');
const pageAction = ({ bindingId, componentId, actionCode }) => ({
  bindingId, surfaceId: 'main', sourceComponentId: componentId, actionCode,
  allowedSourceComponentIds: [componentId],
  contextSchema: contextSchema({ page: integerItem, selectedPersonIds: { type: 'array', items: stringItem } }),
  capability: { actionCode: 'content.people.list' },
  requestMappings: [
    { source: 'ACTION_CONTEXT', sourcePath: '/page', targetPath: '/page' },
    { source: 'CONSTANT', targetPath: '/pageSize', constantValue: 5 },
  ],
  successOutcome: 'ADAPTER_PIPELINE', failureOutcome: 'ADAPTER_PIPELINE',
  resultAdapters: [optionsAdapter(1), paginationAdapter(2), selectedIdsAdapter(3), statusAdapter('success', 4, '')],
  failureResultAdapters: [failureAdapter], completeWorkflowInteractionOnSuccess: false,
});

export function buildApplication() {
  return {
    appCode: 'people-selector', nameCn: '分页选择演示人员',
    description: '通过真实只读 RPC 分页展示虚构人员，跨页多选后把权威姓名和脱敏电话追加到聊天输入框。',
    interactionMode: 'DISPLAY_ONLY', catalogId: CATALOG_ID,
    showTemplate: {
      templateCode: 'people_selector_show',
      paramsSchema: { type: 'object', properties: {}, required: [], additionalProperties: false },
      surfaceDeclarations: [{ surfaceId: 'main', rootComponentId: 'root' }],
      messageTemplates: [
        { version: PROTOCOL_VERSION, createSurface: { surfaceId: 'main', catalogId: CATALOG_ID } },
        { version: PROTOCOL_VERSION, updateComponents: { surfaceId: 'main', components: [
          { id: 'root', component: 'Column', children: ['title', 'description', 'people', 'pageInfo', 'pager', 'status', 'fillComposer'] },
          { id: 'title', component: 'Text', text: '选择演示人员', variant: 'h2' },
          { id: 'description', component: 'Text', text: '人员均为虚构演示数据；翻页不会丢失已选项。', variant: 'caption' },
          { id: 'people', component: 'ChoicePicker', label: '人员列表', variant: 'multipleSelection', displayStyle: 'checkbox', options: [], value: ref('/selectedPersonIds') },
          { id: 'pageInfo', component: 'Text', text: formatText('第 ${/pagination/display/pageNum} / ${/pagination/display/totalPages} 页，共 ${/pagination/display/total} 人'), variant: 'caption' },
          { id: 'pager', component: 'Row', children: ['previous', 'next'], justify: 'spaceBetween', align: 'center' },
          { id: 'previous', component: 'Button', child: 'previousText', variant: 'default', checks: buttonEnabled('/pagination/prevDisabled', '已经是第一页'), action: { event: { name: 'previousPage', context: { page: ref('/pagination/prevPage'), selectedPersonIds: ref('/selectedPersonIds') } } } },
          { id: 'previousText', component: 'Text', text: '上一页' },
          { id: 'next', component: 'Button', child: 'nextText', variant: 'default', checks: buttonEnabled('/pagination/nextDisabled', '已经是最后一页'), action: { event: { name: 'nextPage', context: { page: ref('/pagination/nextPage'), selectedPersonIds: ref('/selectedPersonIds') } } } },
          { id: 'nextText', component: 'Text', text: '下一页' },
          { id: 'status', component: 'Text', text: ref('/status'), variant: 'caption' },
          { id: 'fillComposer', component: 'Button', child: 'fillComposerText', variant: 'primary', checks: nonEmptySelection, action: { event: { name: 'fillComposer', context: { selectedPersonIds: ref('/selectedPersonIds') } } } },
          { id: 'fillComposerText', component: 'Text', text: '填入聊天输入框' },
        ] } },
        { version: PROTOCOL_VERSION, updateDataModel: { surfaceId: 'main', path: '/', value: {
          options: [], selectedPersonIds: [],
          pagination: { total: 0, pageSize: 5, pageNum: 1, totalPages: 0, prevPage: 1, nextPage: 1, prevDisabled: true, nextDisabled: true, display: { pageNum: 1, totalPages: 0, total: 0 } },
          status: '',
        } } },
      ], inputBindings: [],
    },
    loadBindings: [{
      bindingId: 'load_people_first_page', capability: { actionCode: 'content.people.list' },
      requestMappings: [
        { source: 'CONSTANT', targetPath: '/page', constantValue: 1 },
        { source: 'CONSTANT', targetPath: '/pageSize', constantValue: 5 },
      ],
      successOutcome: 'ADAPTER_PIPELINE', failureOutcome: 'ADAPTER_PIPELINE',
      resultAdapters: [optionsAdapter(1), paginationAdapter(2, 1), statusAdapter('success', 3, '')],
      failureResultAdapters: [failureAdapter],
    }],
    actionBindings: [
      pageAction({ bindingId: 'previous_page', componentId: 'previous', actionCode: 'previousPage' }),
      pageAction({ bindingId: 'next_page', componentId: 'next', actionCode: 'nextPage' }),
      {
        bindingId: 'fill_composer', surfaceId: 'main', sourceComponentId: 'fillComposer', actionCode: 'fillComposer',
        allowedSourceComponentIds: ['fillComposer'],
        contextSchema: { type: 'object', properties: { selectedPersonIds: { type: 'array', items: stringItem, minItems: 1, maxItems: 15, uniqueItems: true } }, required: ['selectedPersonIds'], additionalProperties: false },
        capability: { actionCode: 'content.people.resolve' },
        requestMappings: [{ source: 'ACTION_CONTEXT', sourcePath: '/selectedPersonIds', targetPath: '/personIds' }],
        successOutcome: 'ADAPTER_PIPELINE', failureOutcome: 'ADAPTER_PIPELINE',
        resultAdapters: [selectedIdsAdapter(1), statusAdapter('composer_success', 2, '已追加到聊天输入框，请确认后再发送。')],
        failureResultAdapters: [failureAdapter], completeWorkflowInteractionOnSuccess: false,
        composerDraftEffect: {
          type: 'COMPOSER_DRAFT', mode: 'APPEND', source: 'CAPABILITY_DATA', itemsPath: '/items',
          columns: [{ label: '姓名', sourcePath: '/name' }, { label: '电话', sourcePath: '/phone' }],
        },
      },
    ],
  };
}

export const skillSpec = {
  skillCode: 'people-selection', nameCn: '分页选择演示人员', applicationCode: 'people-selector',
  capabilities: capabilitySpecs.map(item => item.actionCode),
  markdown: `---
name: people-selection
description: 分页展示虚构演示人员，并由用户多选后把权威姓名和脱敏电话填入聊天输入框。
---

# 人员选择

1. 调用 \`query_skill_dependencies({a2uiApplicationCodeList:["people-selector"]})\` 获取依赖。
2. 调用 \`render_application({appCode:"people-selector",params:{}})\` 展示已发布 Application。
3. 分页、跨页选择和输入框回填由用户在卡片中显式操作；不要替用户选择，不要把回填当作消息已发送。
4. 人员是虚构演示数据，电话为脱敏值；不得声称来自真实通讯录。
5. Load/Action 失败时保留可见错误，不伪造空列表或成功结果。
`,
};

export function validateAssets() {
  const application = buildApplication();
  if (capabilitySpecs.length !== 2) throw new Error('people_selection must publish exactly two capabilities');
  if (application.appCode !== skillSpec.applicationCode) throw new Error('Skill/Application identity mismatch');
  if (new Set(skillSpec.capabilities).size !== 2) throw new Error('Skill capability bindings must be unique');
  return { capabilities: capabilitySpecs.length, applications: 1, skills: 1 };
}

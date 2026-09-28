// @ts-check
export const CONTENT_SERVICE = 'a2flow.content.v1.ContentService';
export const CATALOG_ID = 'a2flow.digital-employee.pc.v1';
export const PROTOCOL_VERSION = 'v0.9.1';

const stringItem = { type: 'string' };
const integerItem = { type: 'integer' };
const referenceItem = {
  type: 'object',
  properties: { kind: { type: 'string', description: '引用类型，只能是 SOURCE 或 ARTIFACT' }, id: stringItem, revision: integerItem },
  required: ['kind', 'id', 'revision'],
};
const citationItem = {
  type: 'object',
  properties: { referenceKind: { type: 'string', description: '引用类型，只能是 SOURCE 或 ARTIFACT' }, referenceId: stringItem, revision: integerItem, label: stringItem },
  required: ['referenceKind', 'referenceId', 'revision', 'label'],
};
const readingPointItem = {
  type: 'object',
  properties: {
    id: stringItem, claim: stringItem, evidenceQuote: stringItem, evidenceLocator: stringItem,
    explanation: stringItem, modelSuggestion: { type: 'boolean' },
  },
  required: ['id', 'claim', 'explanation', 'modelSuggestion'],
};
const topicItem = {
  type: 'object',
  properties: {
    id: stringItem, title: stringItem, angle: stringItem, audience: stringItem,
    rationale: stringItem, sourcePointIds: { type: 'array', items: stringItem },
  },
  required: ['id', 'title', 'angle', 'audience', 'rationale', 'sourcePointIds'],
};

const field = (toolField, type, businessMeaning, required = true, extra = {}) => ({
  toolField, type, source: 'MODEL_INPUT', businessMeaning, required, ...extra,
});
const values = (...items) => items.map(value => ({ value, label: value }));

/**
 * The 12 entries deliberately mirror ContentService one-for-one.  Nested request paths are
 * populated by the existing deterministic request mapper; no JSON-string body escape hatch exists.
 */
export const capabilitySpecs = [
  {
    actionCode: 'content.project.create', methodName: 'CreateProject', nameCn: '创建内容项目', sideEffect: 'WRITE',
    description: '为当前可信用户创建一个阅读到创作项目。',
    fields: [field('title', 'string', '项目标题'), field('audience', 'string', '目标读者'),
      field('outputFormat', 'string', '内容输出形态，只能是 ARTICLE（文章）或 SPOKEN_SCRIPT（口播稿），不是导出文件格式', true, { allowedValues: values('ARTICLE', 'SPOKEN_SCRIPT') })],
    mappings: { title: 'title', audience: 'audience', outputFormat: 'outputFormat' },
    outputs: [['id', '项目 ID', 'string'], ['revision', '项目修订号', 'integer']],
  },
  {
    actionCode: 'content.project.list', methodName: 'ListProjects', nameCn: '列出内容项目', sideEffect: 'READ',
    description: '分页列出当前可信用户自己的内容项目。',
    fields: [field('page', 'integer', '页码'), field('pageSize', 'integer', '每页数量')],
    mappings: { page: 'page', pageSize: 'pageSize' },
    outputs: [['list', '项目列表', 'array'], ['total', '项目总数（uint64 十进制字符串）', 'string']],
  },
  {
    actionCode: 'content.project.get', methodName: 'GetProject', nameCn: '读取内容项目', sideEffect: 'READ',
    description: '按项目 ID 读取当前可信用户自己的项目。',
    fields: [field('projectId', 'string', '项目 ID')], mappings: { projectId: 'projectId' },
    outputs: [['id', '项目 ID', 'string'], ['revision', '项目修订号', 'integer']],
  },
  {
    actionCode: 'content.source.save', methodName: 'SaveSource', nameCn: '保存阅读原文', sideEffect: 'WRITE',
    description: '保存阅读原文并以期望项目修订号做并发保护。',
    fields: [field('projectId', 'string', '项目 ID'), field('title', 'string', '原文标题'), field('body', 'string', '原文正文'),
      field('sourceUrl', 'string', '可选原文地址', false), field('expectedProjectRevision', 'integer', '期望项目修订号')],
    mappings: { projectId: 'projectId', title: 'title', body: 'body', sourceUrl: 'sourceUrl', expectedProjectRevision: 'expectedProjectRevision' },
    outputs: [['id', '原文 ID', 'string'], ['revision', '原文修订号', 'integer'], ['digest', '原文摘要', 'string']],
  },
  {
    actionCode: 'content.source.get', methodName: 'GetSource', nameCn: '读取阅读原文', sideEffect: 'READ',
    description: '按原文 ID 读取当前可信用户自己的阅读原文。',
    fields: [field('sourceId', 'string', '原文 ID')], mappings: { sourceId: 'sourceId' },
    outputs: [['id', '原文 ID', 'string'], ['body', '原文正文', 'string'], ['revision', '原文修订号', 'integer']],
  },
  {
    actionCode: 'content.artifact.save', methodName: 'SaveArtifact', nameCn: '保存创作产物', sideEffect: 'WRITE',
    description: '保存阅读要点、选题方案或稿件；kind 与 body 分支必须一致，且引用必须来自同一项目。',
    fields: [
      field('projectId', 'string', '项目 ID'),
      field('kind', 'string', '产物类型', true, { allowedValues: values('READING_BRIEF', 'TOPIC_PLAN', 'MANUSCRIPT') }),
      field('readingPoints', 'array', '仅 READING_BRIEF 使用，对应 body.readingBrief.points，至少一项', false, { items: readingPointItem }),
      field('questions', 'array', '仅 READING_BRIEF 使用，对应 body.readingBrief.questions', false, { items: stringItem }),
      field('usableMaterials', 'array', '仅 READING_BRIEF 使用，对应 body.readingBrief.usableMaterials', false, { items: stringItem }),
      field('topics', 'array', '仅 TOPIC_PLAN 使用，对应 body.topicPlan.topics，至少一项', false, { items: topicItem }),
      field('manuscriptTitle', 'string', '仅 MANUSCRIPT 使用，对应 body.manuscript.title', false),
      field('manuscriptMarkdown', 'string', '仅 MANUSCRIPT 使用，对应 body.manuscript.bodyMarkdown', false),
      field('citations', 'array', '仅 MANUSCRIPT 使用，对应 body.manuscript.citations', false, { items: citationItem }),
      field('inputRefs', 'array', '冻结输入引用；kind 只能是 SOURCE 或 ARTIFACT，且至少一项', true, { items: referenceItem }),
      field('origin', 'string', '产物来源', true, { allowedValues: values('MODEL_GENERATED', 'USER_EDITED') }),
    ],
    mappings: {
      projectId: 'projectId', kind: 'kind', readingPoints: 'body.readingBrief.points',
      questions: 'body.readingBrief.questions', usableMaterials: 'body.readingBrief.usableMaterials',
      topics: 'body.topicPlan.topics', manuscriptTitle: 'body.manuscript.title',
      manuscriptMarkdown: 'body.manuscript.bodyMarkdown', citations: 'body.manuscript.citations',
      inputRefs: 'inputRefs', origin: 'origin',
    },
    outputs: [['id', '产物 ID', 'string'], ['kind', '产物类型', 'string'], ['revision', '同类型产物修订号', 'integer'], ['body', '结构化产物正文', 'object'], ['bodyMarkdown', '稿件 Markdown', 'string']],
  },
  {
    actionCode: 'content.artifact.get', methodName: 'GetArtifact', nameCn: '读取创作产物', sideEffect: 'READ',
    description: '按产物 ID 读取当前可信用户自己的创作产物。',
    fields: [field('artifactId', 'string', '产物 ID')], mappings: { artifactId: 'artifactId' },
    outputs: [['id', '产物 ID', 'string'], ['kind', '产物类型', 'string'], ['revision', '产物修订号', 'integer'], ['body', '结构化产物正文', 'object']],
  },
  {
    actionCode: 'content.confirmation.get', methodName: 'GetConfirmation', nameCn: '读取用户确认', sideEffect: 'READ',
    description: '按确认 ID 读取当前可信用户自己的不可变确认记录。',
    fields: [field('confirmationId', 'string', '确认记录 ID')], mappings: { confirmationId: 'confirmationId' },
    outputs: [['id', '确认记录 ID', 'string'], ['decisionType', '确认类型', 'string'], ['artifactId', '已确认产物 ID', 'string']],
  },
  {
    actionCode: 'content.reading.confirm', methodName: 'ConfirmReading', nameCn: '确认阅读要点', sideEffect: 'WRITE',
    description: '确认至少一个阅读要点；服务端拒绝空选、重复项、未知项和陈旧项目修订号。',
    fields: [field('projectId', 'string', '项目 ID'), field('artifactId', 'string', '阅读要点产物 ID'),
      field('selectedPointIds', 'array', '用户选中的要点 ID', true, { items: stringItem }),
      field('userNotes', 'string', '用户补充输入', false), field('expectedProjectRevision', 'integer', '期望项目修订号')],
    mappings: { projectId: 'projectId', artifactId: 'artifactId', selectedPointIds: 'selectedPointIds', userNotes: 'userNotes', expectedProjectRevision: 'expectedProjectRevision' },
    outputs: [['id', '确认记录 ID', 'string'], ['decisionType', '确认类型', 'string'], ['selectedPointIds', '已确认要点 ID', 'array']],
  },
  {
    actionCode: 'content.topic.confirm', methodName: 'ConfirmTopic', nameCn: '确认创作选题', sideEffect: 'WRITE',
    description: '确认一个选题并保存用户编辑后的标题与角度。',
    fields: [field('projectId', 'string', '项目 ID'), field('artifactId', 'string', '选题方案产物 ID'),
      field('topicId', 'string', '选题 ID'), field('editedTitle', 'string', '用户确认后的标题'),
      field('editedAngle', 'string', '用户确认后的角度'), field('expectedProjectRevision', 'integer', '期望项目修订号')],
    mappings: { projectId: 'projectId', artifactId: 'artifactId', topicId: 'topicId', editedTitle: 'editedTitle', editedAngle: 'editedAngle', expectedProjectRevision: 'expectedProjectRevision' },
    outputs: [['id', '确认记录 ID', 'string'], ['decisionType', '确认类型', 'string'], ['topicId', '已确认选题 ID', 'string']],
  },
  {
    actionCode: 'content.manuscript.confirm', methodName: 'ConfirmManuscript', nameCn: '确认最终稿件', sideEffect: 'WRITE',
    description: '确认一个已保存稿件；服务端拒绝陈旧项目修订号。',
    fields: [field('projectId', 'string', '项目 ID'), field('artifactId', 'string', '已保存稿件产物 ID'), field('expectedProjectRevision', 'integer', '期望项目修订号')],
    mappings: { projectId: 'projectId', artifactId: 'artifactId', expectedProjectRevision: 'expectedProjectRevision' },
    outputs: [['id', '确认记录 ID', 'string'], ['decisionType', '确认类型', 'string'], ['artifactId', '最终稿件产物 ID', 'string']],
  },
  {
    actionCode: 'content.manuscript.export', methodName: 'ExportManuscript', nameCn: '导出已保存稿件', sideEffect: 'READ',
    description: '按已保存稿件 ID 导出 Markdown 或纯文本，结果以内联内容返回，不接受下载 URL。',
    fields: [field('artifactId', 'string', '已保存稿件产物 ID'),
      field('format', 'string', '导出格式', true, { allowedValues: values('MARKDOWN', 'TXT') })],
    mappings: { artifactId: 'artifactId', format: 'format' },
    outputs: [['filename', '受限文件名', 'string'], ['mediaType', '受限媒体类型', 'string'], ['content', '内联导出内容', 'string']],
  },
];

const dynamicString = {
  anyOf: [
    { type: 'string' },
    { type: 'object', properties: { path: { type: 'string' } }, required: ['path'], additionalProperties: false },
    { type: 'object', properties: {
      call: { type: 'string' }, args: { type: 'object', additionalProperties: true },
      returnType: { type: 'string', enum: ['string', 'number', 'boolean', 'array', 'object', 'any', 'void'] },
    }, required: ['call', 'args'], additionalProperties: false },
  ],
};
const dynamicBoolean = {
  anyOf: [
    { type: 'boolean' },
    { type: 'object', properties: { path: { type: 'string' } }, required: ['path'], additionalProperties: false },
    { type: 'object', properties: {
      call: { type: 'string' }, args: { type: 'object', additionalProperties: true },
      returnType: { type: 'string', enum: ['string', 'number', 'boolean', 'array', 'object', 'any', 'void'] },
    }, required: ['call', 'args'], additionalProperties: false },
  ],
};
const checksSchema = { type: 'array', items: { type: 'object', properties: { condition: dynamicBoolean, message: { type: 'string' } }, required: ['condition', 'message'], additionalProperties: false } };

export const customAtoms = [
  {
    componentCode: 'Markdown', type: 'Markdown', nameCn: 'Markdown 展示', category: 'content', compositionKind: 'ATOMIC',
    propsSchema: { type: 'object', properties: { content: dynamicString }, required: ['content'], additionalProperties: false },
    eventSchema: { type: 'object', properties: {}, additionalProperties: false }, childrenConstraint: {},
    validMessageExample: { id: 'markdown', component: 'Markdown', content: { path: '/savedMarkdown' } },
    invalidMessageExample: { id: 'markdown', component: 'Markdown', content: { url: 'forbidden' } },
  },
  {
    componentCode: 'TextDownload', type: 'TextDownload', nameCn: '受限文本下载', category: 'content', compositionKind: 'ATOMIC',
    propsSchema: { type: 'object', properties: {
      label: dynamicString, filename: dynamicString, mediaType: dynamicString, content: dynamicString,
      checks: checksSchema, isValid: { type: 'boolean' }, validationErrors: { type: 'array', items: { type: 'string' } },
    }, required: ['label', 'filename', 'mediaType', 'content'], additionalProperties: false },
    eventSchema: { type: 'object', properties: {}, additionalProperties: false }, childrenConstraint: {},
    validMessageExample: { id: 'download', component: 'TextDownload', label: '下载', filename: { path: '/export/filename' }, mediaType: { path: '/export/mediaType' }, content: { path: '/export/content' } },
    invalidMessageExample: { id: 'download', component: 'TextDownload', label: '下载', url: 'https://example.invalid/file' },
  },
];

const ref = path => ({ path });
const fn = (call, args) => ({ call, args, returnType: 'boolean' });
const equalsCheck = (left, right, message) => ({ condition: fn('equals', { a: ref(left), b: ref(right) }), message });
const requiredCheck = (path, message) => ({ condition: fn('required', { value: ref(path) }), message });
const savedChecks = [
  equalsCheck('/draftTitle', '/savedTitle', '标题有未保存修改'),
  equalsCheck('/draftMarkdown', '/savedMarkdown', '正文有未保存修改'),
  requiredCheck('/savedArtifactId', '请先保存稿件'),
];
const binding = (name, path = `/${name}`) => ({ [name]: ref(path) });
const appSchema = properties => ({ type: 'object', properties, required: Object.keys(properties), additionalProperties: false });
const appInputBindings = keys => keys.map(key => ({ targetMessageIndex: 2, targetPath: `/updateDataModel/value/${key}`, source: 'APP_PARAMS', sourcePath: `/${key}`, required: true }));
const contextSchema = properties => ({ type: 'object', properties, required: Object.keys(properties), additionalProperties: false });
const actionMappings = keys => keys.map(key => ({ source: 'ACTION_CONTEXT', sourcePath: `/${key}`, targetPath: `/${key}` }));
const adapter = (adapterId, value, bindings = []) => {
  const matchedBindings = new Set();
  const adapters = Object.entries(value).map(([fieldName, fieldValue], index) => {
    const fieldTarget = `/updateDataModel/value/${fieldName}`;
    const fieldBindings = bindings
      .map((item, bindingIndex) => ({ item, bindingIndex }))
      .filter(({ item }) => item.targetPath === fieldTarget || item.targetPath.startsWith(`${fieldTarget}/`))
      .map(({ item, bindingIndex }) => {
        matchedBindings.add(bindingIndex);
        return {
          ...item,
          targetPath: `/updateDataModel/value${item.targetPath.slice(fieldTarget.length)}`,
        };
      });
    return {
      adapterId: `${adapterId}_${fieldName}`, order: index + 1, type: 'MESSAGE_TEMPLATE',
      messageTemplate: { version: PROTOCOL_VERSION, updateDataModel: { surfaceId: 'main', path: `/${fieldName}`, value: fieldValue } },
      bindings: fieldBindings,
    };
  });
  if (matchedBindings.size !== bindings.length) throw new Error(`${adapterId}: binding target must belong to one top-level field`);
  return adapters;
};
const failureAdapter = statusPath => ({
  adapterId: 'show_failure', order: 1, type: 'MESSAGE_TEMPLATE',
  messageTemplate: { version: PROTOCOL_VERSION, updateDataModel: { surfaceId: 'main', path: statusPath, value: '' } },
  bindings: [{ targetPath: '/updateDataModel/value', source: 'CONSTANT', constantValue: '操作失败，请保留当前输入并核对后重试。', required: true }],
});
const actionBinding = ({ bindingId, componentId, actionName, capability, schema, keys, adapters, complete = false, decisionType }) => ({
  bindingId, surfaceId: 'main', sourceComponentId: componentId, actionCode: actionName,
  allowedSourceComponentIds: [componentId], contextSchema: schema, capability: { actionCode: capability },
  requestMappings: actionMappings(keys), successOutcome: 'ADAPTER_PIPELINE', failureOutcome: capability.endsWith('.export') ? 'NO_UI_MESSAGES' : 'ADAPTER_PIPELINE',
  completeWorkflowInteractionOnSuccess: complete,
  ...(complete ? { businessSuccessPredicate: { version: 'JSON_POINTER_V1', allOf: [{ source: 'CAPABILITY_DATA', sourcePath: '/decisionType', operator: 'EQUALS', expectedValue: decisionType }] } } : {}),
  resultAdapters: adapters,
  failureResultAdapters: capability.endsWith('.export') ? [] : [failureAdapter('/status')],
});

export function buildApplications() {
  const readingProperties = {
    prompt: stringItem, projectId: stringItem, artifactId: stringItem, projectRevision: integerItem,
    points: { type: 'array', items: readingPointItem },
    options: { type: 'array', items: { type: 'object', properties: { label: stringItem, value: stringItem }, required: ['label', 'value'] } },
    selectedPointIds: { type: 'array', items: stringItem }, userNotes: stringItem, confirmationId: stringItem, status: stringItem,
  };
  const readingKeys = Object.keys(readingProperties);
  const readingContext = contextSchema({ projectId: stringItem, artifactId: stringItem, selectedPointIds: { type: 'array', items: stringItem }, userNotes: stringItem, expectedProjectRevision: integerItem });
  const reading = {
    appCode: 'reading-point-selector', nameCn: '阅读要点选择', description: '展示原文证据并由用户多选确认阅读要点。', interactionMode: 'INTERACTIVE', catalogId: CATALOG_ID,
    showTemplate: { templateCode: 'reading_point_selector_show', paramsSchema: appSchema(readingProperties), surfaceDeclarations: [{ surfaceId: 'main', rootComponentId: 'root' }], messageTemplates: [
      { version: PROTOCOL_VERSION, createSurface: { surfaceId: 'main', catalogId: CATALOG_ID } },
      { version: PROTOCOL_VERSION, updateComponents: { surfaceId: 'main', components: [
        { id: 'root', component: 'Column', children: ['title', 'points', 'selection', 'notes', 'status', 'confirm'] },
        { id: 'title', component: 'Text', text: ref('/prompt'), variant: 'h2' },
        { id: 'points', component: 'List', children: { componentId: 'pointCard', path: '/points' }, direction: 'vertical' },
        { id: 'pointCard', component: 'Card', child: 'pointBody' },
        { id: 'pointBody', component: 'Column', children: ['pointClaim', 'pointQuote', 'pointExplanation'] },
        { id: 'pointClaim', component: 'Text', text: ref('claim'), variant: 'h4' },
        { id: 'pointQuote', component: 'Text', text: ref('evidenceQuote'), variant: 'caption' },
        { id: 'pointExplanation', component: 'Text', text: ref('explanation') },
        { id: 'selection', component: 'ChoicePicker', label: '选择要保留的阅读要点', variant: 'multipleSelection', displayStyle: 'checkbox', options: [], value: ref('/selectedPointIds'), checks: [{ condition: fn('length', { value: ref('/selectedPointIds'), min: 1 }), message: '至少选择一个阅读要点' }] },
        { id: 'notes', component: 'TextField', label: '补充你的理解（可选）', value: ref('/userNotes'), variant: 'longText' },
        { id: 'status', component: 'Text', text: ref('/status'), variant: 'caption' },
        { id: 'confirm', component: 'Button', child: 'confirmText', variant: 'primary', checks: [{ condition: fn('length', { value: ref('/selectedPointIds'), min: 1 }), message: '至少选择一个阅读要点' }], action: { event: { name: 'confirmReading', context: { ...binding('projectId'), ...binding('artifactId'), ...binding('selectedPointIds'), ...binding('userNotes'), expectedProjectRevision: ref('/projectRevision') } } } },
        { id: 'confirmText', component: 'Text', text: '确认阅读要点' },
      ] } },
      { version: PROTOCOL_VERSION, updateDataModel: { surfaceId: 'main', path: '/', value: Object.fromEntries(readingKeys.map(key => [key, readingProperties[key].type === 'array' ? [] : readingProperties[key].type === 'integer' ? 0 : ''])) } },
    ], inputBindings: [...appInputBindings(readingKeys), {
      targetMessageIndex: 1, targetPath: '/updateComponents/components/8/options',
      source: 'APP_PARAMS', sourcePath: '/options', required: true,
    }] }, loadBindings: [],
    actionBindings: [actionBinding({ bindingId: 'confirm_reading', componentId: 'confirm', actionName: 'confirmReading', capability: 'content.reading.confirm', schema: readingContext, keys: ['projectId', 'artifactId', 'selectedPointIds', 'userNotes', 'expectedProjectRevision'], complete: true, decisionType: 'READING', adapters: adapter('reading_confirmed', {
      confirmationId: '', selectedPointIds: [], userNotes: '', status: '阅读要点已确认',
    }, [
      { targetPath: '/updateDataModel/value/confirmationId', source: 'CAPABILITY_DATA', sourcePath: '/id', required: true },
      { targetPath: '/updateDataModel/value/selectedPointIds', source: 'CAPABILITY_DATA', sourcePath: '/selectedPointIds', required: true },
      { targetPath: '/updateDataModel/value/userNotes', source: 'CAPABILITY_DATA', sourcePath: '/userNotes', required: true },
    ]) })],
  };

  const topicProperties = {
    prompt: stringItem, projectId: stringItem, artifactId: stringItem, projectRevision: integerItem,
    topics: { type: 'array', items: topicItem }, confirmationId: stringItem, status: stringItem,
  };
  const topicKeys = Object.keys(topicProperties);
  const topicContext = contextSchema({ projectId: stringItem, artifactId: stringItem, topicId: stringItem, editedTitle: stringItem, editedAngle: stringItem, expectedProjectRevision: integerItem });
  const topic = {
    appCode: 'content-topic-selector', nameCn: '创作选题确认', description: '逐项展示选题，允许编辑标题和角度后确认一个方案。', interactionMode: 'INTERACTIVE', catalogId: CATALOG_ID,
    showTemplate: { templateCode: 'content_topic_selector_show', paramsSchema: appSchema(topicProperties), surfaceDeclarations: [{ surfaceId: 'main', rootComponentId: 'root' }], messageTemplates: [
      { version: PROTOCOL_VERSION, createSurface: { surfaceId: 'main', catalogId: CATALOG_ID } },
      { version: PROTOCOL_VERSION, updateComponents: { surfaceId: 'main', components: [
        { id: 'root', component: 'Column', children: ['title', 'topics', 'status'] },
        { id: 'title', component: 'Text', text: ref('/prompt'), variant: 'h2' },
        { id: 'topics', component: 'List', children: { componentId: 'topicCard', path: '/topics' }, direction: 'vertical' },
        { id: 'topicCard', component: 'Card', child: 'topicBody' },
        { id: 'topicBody', component: 'Column', children: ['topicTitle', 'topicAngle', 'topicAudience', 'topicRationale', 'confirmTopic'] },
        { id: 'topicTitle', component: 'TextField', label: '标题', value: ref('title'), variant: 'shortText' },
        { id: 'topicAngle', component: 'TextField', label: '角度', value: ref('angle'), variant: 'longText' },
        { id: 'topicAudience', component: 'Text', text: ref('audience'), variant: 'caption' },
        { id: 'topicRationale', component: 'Text', text: ref('rationale') },
        { id: 'confirmTopic', component: 'Button', child: 'confirmTopicText', variant: 'primary', action: { event: { name: 'confirmTopic', context: { projectId: ref('/projectId'), artifactId: ref('/artifactId'), topicId: ref('id'), editedTitle: ref('title'), editedAngle: ref('angle'), expectedProjectRevision: ref('/projectRevision') } } } },
        { id: 'confirmTopicText', component: 'Text', text: '确认这个选题' },
        { id: 'status', component: 'Text', text: ref('/status'), variant: 'caption' },
      ] } },
      { version: PROTOCOL_VERSION, updateDataModel: { surfaceId: 'main', path: '/', value: Object.fromEntries(topicKeys.map(key => [key, topicProperties[key].type === 'array' ? [] : topicProperties[key].type === 'integer' ? 0 : ''])) } },
    ], inputBindings: appInputBindings(topicKeys) }, loadBindings: [],
    actionBindings: [actionBinding({ bindingId: 'confirm_topic', componentId: 'confirmTopic', actionName: 'confirmTopic', capability: 'content.topic.confirm', schema: topicContext, keys: ['projectId', 'artifactId', 'topicId', 'editedTitle', 'editedAngle', 'expectedProjectRevision'], complete: true, decisionType: 'TOPIC', adapters: adapter('topic_confirmed', {
      confirmationId: '',
      topics: [{ id: '', title: '', angle: '', audience: '', rationale: '', sourcePointIds: [] }],
      status: '创作选题已确认',
    }, [
      { targetPath: '/updateDataModel/value/confirmationId', source: 'CAPABILITY_DATA', sourcePath: '/id', required: true },
      { targetPath: '/updateDataModel/value/topics/0/id', source: 'CAPABILITY_DATA', sourcePath: '/topicId', required: true },
      { targetPath: '/updateDataModel/value/topics/0/title', source: 'CAPABILITY_DATA', sourcePath: '/editedTitle', required: true },
      { targetPath: '/updateDataModel/value/topics/0/angle', source: 'CAPABILITY_DATA', sourcePath: '/editedAngle', required: true },
    ]) })],
  };

  const manuscriptProperties = {
    projectId: stringItem, projectRevision: integerItem, draftTitle: stringItem, draftMarkdown: stringItem,
    savedTitle: stringItem, savedMarkdown: stringItem, savedArtifactId: stringItem, savedArtifactRevision: integerItem,
    inputRefs: { type: 'array', items: referenceItem }, citations: { type: 'array', items: citationItem },
    status: stringItem, confirmationId: stringItem,
    export: { type: 'object', properties: { artifactId: stringItem, artifactRevision: integerItem, filename: stringItem, mediaType: stringItem, content: stringItem }, required: ['artifactId', 'artifactRevision', 'filename', 'mediaType', 'content'] },
  };
  const manuscriptKeys = Object.keys(manuscriptProperties);
  const saveContext = contextSchema({ projectId: stringItem, kind: stringItem, manuscriptTitle: stringItem, manuscriptMarkdown: stringItem, citations: { type: 'array', items: citationItem }, inputRefs: { type: 'array', items: referenceItem }, origin: stringItem });
  const confirmContext = contextSchema({ projectId: stringItem, artifactId: stringItem, expectedProjectRevision: integerItem });
  const exportContext = contextSchema({ artifactId: stringItem, artifactRevision: integerItem, format: stringItem });
  const downloadChecks = [...savedChecks,
    equalsCheck('/export/artifactId', '/savedArtifactId', '导出内容不是当前已保存稿件'),
    equalsCheck('/export/artifactRevision', '/savedArtifactRevision', '导出内容不是当前已保存修订'),
    requiredCheck('/export/content', '请先导出当前已保存稿件'),
  ];
  const manuscript = {
    appCode: 'content-manuscript-editor', nameCn: '稿件编辑与导出', description: '编辑、预览、保存、确认并以内联内容导出稿件。', interactionMode: 'INTERACTIVE', catalogId: CATALOG_ID,
    showTemplate: { templateCode: 'content_manuscript_editor_show', paramsSchema: appSchema(manuscriptProperties), surfaceDeclarations: [{ surfaceId: 'main', rootComponentId: 'root' }], messageTemplates: [
      { version: PROTOCOL_VERSION, createSurface: { surfaceId: 'main', catalogId: CATALOG_ID } },
      { version: PROTOCOL_VERSION, updateComponents: { surfaceId: 'main', components: [
        { id: 'root', component: 'Column', children: ['title', 'body', 'previewLabel', 'preview', 'status', 'actions', 'download'] },
        { id: 'title', component: 'TextField', label: '稿件标题', value: ref('/draftTitle'), variant: 'shortText' },
        { id: 'body', component: 'TextField', label: '稿件正文（Markdown）', value: ref('/draftMarkdown'), variant: 'longText' },
        { id: 'previewLabel', component: 'Text', text: 'Markdown 预览', variant: 'h3' },
        { id: 'preview', component: 'Markdown', content: ref('/draftMarkdown') },
        { id: 'status', component: 'Text', text: ref('/status'), variant: 'caption' },
        { id: 'actions', component: 'Row', children: ['save', 'exportButton', 'confirm'] },
        { id: 'save', component: 'Button', child: 'saveText', variant: 'primary', action: { event: { name: 'saveManuscriptDraft', context: { projectId: ref('/projectId'), kind: 'MANUSCRIPT', manuscriptTitle: ref('/draftTitle'), manuscriptMarkdown: ref('/draftMarkdown'), citations: ref('/citations'), inputRefs: ref('/inputRefs'), origin: 'USER_EDITED' } } } },
        { id: 'saveText', component: 'Text', text: '保存稿件' },
        { id: 'exportButton', component: 'Button', child: 'exportText', checks: savedChecks, action: { event: { name: 'exportManuscript', context: { artifactId: ref('/savedArtifactId'), artifactRevision: ref('/savedArtifactRevision'), format: 'MARKDOWN' } } } },
        { id: 'exportText', component: 'Text', text: '生成下载内容' },
        { id: 'confirm', component: 'Button', child: 'confirmText', checks: savedChecks, action: { event: { name: 'confirmManuscript', context: { projectId: ref('/projectId'), artifactId: ref('/savedArtifactId'), expectedProjectRevision: ref('/projectRevision') } } } },
        { id: 'confirmText', component: 'Text', text: '确认最终稿' },
        { id: 'download', component: 'TextDownload', label: '下载当前已保存稿件', filename: ref('/export/filename'), mediaType: ref('/export/mediaType'), content: ref('/export/content'), checks: downloadChecks },
      ] } },
      { version: PROTOCOL_VERSION, updateDataModel: { surfaceId: 'main', path: '/', value: {
        projectId: '', projectRevision: 0, draftTitle: '', draftMarkdown: '', savedTitle: '', savedMarkdown: '', savedArtifactId: '', savedArtifactRevision: 0,
        inputRefs: [], citations: [], status: '', confirmationId: '', export: { artifactId: '', artifactRevision: 0, filename: '', mediaType: '', content: '' },
      } } },
    ], inputBindings: appInputBindings(manuscriptKeys) }, loadBindings: [],
    actionBindings: [
      actionBinding({ bindingId: 'save_manuscript', componentId: 'save', actionName: 'saveManuscriptDraft', capability: 'content.artifact.save', schema: saveContext, keys: ['projectId', 'kind', 'manuscriptTitle', 'manuscriptMarkdown', 'citations', 'inputRefs', 'origin'], adapters: adapter('manuscript_saved', {
        draftTitle: '', draftMarkdown: '', savedTitle: '', savedMarkdown: '', savedArtifactId: '', savedArtifactRevision: 0,
        status: '稿件已保存', export: { artifactId: '', artifactRevision: 0, filename: '', mediaType: '', content: '' },
      }, [
        { targetPath: '/updateDataModel/value/draftTitle', source: 'CAPABILITY_DATA', sourcePath: '/body/manuscript/title', required: true },
        { targetPath: '/updateDataModel/value/draftMarkdown', source: 'CAPABILITY_DATA', sourcePath: '/body/manuscript/bodyMarkdown', required: true },
        { targetPath: '/updateDataModel/value/savedTitle', source: 'CAPABILITY_DATA', sourcePath: '/body/manuscript/title', required: true },
        { targetPath: '/updateDataModel/value/savedMarkdown', source: 'CAPABILITY_DATA', sourcePath: '/body/manuscript/bodyMarkdown', required: true },
        { targetPath: '/updateDataModel/value/savedArtifactId', source: 'CAPABILITY_DATA', sourcePath: '/id', required: true },
        { targetPath: '/updateDataModel/value/savedArtifactRevision', source: 'CAPABILITY_DATA', sourcePath: '/revision', required: true },
      ]) }),
      actionBinding({ bindingId: 'export_manuscript', componentId: 'exportButton', actionName: 'exportManuscript', capability: 'content.manuscript.export', schema: exportContext, keys: ['artifactId', 'format'], adapters: adapter('manuscript_exported', { export: { artifactId: '', artifactRevision: 0, filename: '', mediaType: '', content: '' }, status: '下载内容已生成' }, [
        { targetPath: '/updateDataModel/value/export/artifactId', source: 'ACTION_CONTEXT', sourcePath: '/artifactId', required: true },
        { targetPath: '/updateDataModel/value/export/artifactRevision', source: 'ACTION_CONTEXT', sourcePath: '/artifactRevision', required: true },
        { targetPath: '/updateDataModel/value/export/filename', source: 'CAPABILITY_DATA', sourcePath: '/filename', required: true },
        { targetPath: '/updateDataModel/value/export/mediaType', source: 'CAPABILITY_DATA', sourcePath: '/mediaType', required: true },
        { targetPath: '/updateDataModel/value/export/content', source: 'CAPABILITY_DATA', sourcePath: '/content', required: true },
      ]) }),
      actionBinding({ bindingId: 'confirm_manuscript', componentId: 'confirm', actionName: 'confirmManuscript', capability: 'content.manuscript.confirm', schema: confirmContext, keys: ['projectId', 'artifactId', 'expectedProjectRevision'], complete: true, decisionType: 'MANUSCRIPT', adapters: adapter('manuscript_confirmed', { confirmationId: '', status: '最终稿已确认' }, [{ targetPath: '/updateDataModel/value/confirmationId', source: 'CAPABILITY_DATA', sourcePath: '/id', required: true }]) }),
    ],
  };
  return [reading, topic, manuscript];
}

export const skillSpecs = [
  {
    skillCode: 'reading-material-analysis', nameCn: '阅读材料分析', applicationCode: 'reading-point-selector',
    capabilities: ['content.project.create', 'content.project.list', 'content.project.get', 'content.source.save', 'content.source.get', 'content.artifact.save', 'content.artifact.get', 'content.confirmation.get', 'content.reading.confirm'],
    markdown: `---\nname: reading-material-analysis\ndescription: 保存阅读材料、生成有原文依据的阅读要点，并交给用户多选确认\n---\n\n# 阅读材料分析\n\n创建项目时 outputFormat 只能取 ARTICLE 或 SPOKEN_SCRIPT；本场景默认 ARTICLE，不能填写 Markdown。先创建或读取项目并保存原文，再调用 content.artifact.save：kind 必须为 READING_BRIEF，只填写 readingPoints/questions/usableMaterials 分支，inputRefs 使用 kind=SOURCE。非模型建议的要点必须引用原文中真实存在的原句。能力响应中的展示数据路径是 body.readingBrief.points；调用 reading-point-selector 时，把该 points 规范化为展示列表，把每个 id/claim 规范化为 options 的 value/label；不得代替用户选择。只有 confirmReading 成功且响应 decisionType=READING 才视为本阶段完成。\n`,
  },
  {
    skillCode: 'content-topic-planning', nameCn: '内容选题规划', applicationCode: 'content-topic-selector',
    capabilities: ['content.project.get', 'content.artifact.get', 'content.artifact.save', 'content.confirmation.get', 'content.topic.confirm'],
    markdown: `---\nname: content-topic-planning\ndescription: 基于已确认阅读要点生成选题，并等待用户编辑和确认\n---\n\n# 内容选题规划\n\n只基于 decisionType=READING 的确认记录生成选题。调用 content.artifact.save 时 kind 必须为 TOPIC_PLAN，只填写 topics 分支，inputRefs 使用 kind=ARTIFACT 指向已确认的 READING_BRIEF；每个候选都要保留 sourcePointIds。能力响应中的展示数据路径是 body.topicPlan.topics；使用 content-topic-selector 展示候选。每张候选卡中的标题和角度可编辑，必须由用户点击该卡的 confirmTopic；只有响应 decisionType=TOPIC 才算确认，不能替用户确认。\n`,
  },
  {
    skillCode: 'content-draft-writing', nameCn: '内容稿件创作', applicationCode: 'content-manuscript-editor',
    capabilities: ['content.project.get', 'content.artifact.get', 'content.artifact.save', 'content.confirmation.get', 'content.manuscript.confirm', 'content.manuscript.export'],
    markdown: `---\nname: content-draft-writing\ndescription: 基于已确认选题创作、编辑、保存、确认和导出稿件\n---\n\n# 内容稿件创作\n\n只基于 decisionType=TOPIC 的确认记录创作稿件。先调用 content.project.get；project.currentSelectionId 是 confirmationId，不是 artifactId。调用 content.confirmation.get({confirmationId: currentSelectionId})；如果 currentSelectionId 为空，或该响应 decisionType 不是 TOPIC，立即停止并请用户先确认选题，不得自行生成确认。从 TOPIC 确认记录的 artifactId、topicId、editedTitle 和 editedAngle 取得用户最终确认结果；稿件标题和角度必须采用 editedTitle 和 editedAngle。该确认记录不含产物 revision，使用该响应的 artifactId 调用 content.artifact.get，确认 kind=TOPIC_PLAN 并取得 artifact revision 和 body.topicPlan.topics；topicId 只用于在候选中定位证据与 sourcePointIds，不得用原候选 title/angle 覆盖用户确认后的 editedTitle/editedAngle。调用 content.artifact.save 时顶层必须填写 projectId、kind=MANUSCRIPT、inputRefs 和 origin，body 分支只填写 manuscriptTitle/manuscriptMarkdown/citations。inputRefs 至少包含已确认的 TOPIC_PLAN：kind=ARTIFACT、id=上述 artifactId、revision=content.artifact.get 返回的 revision。citation 的 referenceKind 只能是 SOURCE 或 ARTIFACT，且每个 citation 的 referenceKind/referenceId/revision 必须在 inputRefs 中存在完全一致的 kind/id/revision。能力响应中的已保存正文路径是 body.manuscript.title 和 body.manuscript.bodyMarkdown。调用 render_application 前，必须以本轮 use_skill 返回的 dependencies.applications 中 content-manuscript-editor.paramsSchema.required 为准逐项完整构造 data；initialMessages 的默认值不代表可以省略 required 字段。首次渲染尚未导出时，export 必须显式传 {artifactId:"",artifactRevision:0,filename:"",mediaType:"",content:""}；该空对象只表示未导出，不得伪造文件名、媒体类型或导出内容。若 project.currentManuscriptId 非空且用户只要求展示或继续编辑已保存稿件，调用 content.artifact.get 读取该 id 对应的真实 MANUSCRIPT，不得再次调用 content.artifact.save。渲染时使用 project.get 返回的真实 id/revision 作为 projectId/projectRevision，使用 artifact.get 返回的真实 id/revision/body/inputRefs 映射 draftTitle/draftMarkdown、savedTitle/savedMarkdown、savedArtifactId/savedArtifactRevision、citations 和 inputRefs；不存在真实确认或导出结果时，confirmationId 和 export 保持上述空值。使用 content-manuscript-editor 编辑和预览；saveManuscriptDraft 返回的新 artifact id/revision 是后续唯一有效保存身份。存在未保存标题或正文时 confirmManuscript、exportManuscript 和下载都会被组件 checks 阻断。导出 format 只能是 MARKDOWN 或 TXT；最终确认必须返回 decisionType=MANUSCRIPT。不得对旧 artifact 执行确认或导出。\n`,
  },
];

export function buildWorkflow(workflowCode) {
  const summaryPrompt = '总结用户已确认的阅读要点、选题与最终稿，不得把未确认草稿表述为最终结果。';
  const nodes = skillSpecs.map((skill, index) => ({
    nodeCode: ['reading', 'topic', 'manuscript'][index], nodeType: 'SKILL', displayName: skill.nameCn,
    skillCode: skill.skillCode, nodePrompt: skill.markdown.split('\n\n').at(-2) || skill.nameCn,
    quickTriggerMessage: ['开始整理阅读材料', '基于已确认要点规划选题', '基于已确认选题创作稿件'][index],
    controlPolicy: { allowSkip: false },
  }));
  nodes.push({ nodeCode: 'summary', nodeType: 'SUMMARY', displayName: '创作结果总结', prompt: summaryPrompt, allowSkip: false });
  return {
    snapshotContractVersion: 2, workflowCode, metadata: { scenario: 'reading-to-creation-mvp' }, nodes,
    edges: [
      { edgeId: 'reading_to_topic', sourceNodeCode: 'reading', targetNodeCode: 'topic', edgeType: 'NORMAL' },
      { edgeId: 'topic_to_manuscript', sourceNodeCode: 'topic', targetNodeCode: 'manuscript', edgeType: 'NORMAL' },
      { edgeId: 'manuscript_to_summary', sourceNodeCode: 'manuscript', targetNodeCode: 'summary', edgeType: 'NORMAL' },
    ],
    summaryConfig: { prompt: summaryPrompt, handlingSuggestions: [] },
  };
}

export function validateAssets() {
  const invariant = (condition, message) => { if (!condition) throw new Error(message); };
  const methods = ['CreateProject', 'ListProjects', 'GetProject', 'SaveSource', 'GetSource', 'SaveArtifact', 'GetArtifact', 'GetConfirmation', 'ConfirmReading', 'ConfirmTopic', 'ConfirmManuscript', 'ExportManuscript'];
  invariant(capabilitySpecs.length === 12, 'expected exactly 12 capabilities');
  invariant(new Set(capabilitySpecs.map(item => item.actionCode)).size === 12, 'capability actionCode must be unique');
  invariant(JSON.stringify(capabilitySpecs.map(item => item.methodName)) === JSON.stringify(methods), 'content.proto methods differ');
  for (const spec of capabilitySpecs) {
    invariant(Object.keys(spec.mappings).length === spec.fields.length, `${spec.actionCode}: every field must have one request mapping`);
    invariant(spec.fields.every(item => ['string', 'integer', 'number', 'boolean', 'array'].includes(item.type)), `${spec.actionCode}: unsupported top-level field type`);
  }
  const applications = buildApplications();
  invariant(JSON.stringify(applications.map(item => item.appCode)) === JSON.stringify(['reading-point-selector', 'content-topic-selector', 'content-manuscript-editor']), 'application identity differs');
  const manuscript = applications[2];
  invariant(JSON.stringify(manuscript.actionBindings.map(item => item.actionCode)) === JSON.stringify(['saveManuscriptDraft', 'exportManuscript', 'confirmManuscript']), 'manuscript actions differ');
  const exportAdapter = manuscript.actionBindings[1].resultAdapters[0];
  invariant(exportAdapter.bindings.some(item => item.source === 'ACTION_CONTEXT' && item.sourcePath === '/artifactRevision'), 'export revision identity is not persisted');
  invariant(skillSpecs.length === 3, 'expected three skills');
  const workflow = buildWorkflow('wf_fixture');
  invariant(workflow.nodes.filter(item => item.nodeType === 'SUMMARY').length === 1, 'workflow summary node differs');
  invariant(workflow.edges.length === 3, 'workflow edge count differs');
  return { capabilities: capabilitySpecs.length, applications: applications.length, skills: skillSpecs.length, customAtoms: customAtoms.length, workflowNodes: workflow.nodes.length };
}

if (typeof process !== 'undefined' && process.argv?.includes('--check')) console.log(`PASS ${JSON.stringify(validateAssets())}`);

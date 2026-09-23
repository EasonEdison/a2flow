import { strict as assert } from 'node:assert';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import CapabilityExecutionBindingEditor from './CapabilityExecutionBindingEditor';
import { capabilityCenterApi } from './api';
import { createEmptyCapabilityDraft, capabilityDraftWithSourceType, registerCapabilityDraftWithName } from './capabilityDraftLifecycle';
import { buildCapabilityClientCanonicalDraft, splitCapabilityClientCanonicalDraft } from './capabilityClientTechnicalDraft';

const draft = createEmptyCapabilityDraft();
draft.basicInfo = { actionCode: 'orders.query', nameCn: '查询订单' };
draft.executionBinding.target = {
  targetKey: 'orders', serviceName: 'a2flow.Orders', methodName: 'Query',
  descriptorSetBase64: 'ZGVzY3JpcHRvcg==', contextField: 'context',
};
draft.resultContract.technicalOutputSchema = '{"type":"object","properties":{"id":{"type":"string"}}}';
draft.executionBinding.requestMappingsJson = '{"id":"order_id"}';
const canonical = buildCapabilityClientCanonicalDraft(draft, createEmptyCapabilityDraft(), createEmptyCapabilityDraft(), ['PC']);
const originalFetch = globalThis.fetch;
const methods: string[] = [];
globalThis.fetch = async (url, options) => {
  assert.equal(url, '/api/management/v2/handler', 'management transport stays HTTP');
  const request = JSON.parse(String(options?.body));
  methods.push(request.method);
  if (request.method === 'CAPABILITY_DRAFT_CREATE') {
    assert.deepEqual(JSON.parse(request.params.draftJson), {
      payloadType: 'CAPABILITY_DRAFT_SNAPSHOT', mode: 'CREATE', basicInfo: { nameCn: '查询订单' },
    }, 'registration remains the server-authorized minimal name payload');
  }
  if (request.method === 'CAPABILITY_DRAFT_SAVE') {
    assert.equal(request.params.baseRevision, 1);
    assert.deepEqual(JSON.parse(request.params.draftJson), canonical, 'RPC fields survive request serialization');
    assert.equal(request.params.businessDomain, 'orders');
  }
  if (request.method === 'CAPABILITY_VALIDATE') return new Response(JSON.stringify({ result: 1, data: { valid: false, errors: ['descriptor fixture is not valid protobuf'] } }));
  if (request.method === 'CAPABILITY_PUBLISH') return new Response(JSON.stringify({ result: 0, errorMsg: 'RPC validation required' }));
  return new Response(JSON.stringify({ result: 1, data: { draftId: 'rpc-test', revision: 2, status: 'DRAFT', draft: canonical } }));
};
try {
  await registerCapabilityDraftWithName({ nameCn: ' 查询订单 ', create: capabilityCenterApi.create, openEditor: () => {} });
  await capabilityCenterApi.save('rpc-test', 1, canonical, { businessDomain: 'orders', capabilityDomain: 'query', specialistIds: [] });
  const loaded = await capabilityCenterApi.detail('rpc-test');
  const restored = splitCapabilityClientCanonicalDraft(loaded.draft, createEmptyCapabilityDraft()).canonicalDraft;
  assert.deepEqual(capabilityDraftWithSourceType(restored, 'GRPC').executionBinding.target, draft.executionBinding.target);
  assert.equal(restored.resultContract.technicalOutputSchema, draft.resultContract.technicalOutputSchema);
  assert.equal((await capabilityCenterApi.validate('rpc-test')).valid, false, 'backend failure is not converted to success');
  await assert.rejects(capabilityCenterApi.publish('rpc-test'), /RPC validation required/);
  assert.deepEqual(methods, ['CAPABILITY_DRAFT_CREATE', 'CAPABILITY_DRAFT_SAVE', 'CAPABILITY_DRAFT_DETAIL', 'CAPABILITY_VALIDATE', 'CAPABILITY_PUBLISH']);
} finally { globalThis.fetch = originalFetch; }
const markup = renderToStaticMarkup(React.createElement(CapabilityExecutionBindingEditor, {
  value: draft.executionBinding, inputFields: [], sourceType: 'GRPC', onChange: () => {},
}));
for (const label of ['业务服务配置键', '完整服务名', '方法名', '协议描述文件', '请求字段映射']) assert.ok(markup.includes(label), label);
assert.doesNotMatch(markup, /HTTP Method|登记 URL|静态 Header|Cookie|环境 Header/);
console.log('PASS RPC manual form and register/save/read/validation/publication wire contracts (mock transport only)');

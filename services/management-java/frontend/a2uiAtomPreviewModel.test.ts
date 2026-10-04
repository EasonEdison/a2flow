import assert from 'node:assert/strict';
import test from 'node:test';
import { basicCatalog } from '@a2ui/react/v0_9';
import { MessageProcessor } from '@a2ui/web_core/v0_9';
import {
  OFFICIAL_BASIC_CATALOG_ID,
  parseA2uiAtomPreviewDocument,
  resolveA2uiAtomPreviewSource,
} from './a2uiAtomPreviewModel';

test('official Button without upstream demo gets an explicitly schema-derived interactive example', () => {
  const source = resolveA2uiAtomPreviewSource({
    id: 'button',
    componentCode: 'Button',
    type: 'Button',
    nameCn: '按钮',
    componentOriginType: 'A2UI_OFFICIAL',
    officialSchema: { type: 'object' },
  });
  assert.equal(source.kind, 'SCHEMA_DERIVED');
  assert.match(source.description, /不是 Google 官方原始 demo/);
  assert.equal(source.document?.components[0].component, 'Button');
  assert.equal(source.document?.components[1].component, 'Text');
});

test('registered validMessageExample has priority over schema-derived examples', () => {
  const source = resolveA2uiAtomPreviewSource({
    id: 'text',
    componentCode: 'Text',
    type: 'Text',
    nameCn: '文本',
    componentOriginType: 'A2UI_OFFICIAL',
    officialSchema: { type: 'object' },
    validMessageExample: { id: 'registered', component: 'Text', text: 'registered value' },
  });
  assert.equal(source.kind, 'REGISTERED_EXAMPLE');
  assert.equal(source.document?.components[0].id, 'root');
  assert.equal(source.document?.components[0].text, 'registered value');
});

test('non-empty invalid registered example fails closed instead of using a schema example', () => {
  const source = resolveA2uiAtomPreviewSource({
    id: 'button',
    componentCode: 'Button',
    type: 'Button',
    nameCn: '按钮',
    componentOriginType: 'A2UI_OFFICIAL',
    officialSchema: { type: 'object' },
    validMessageExample: { component: 'Text', text: 'wrong component type' },
  });
  assert.equal(source.kind, 'UNAVAILABLE');
  assert.match(source.description, /不会静默改用 Schema 示例/);
  assert.equal(source.document, undefined);
});

test('Tabs schema-derived example includes two referenced panels', () => {
  const source = resolveA2uiAtomPreviewSource({
    id: 'tabs',
    componentCode: 'Tabs',
    type: 'Tabs',
    nameCn: '标签页',
    componentOriginType: 'A2UI_OFFICIAL',
    officialSchema: { type: 'object' },
  });
  assert.equal(source.document?.components.length, 3);
  assert.equal(source.document?.components[0].component, 'Tabs');
});

test('invalid preview document fails closed', () => {
  assert.throws(() => parseA2uiAtomPreviewDocument('{"components":[]}'), /非空 components/);
  assert.throws(
    () => parseA2uiAtomPreviewDocument('{"components":[{"id":"other","component":"Text"}]}'),
    /缺少 id 为 root/,
  );
});

test('all registered official basic renderer implementations accept their contract examples', () => {
  for (const componentType of basicCatalog.components.keys()) {
    const source = resolveA2uiAtomPreviewSource({
      id: componentType,
      componentCode: componentType,
      type: componentType,
      nameCn: componentType,
      componentOriginType: 'A2UI_OFFICIAL',
      officialSchema: { type: 'object' },
    });
    assert.equal(source.kind, 'SCHEMA_DERIVED', componentType);
    const processor = new MessageProcessor([basicCatalog], undefined, { version: 'v0.9.1' });
    try {
      processor.processMessages([
        {
          version: 'v0.9.1',
          createSurface: { surfaceId: componentType, catalogId: OFFICIAL_BASIC_CATALOG_ID },
        },
        {
          version: 'v0.9.1',
          updateComponents: { surfaceId: componentType, components: source.document?.components || [] },
        },
        ...(source.document?.dataModel
          ? [{
              version: 'v0.9.1' as const,
              updateDataModel: { surfaceId: componentType, path: '/', value: source.document.dataModel },
            }]
          : []),
      ]);
      assert.ok(processor.model.getSurface(componentType)?.componentsModel.get('root'), componentType);
    } finally {
      processor.model.dispose();
    }
  }
});

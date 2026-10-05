import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
import { buildApplication } from './assets.mjs';

const requireWeb = createRequire(resolve(process.argv[2] || 'apps/digital-employee/web', 'package.json'));
const { basicCatalog } = await import(pathToFileURL(requireWeb.resolve('@a2ui/react/v0_9')));
const application = buildApplication();
let checked = 0;
for (const message of application.showTemplate.messageTemplates) {
  for (const { id, component, ...props } of message.updateComponents?.components || []) {
    const registered = basicCatalog.components.get(component);
    assert.ok(registered, `${application.appCode}/${id}: missing ${component} in locked React catalog`);
    const result = registered.schema.safeParse(props);
    assert.ok(result.success, `${application.appCode}/${id}: ${result.error?.message}`);
    checked += 1;
  }
}
const components = application.showTemplate.messageTemplates[1].updateComponents.components;
const picker = components.find(item => item.id === 'people');
const { id: _id, component, ...props } = picker;
const pickerSchema = basicCatalog.components.get(component).schema;
assert.ok(pickerSchema.safeParse({
  ...props,
  options: [{ label: '姓名：林晓｜电话：138****0001｜爱好：阅读、徒步', value: 'demo-person-001' }],
}).success, 'rich same-row label remains a valid official ChoicePicker option');
assert.equal(pickerSchema.safeParse({ ...props, options: { path: '/options' } }).success, false);
for (const buttonId of ['previous', 'next', 'fillComposer']) {
  const button = components.find(item => item.id === buttonId);
  assert.ok(button.checks?.length, `${buttonId} must expose renderer-enforced disabled validation`);
}
console.log(`PASS ${checked} people-selector components match locked @a2ui/react/v0_9 schemas`);

// Validate authored basic components with the same locked SDK used by the B UI.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
import { buildApplications } from './assets.mjs';

const requireWeb = createRequire(resolve(process.argv[2] || 'apps/digital-employee/web', 'package.json'));
const { basicCatalog } = await import(pathToFileURL(requireWeb.resolve('@a2ui/react/v0_9')));
let checked = 0;
for (const app of buildApplications()) {
  for (const message of app.showTemplate.messageTemplates) {
    for (const { id, component, ...props } of message.updateComponents?.components || []) {
      const registered = basicCatalog.components.get(component);
      if (!registered) continue; // Project-specific components have their own contract tests.
      const result = registered.schema.safeParse(props);
      assert.ok(result.success, `${app.appCode}/${id}: ${result.error?.message}`);
      checked++;
    }
  }
}
const [reading] = buildApplications();
const selection = reading.showTemplate.messageTemplates[1].updateComponents.components[8];
const { id, component, ...props } = selection;
const schema = basicCatalog.components.get(component).schema;
assert.ok(schema.safeParse({ ...props, options: [{ label: '一个真实选项', value: 'point-1' }] }).success);
assert.equal(schema.safeParse({ ...props, options: { path: '/options' } }).success, false);
console.log(`PASS ${checked} basic components match the locked B SDK; concrete choices accepted, path object rejected`);

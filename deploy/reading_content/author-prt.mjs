// @ts-check
import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { ManagementClient, bootstrapBasicAtoms, runPrtAuthoring } from './authoring-core.mjs';
import { validateAssets } from './assets.mjs';

if (process.argv.includes('--check')) {
  console.log(`PASS ${JSON.stringify(validateAssets())}; no HTTP requests made`);
  process.exit(0);
}

const env = name => { assert.ok(process.env[name], `${name} is required`); return process.env[name]; };
assert.equal(env('M_REVIEW_CONFIRM'), 'reading-content-prt-v1', 'explicit reviewed authoring confirmation required');
assert.equal(env('M_FRESH_TEST_DB'), '1', 'Node CLI is restricted to a fresh disposable M database');
const origin = new URL(env('M_ORIGIN'));
assert.equal(origin.protocol, 'http:');
assert.ok(['127.0.0.1', 'localhost', '[::1]'].includes(origin.hostname), 'Node CLI only permits loopback M');
const cookie = env('M_SESSION_COOKIE');
assert.match(cookie, /^a2flow_management_session=[A-Za-z0-9_-]+$/);
const descriptorSetBase64 = (await readFile(env('RPC_DESCRIPTOR_FILE'), 'utf8')).trim();
const functionContract = JSON.parse(await readFile(
  new URL('./digital-employee-functions.json', import.meta.url), 'utf8'));
const client = new ManagementClient({ origin: origin.origin, cookie, signal: AbortSignal.timeout(30 * 60_000), onProgress: message => console.log(`PASS ${message}`) });

if (process.env.M_BOOTSTRAP_BASIC_CATALOG === '1') {
  const webDirectory = env('B_WEB_DIR');
  const requireWeb = createRequire(resolve(webDirectory, 'package.json'));
  const { basicCatalog } = await import(pathToFileURL(requireWeb.resolve('@a2ui/react/v0_9')));
  const { zodToJsonSchema } = await import(pathToFileURL(requireWeb.resolve('zod-to-json-schema')));
  const sample = (schema, depth = 0) => {
    assert.ok(depth < 30, 'schema example recursion limit');
    if ('const' in schema) return schema.const;
    if (schema.enum) return schema.enum[0];
    if ('default' in schema) return schema.default;
    if (schema.anyOf || schema.oneOf) return sample((schema.anyOf || schema.oneOf)[0], depth + 1);
    if (schema.type === 'object') return Object.fromEntries((schema.required || []).map(key => [key, sample(schema.properties[key], depth + 1)]));
    if (schema.type === 'array') return Array.from({ length: schema.minItems || 0 }, () => sample(schema.items, depth + 1));
    if (schema.type === 'boolean') return false;
    if (schema.type === 'number' || schema.type === 'integer') return schema.minimum || 0;
    if (schema.type === 'null') return null;
    return 'example';
  };
  const atoms = [...basicCatalog.components.values()].map(component => {
    const propsSchema = zodToJsonSchema(component.schema, { $refStrategy: 'none' });
    const props = component.schema.parse(sample(propsSchema));
    const eventProperties = Object.fromEntries(Object.entries(propsSchema.properties).filter(([key]) => key === 'action' || key.endsWith('Action')));
    return { componentCode: component.name, type: component.name, nameCn: `基础组件 ${component.name}`, category: 'basic', compositionKind: 'ATOMIC', propsSchema,
      eventSchema: { type: 'object', properties: eventProperties, additionalProperties: false }, childrenConstraint: {},
      validMessageExample: { id: 'example', component: component.name, ...props }, invalidMessageExample: { id: 'invalid', component: component.name, unsupportedProperty: true } };
  });
  await bootstrapBasicAtoms(client, atoms);
}

const result = await runPrtAuthoring(client, {
  descriptorSetBase64, targetKey: env('RPC_TARGET_KEY'), specialistIds: env('M_SPECIALIST_IDS'),
  functionContract,
  includeWorkflow: process.env.M_INCLUDE_WORKFLOW === '1', specialistCode: process.env.M_SPECIALIST_CODE,
  workflowCode: process.env.M_EXISTING_WORKFLOW_CODE,
});
await writeFile(env('OUTPUT_FILE'), JSON.stringify(result, null, 2), { mode: 0o600, flag: 'wx' });
console.log('PASS real M HTTP authoring and PRT publication; ONLINE was intentionally not attempted');

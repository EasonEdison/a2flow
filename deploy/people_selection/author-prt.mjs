// @ts-check
import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { ManagementClient, runPrtAuthoring } from './authoring-core.mjs';
import { validateAssets } from './assets.mjs';

if (process.argv.includes('--check')) {
  console.log(`PASS ${JSON.stringify(validateAssets())}; no HTTP requests made`);
  process.exit(0);
}

const env = name => { assert.ok(process.env[name], `${name} is required`); return process.env[name]; };
assert.equal(env('M_REVIEW_CONFIRM'), 'people-selection-prt-v1', 'explicit reviewed authoring confirmation required');
assert.equal(env('M_FRESH_TEST_DB'), '1', 'Node CLI is restricted to a fresh disposable M database');
const origin = new URL(env('M_ORIGIN'));
assert.equal(origin.protocol, 'http:');
assert.ok(['127.0.0.1', 'localhost', '[::1]'].includes(origin.hostname), 'Node CLI only permits loopback M');
const cookie = env('M_SESSION_COOKIE');
assert.match(cookie, /^a2flow_management_session=[A-Za-z0-9_-]+$/);
const descriptorSetBase64 = (await readFile(env('RPC_DESCRIPTOR_FILE'), 'utf8')).trim();
const client = new ManagementClient({
  origin: origin.origin, cookie, signal: AbortSignal.timeout(30 * 60_000),
  onProgress: message => console.log(`PASS ${message}`),
});
const result = await runPrtAuthoring(client, {
  descriptorSetBase64, targetKey: env('RPC_TARGET_KEY'), specialistIds: env('M_SPECIALIST_IDS'),
});
await writeFile(env('OUTPUT_FILE'), JSON.stringify(result, null, 2), { mode: 0o600, flag: 'wx' });
console.log('PASS people-selection M authoring and PRT publication; ONLINE was intentionally not attempted');

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { callSkillFactory, callSkillFactoryBizRender } from '../api';
import { isManagementLoginRequired, managementFetch, subscribeManagementSession } from './managementSession';

const originalFetch = globalThis.fetch;
let status = 403;
let calls = 0;
let notifications = 0;
const unsubscribe = subscribeManagementSession(() => notifications++);
globalThis.fetch = async () => { calls++; return new Response('{"result":1,"data":{}}', { status }); };
try {
  await assert.rejects(callSkillFactory('SKILL_LIST'), /权限.*403/);
  assert.equal(isManagementLoginRequired(), false, '403 must not become a login prompt or redirect');
  assert.equal(notifications, 0);
  status = 500;
  assert.equal((await managementFetch('/api/management/v2/handler')).status, 500);
  assert.equal(isManagementLoginRequired(), false);
  status = 200;
  assert.deepEqual(await callSkillFactory('SKILL_LIST'), {});
  status = 401;
  await assert.rejects(callSkillFactory('SKILL_LIST'), /登录已过期/);
  await assert.rejects(callSkillFactoryBizRender('SKILL_LIST'), /登录已过期/);
  assert.equal(isManagementLoginRequired(), true);
  assert.equal(notifications, 1, 'concurrent failed requests produce one shared notice');
  assert.equal(calls, 5, 'no automatic request retry');
  unsubscribe();
  const shell = readFileSync(new URL('../main.tsx', import.meta.url), 'utf8');
  assert.match(shell, /href="\/login"/);
  assert.match(shell, /action="\/logout" method="post"/);
  assert.match(shell, /<ManagementSessionNotice\s*\/>/);
  assert.doesNotMatch(shell, /location\.(assign|replace)/, 'no navigation discarding an unsaved draft');
} finally { globalThis.fetch = originalFetch; unsubscribe(); }
console.log('PASS management 401 notice, 403 isolation, account navigation and no retry');

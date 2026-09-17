import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { drafts, digest } from './browser-fixtures.mjs';

const root = path.resolve(import.meta.dirname, '..');
const output = path.resolve(root, '../../..', 'qa-output');
const playwrightPath = process.env.PLAYWRIGHT_PATH;
const chromePath = process.env.CHROME_PATH;
if (!playwrightPath) throw new Error('PLAYWRIGHT_PATH 必须指向已安装的 playwright 模块目录');
if (!chromePath || !fs.existsSync(chromePath)) throw new Error('CHROME_PATH 必须指向可执行的 Chrome');
const require = createRequire(import.meta.url);
const { chromium } = require(playwrightPath);
fs.mkdirSync(output, { recursive: true });

const kinds = Object.keys(drafts);
const clone = (value) => structuredClone(value);
const deferred = () => {
  let release;
  let markStarted;
  const started = new Promise((resolve) => { markStarted = resolve; });
  const blocked = new Promise((resolve) => { release = resolve; });
  return { started, blocked, markStarted, release };
};

async function createHarness(browser, options = {}) {
  const context = await browser.newContext({ viewport: options.viewport ?? { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const unexpected = [];
  const expectedHttpErrors = [];
  const requests = [];
  const documents = clone(options.documents ?? drafts);
  const serverDocuments = clone(options.serverDocuments ?? documents);
  const revisions = Object.fromEntries(kinds.map((kind) => [kind, 1]));
  const draftReads = [];
  const gates = options.gates ?? {};
  let conflictOnce = options.conflictOnce ?? false;
  let reloadFailureOnce = options.reloadFailureOnce ?? false;
  page.on('pageerror', (error) => unexpected.push(error.message));
  page.on('console', (message) => {
    if (message.type() !== 'error') return;
    const text = message.text();
    if (/Failed to load resource: the server responded with a status of (409|503)/.test(text)) expectedHttpErrors.push(text);
    else unexpected.push(text);
  });
  await context.route('**/*', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.hostname !== 'a2flow.test') return route.abort();
    const pathname = decodeURIComponent(url.pathname);
    const reply = (value, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(value) });
    if (pathname === '/management/session') return reply({ userId: `${options.environment?.toLowerCase() ?? 'prt'}-${options.canAuthor === false ? 'reader' : 'admin'}`, environment: options.environment ?? 'PRT', registeredKinds: kinds, canAuthor: options.canAuthor !== false });
    if (pathname.startsWith('/management/assets/')) {
      const kind = pathname.split('/')[3];
      const key = `demo/${kind.toLowerCase()}`;
      const summary = { kind, key, assetId: kind.toLowerCase(), versionId: 'v1', contentDigest: digest, name: `${kind} fixture` };
      if (pathname === `/management/assets/${kind}`) return reply([summary]);
      if (pathname.endsWith('/versions')) return reply({ kind, key, versions: [{ versionId: 'v1', assetId: summary.assetId, contentDigest: digest }, { versionId: 'v0', assetId: `${summary.assetId}-old`, contentDigest: `sha256:${'2'.repeat(64)}` }], serving: { current: 'v1', stable: 'v1', gray: {} }, servingDigest: digest });
      if (pathname.endsWith('/draft')) {
        assert.equal(options.canAuthor !== false, true);
        if (request.method() === 'PUT') {
          const payload = request.postDataJSON();
          requests.push({ type: 'save', kind, payload });
          gates.save?.markStarted();
          if (gates.save) await gates.save.blocked;
          if (conflictOnce) {
            conflictOnce = false;
            return reply({ error: { code: 'DRAFT_REVISION_CONFLICT' } }, 409);
          }
          documents[kind] = clone(payload.document);
          serverDocuments[kind] = clone(payload.document);
          revisions[kind] += 1;
          return reply({ kind, key, revision: revisions[kind], document: serverDocuments[kind], contentDigest: digest, updatedBy: 'fixture-admin' });
        }
        draftReads.push(kind);
        if (reloadFailureOnce && requests.some((item) => item.type === 'save')) {
          reloadFailureOnce = false;
          return reply({ error: { code: 'RELOAD_UNAVAILABLE' } }, 503);
        }
        return reply({ kind, key, revision: revisions[kind], document: serverDocuments[kind], contentDigest: digest, updatedBy: 'fixture-admin' });
      }
      if (pathname.endsWith('/validate')) {
        requests.push({ type: 'validate', kind });
        return reply(options.validation ?? { valid: false, issues: [
          { code: 'INVALID_FIELD', path: '/metadata/name', message: 'exact backend message' },
          { code: 'UNKNOWN_EXTENSION', path: '/extension/mystery', message: 'unknown path remains visible' },
        ] });
      }
      if (pathname.endsWith('/publication-plans')) {
        const payload = request.postDataJSON();
        requests.push({ type: 'prepare', kind, payload });
        return reply({ kind, key, draftRevision: revisions[kind], contentDigest: digest, target: payload.target, status: 'PREPARED_NOT_PUBLISHED', published: false, candidate: clone(documents[kind]) });
      }
      if (pathname.endsWith('/publications')) {
        const payload = request.postDataJSON();
        requests.push({ type: 'publish', kind, payload });
        gates.publish?.markStarted();
        if (gates.publish) await gates.publish.blocked;
        return reply({ status: 'PUBLISHED', published: true, businessCompensated: false });
      }
      if (pathname.endsWith('/rollbacks')) {
        const payload = request.postDataJSON();
        requests.push({ type: 'rollback', kind, payload });
        return reply({ status: 'ROLLED_BACK', published: true, businessCompensated: false });
      }
      return reply({ ...summary, definition: clone(documents[kind]) });
    }
    const file = path.join(root, 'dist', pathname === '/' ? 'index.html' : pathname);
    if (!file.startsWith(path.join(root, 'dist') + path.sep) || !fs.existsSync(file)) return route.fulfill({ status: 404, body: 'Not found' });
    return route.fulfill({ status: 200, contentType: file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html', body: fs.readFileSync(file) });
  });
  await page.goto('http://a2flow.test/');
  await page.getByRole('heading', { name: '保留版本', exact: true }).waitFor();
  const button = (name) => page.getByRole('button', { name, exact: true });
  const selectKind = async (kind) => {
    await page.getByRole('navigation', { name: '资产类型' }).getByRole('button', { name: new RegExp(kind, 'i') }).click();
    await page.getByRole('heading', { name: `${kind.toUpperCase()} · demo/${kind.toLowerCase()}`, exact: true }).waitFor();
  };
  const finish = async (expectedStatuses = []) => {
    assert.equal(await page.locator('vite-error-overlay').count(), 0);
    assert.deepEqual(unexpected, []);
    assert.deepEqual(expectedHttpErrors.map((text) => Number(text.match(/(409|503)/)[1])), expectedStatuses);
    await context.close();
  };
  return { context, page, requests, documents, serverDocuments, revisions, draftReads, button, selectKind, finish };
}

async function assertNoEditRoundtrips(harness) {
  const { page, button, selectKind } = harness;
  const full = page.getByRole('textbox', { name: '结构化草稿 JSON' });
  for (const kind of kinds) {
    await selectKind(kind);
    if (await full.count() === 0) await button('完整 JSON').click();
    assert.deepEqual(JSON.parse(await full.inputValue()), drafts[kind]);
    await button('表单').click();
    assert.equal(await page.getByText('已同步', { exact: true }).count(), 1);
    await button('完整 JSON').click();
    assert.deepEqual(JSON.parse(await full.inputValue()), drafts[kind]);
  }
}

async function runEditorCoverage(browser) {
  const harness = await createHarness(browser);
  const { page, requests, button, selectKind } = harness;
  await assertNoEditRoundtrips(harness);

  await selectKind('Skill');
  await button('表单').click();
  assert.equal(await page.getByRole('status', { name: /所需工具 2 类型错误/ }).getByText('{"extension":1}').count(), 1);
  assert.equal(await page.getByRole('status', { name: /所需工具 3 类型错误/ }).getByText('42').count(), 1);
  assert.equal(await page.getByRole('status', { name: /所需工具 4 类型错误/ }).locator('code').filter({ hasText: /^null$/ }).count(), 1);
  const firstTool = page.getByRole('textbox', { name: '所需工具 1', exact: true });
  await firstTool.fill('duplicate');
  await page.getByRole('button', { name: '添加一项', exact: true }).first().click();
  const lastTool = page.getByRole('textbox', { name: '所需工具 5', exact: true });
  await lastTool.fill('duplicate');
  await lastTool.focus();
  await lastTool.pressSequentially('-typed');
  assert.equal(await lastTool.inputValue(), 'duplicate-typed');
  assert.equal(await lastTool.evaluate((element) => document.activeElement === element && element.selectionStart === element.value.length), true);
  const toolSection = page.getByRole('group', { name: '所需工具' });
  await toolSection.getByRole('button', { name: '上移', exact: true }).last().click();
  assert.equal(await page.getByRole('textbox', { name: '所需工具 4', exact: true }).inputValue(), 'duplicate-typed');
  assert.equal(await page.evaluate(() => document.activeElement?.getAttribute('aria-label') === '上移' && document.activeElement?.closest('.form-row')?.querySelector('input')?.value === 'duplicate-typed'), true);
  await toolSection.getByRole('button', { name: '移除', exact: true }).first().click();
  assert.equal(await page.getByRole('textbox', { name: '所需工具 3', exact: true }).inputValue(), 'duplicate-typed');
  page.once('dialog', (dialog) => dialog.dismiss());
  await page.getByRole('button', { name: '确认移除异常项', exact: true }).first().click();
  assert.equal(await page.getByText('{"extension":1}', { exact: true }).count(), 1);
  page.once('dialog', (dialog) => dialog.accept());
  await page.getByRole('button', { name: '确认移除异常项', exact: true }).first().click();
  await button('保存草稿').click();
  await page.getByText('已同步', { exact: true }).waitFor();
  const skillSaved = requests.filter((item) => item.type === 'save' && item.kind === 'SKILL').at(-1).payload.document;
  assert.equal(JSON.stringify(skillSaved).includes('row-'), false);
  assert.deepEqual(skillSaved.requiredToolNames, [42, 'duplicate-typed', null]);

  await selectKind('Ability');
  await button('完整 JSON').click();
  const full = page.getByRole('textbox', { name: '结构化草稿 JSON' });
  const malformedAbility = clone(drafts.ABILITY);
  malformedAbility.inputBindings = [null, { targetPath: '/x', source: 'UNKNOWN_SOURCE', sourcePath: '/x' }];
  malformedAbility.credentialRequirements = { wrong: true };
  await full.fill(JSON.stringify(malformedAbility));
  await button('表单').click();
  assert.match(await page.locator('.editor-panel').innerText(), /inputBindings\[0\].*null/s);
  assert.match(await page.locator('.editor-panel').innerText(), /不受支持：UNKNOWN_SOURCE/);
  assert.match(await page.locator('.editor-panel').innerText(), /credentialRequirements 不是数组/);
  await button('完整 JSON').click();
  assert.deepEqual(JSON.parse(await full.inputValue()), malformedAbility);

  await selectKind('Application');
  await button('完整 JSON').click();
  const malformedApplication = clone(drafts.APPLICATION);
  malformedApplication.definition.actionPolicies = [42];
  malformedApplication.dependencies = [{ kind: 'UNKNOWN_KIND', key: 'retained' }];
  await full.fill(JSON.stringify(malformedApplication));
  await button('表单').click();
  assert.match(await page.locator('.editor-panel').innerText(), /actionPolicies\[0\].*42/s);
  assert.match(await page.locator('.editor-panel').innerText(), /不受支持：UNKNOWN_KIND/);
  await button('完整 JSON').click();
  assert.deepEqual(JSON.parse(await full.inputValue()), malformedApplication);

  await selectKind('Workflow');
  await button('完整 JSON').click();
  const unsupported = clone(drafts.WORKFLOW);
  unsupported.topology = 'PARALLEL';
  unsupported.nodes = [null, ...unsupported.nodes];
  await full.fill(JSON.stringify(unsupported));
  await button('表单').click();
  assert.match(await page.locator('.editor-panel').innerText(), /PARALLEL 拓扑可保留草稿/);
  assert.match(await page.locator('.editor-panel').innerText(), /nodes\[0\].*null/s);
  await button('完整 JSON').click();
  assert.deepEqual(JSON.parse(await full.inputValue()), unsupported);
  await full.fill(JSON.stringify(drafts.WORKFLOW));
  await button('表单').click();
  const firstNode = page.getByLabel('Node ID').first();
  await firstNode.focus();
  await page.getByRole('button', { name: '下移', exact: true }).first().click();
  assert.equal(await page.getByLabel('Node ID').nth(1).inputValue(), 'one');
  await page.getByRole('button', { name: '添加节点', exact: true }).click();
  await page.getByLabel('Node ID').last().fill('three');
  await page.getByLabel('Skill key').last().fill('demo/three');
  assert.match(await page.getByRole('group', { name: '顺序预览' }).innerText(), /three.*demo\/three/s);
  await page.getByRole('group', { name: 'Nodes' }).getByRole('button', { name: '移除', exact: true }).first().click();
  assert.equal(await page.getByLabel('Node ID').count(), 2);
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 2), false);
  await page.screenshot({ path: path.join(output, 'workflow-mobile.png'), fullPage: false });
  await harness.finish();
}

async function runPendingAndValidation(browser) {
  const harness = await createHarness(browser);
  const { page, button, selectKind } = harness;
  await selectKind('Ability');
  const schema = page.getByLabel('Model argument schema');
  await schema.fill('{unfinished');
  assert.equal(await button('保存草稿').isDisabled(), true);
  await button('完整 JSON').click();
  assert.deepEqual(JSON.parse(await page.getByLabel('结构化草稿 JSON').inputValue()).modelArgumentSchema, drafts.ABILITY.modelArgumentSchema);
  await selectKind('Skill');
  await selectKind('Ability');
  await button('表单').click();
  assert.equal(await schema.inputValue(), '{unfinished');
  page.once('dialog', (dialog) => dialog.dismiss());
  await button('丢弃字段编辑').click();
  assert.equal(await schema.inputValue(), '{unfinished');
  page.once('dialog', (dialog) => dialog.accept());
  await button('丢弃字段编辑').click();
  await schema.fill('{"type":"array","applied":true}');
  await button('应用 JSON').click();
  await button('完整 JSON').click();
  assert.equal(JSON.parse(await page.getByLabel('结构化草稿 JSON').inputValue()).modelArgumentSchema.applied, true);

  await selectKind('Application');
  await button('表单').click();
  const child = page.getByLabel('Parameter schema');
  const parent = page.getByLabel('Surface template');
  await child.fill('{child pending');
  assert.equal(await parent.isDisabled(), true);
  await button('完整 JSON').click();
  const full = page.getByLabel('结构化草稿 JSON');
  let canonical = JSON.parse(await full.inputValue());
  canonical.definition.renderPolicy.interactionMode = 'DISPLAY_ONLY';
  await full.fill(JSON.stringify(canonical));
  await button('表单').click();
  assert.equal(await child.inputValue(), '{child pending');
  assert.equal(await page.getByText(/canonical 字段已改变/).count(), 0);
  page.once('dialog', (dialog) => dialog.accept());
  await button('丢弃字段编辑').click();
  await parent.fill('{"inputSchema":{"type":"object"},"components":[]}');
  assert.equal(await child.isDisabled(), true);
  page.once('dialog', (dialog) => dialog.accept());
  await button('丢弃字段编辑').click();
  await child.fill('{child pending');
  await button('完整 JSON').click();
  canonical = JSON.parse(await full.inputValue());
  canonical.definition.surfaceTemplate.inputSchema = { type: 'array' };
  await full.fill(JSON.stringify(canonical));
  await button('表单').click();
  await page.getByText(/canonical 字段已改变/).waitFor();

  await selectKind('Skill');
  await button('验证已保存草稿').click();
  const known = page.getByRole('button', { name: 'INVALID_FIELD · /metadata/name · exact backend message', exact: true });
  await known.click();
  assert.equal(await page.getByLabel('名称').evaluate((element) => document.activeElement === element), true);
  assert.equal(await page.getByText('UNKNOWN_EXTENSION · /extension/mystery · unknown path remains visible', { exact: true }).count(), 1);
  await page.screenshot({ path: path.join(output, 'validation-desktop.png'), fullPage: false });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 2), false);
  await harness.finish();
}

async function runApplicationPendingRecovery(browser) {
  const harness = await createHarness(browser);
  const { page, button, selectKind, finish } = harness;
  await selectKind('Application');
  const full = page.getByLabel('结构化草稿 JSON');

  for (const malformedDocument of [
    { ...clone(drafts.APPLICATION), definition: null },
    {
      ...clone(drafts.APPLICATION),
      definition: { ...clone(drafts.APPLICATION.definition), surfaceTemplate: null },
    },
  ]) {
    const schema = page.getByLabel('Parameter schema');
    await schema.fill('{exact pending');
    await button('完整 JSON').click();
    assert.deepEqual(JSON.parse(await full.inputValue()), drafts.APPLICATION);
    await full.fill(JSON.stringify(malformedDocument));
    await button('表单').click();
    assert.equal(await page.getByLabel('Parameter schema').inputValue(), '{exact pending');
    assert.equal(await button('丢弃字段编辑').count(), 1);
    await button('完整 JSON').click();
    await full.fill(JSON.stringify(drafts.APPLICATION));
    await button('表单').click();
    assert.equal(await page.getByLabel('Parameter schema').inputValue(), '{exact pending');
    assert.equal(await page.getByText(/canonical 字段已改变/).count(), 0);
    page.once('dialog', (dialog) => dialog.accept());
    await button('丢弃字段编辑').click();
    assert.deepEqual(JSON.parse(await page.getByLabel('Parameter schema').inputValue()), drafts.APPLICATION.definition.surfaceTemplate.inputSchema);
  }

  await finish();
}

async function runConflictReload(browser) {
  const serverDocuments = clone(drafts);
  serverDocuments.ABILITY.defaultSuccessPolicyRef = 'server-latest';
  const harness = await createHarness(browser, { conflictOnce: true, reloadFailureOnce: true, serverDocuments });
  const { page, requests, revisions, button, selectKind, finish } = harness;
  await selectKind('Ability');
  const canonicalField = page.getByLabel('Default success policy');
  await canonicalField.fill('local-canonical');
  await button('保存草稿').click();
  await page.getByText('修订冲突', { exact: true }).waitFor();
  assert.equal(await canonicalField.inputValue(), 'local-canonical');
  const pendingField = page.getByLabel('Model argument schema');
  await pendingField.fill('{exact invalid pending');
  assert.equal(await pendingField.inputValue(), '{exact invalid pending');
  await button('完整 JSON').click();
  assert.equal(JSON.parse(await page.getByLabel('结构化草稿 JSON').inputValue()).defaultSuccessPolicyRef, 'local-canonical');
  await button('表单').click();
  page.once('dialog', (dialog) => dialog.dismiss());
  await button('重新加载最新草稿').click();
  assert.equal(await canonicalField.inputValue(), 'local-canonical');
  assert.equal(await pendingField.inputValue(), '{exact invalid pending');
  assert.equal(requests.filter((item) => item.type === 'save').length, 1);
  page.once('dialog', (dialog) => dialog.accept());
  await button('重新加载最新草稿').click();
  await page.getByText('RELOAD_UNAVAILABLE · HTTP 503', { exact: true }).waitFor();
  assert.equal(await canonicalField.inputValue(), 'local-canonical');
  assert.equal(await pendingField.inputValue(), '{exact invalid pending');
  revisions.ABILITY = 7;
  page.once('dialog', (dialog) => dialog.accept());
  await button('重新加载最新草稿').click();
  await page.getByText('修订 #7 · fixture-admin', { exact: true }).waitFor();
  assert.equal(await canonicalField.inputValue(), 'server-latest');
  assert.deepEqual(JSON.parse(await pendingField.inputValue()), drafts.ABILITY.modelArgumentSchema);
  assert.equal(await page.getByText('存在尚未应用的字段 JSON', { exact: true }).count(), 0);
  await button('完整 JSON').click();
  assert.deepEqual(JSON.parse(await page.getByLabel('结构化草稿 JSON').inputValue()), serverDocuments.ABILITY);
  await finish([409, 503]);
}

async function assertLocked(page) {
  const controls = page.locator('.editor-panel input, .editor-panel textarea, .editor-panel select, .editor-panel button');
  const count = await controls.count();
  for (let index = 0; index < count; index += 1) assert.equal(await controls.nth(index).isDisabled(), true);
  const nav = page.getByRole('navigation', { name: '资产类型' }).getByRole('button');
  for (let index = 0; index < await nav.count(); index += 1) assert.equal(await nav.nth(index).isDisabled(), true);
  assert.equal(await page.getByRole('searchbox', { name: '搜索当前资产类型' }).isDisabled(), true);
  assert.equal(await page.locator('.asset-row').first().isDisabled(), true);
}

async function runBusyAndPublication(browser, environment) {
  const saveGate = deferred();
  const publishGate = deferred();
  const harness = await createHarness(browser, { environment, validation: { valid: true, issues: [], normalized: clone(drafts.SKILL) }, gates: { save: saveGate, publish: publishGate } });
  const { page, requests, button, finish } = harness;
  await page.getByLabel('描述').fill('busy save');
  void button('保存草稿').click();
  await saveGate.started;
  await assertLocked(page);
  saveGate.release();
  await page.getByText('已同步', { exact: true }).waitFor();
  const save = requests.find((item) => item.type === 'save');
  assert.equal(save.payload.expectedRevision, 1);
  assert.equal(save.payload.document.metadata.description, 'busy save');
  await button('验证已保存草稿').click();
  await page.getByText('草稿验证通过', { exact: true }).waitFor();
  const version = page.getByLabel('候选版本标识');
  await version.fill(`${environment.toLowerCase()}-v2`);
  if (environment === 'ONLINE') {
    await page.getByLabel('目标通道').selectOption('GRAY');
    await page.getByLabel('灰度用户 ID').fill('user-a\nuser-b');
  }
  await button('准备未发布候选').click();
  await page.getByText('候选已准备，但尚未发布', { exact: true }).waitFor();
  const prepare = requests.find((item) => item.type === 'prepare');
  assert.equal(prepare.payload.expectedRevision, 2);
  assert.deepEqual(prepare.payload.target, environment === 'ONLINE'
    ? { environment, versionId: 'online-v2', channel: 'GRAY', grayUserIds: ['user-a', 'user-b'] }
    : { environment, versionId: 'prt-v2', channel: 'CURRENT', grayUserIds: [] });
  page.once('dialog', (dialog) => dialog.dismiss());
  await button('确认并显式发布').click();
  assert.equal(requests.filter((item) => item.type === 'publish').length, 0);
  page.once('dialog', (dialog) => dialog.accept());
  void button('确认并显式发布').click();
  await publishGate.started;
  await assertLocked(page);
  assert.equal(await button('确认并显式发布').isDisabled(), true);
  publishGate.release();
  await page.getByText(/发布完成/).waitFor();
  const publish = requests.find((item) => item.type === 'publish');
  assert.equal(publish.payload.expectedServingDigest, digest);
  assert.equal(publish.payload.target.versionId, `${environment.toLowerCase()}-v2`);
  assert.deepEqual(publish.payload.candidate, save.payload.document);

  page.once('dialog', (dialog) => dialog.dismiss());
  await page.getByRole('button', { name: '回滚配置到此版本', exact: true }).last().click();
  assert.equal(requests.filter((item) => item.type === 'rollback').length, 0);
  page.once('dialog', (dialog) => dialog.accept());
  await page.getByRole('button', { name: '回滚配置到此版本', exact: true }).last().click();
  await page.getByText(/配置回滚完成/).waitFor();
  const rollback = requests.find((item) => item.type === 'rollback');
  assert.equal(rollback.payload.expectedServingDigest, digest);
  assert.deepEqual(rollback.payload.target, { environment, versionId: 'v0', channel: environment === 'PRT' ? 'CURRENT' : 'STABLE', grayUserIds: [] });

  await button('验证已保存草稿').click();
  await version.fill(`${environment.toLowerCase()}-v3`);
  await button('准备未发布候选').click();
  await page.getByText('候选已准备，但尚未发布', { exact: true }).waitFor();
  await page.getByLabel('描述').fill('candidate invalidated');
  assert.equal(await page.getByText('候选已准备，但尚未发布', { exact: true }).count(), 0);
  await page.screenshot({ path: path.join(output, `${environment.toLowerCase()}-publication-desktop.png`), fullPage: false });
  await finish();
}

async function runPendingPublicationLockout(browser) {
  const harness = await createHarness(browser, { validation: { valid: true, issues: [] } });
  const { page, button, selectKind, requests, finish } = harness;
  await selectKind('Ability');
  await page.getByLabel('Model argument schema').fill('{pending');
  assert.equal(await button('保存草稿').isDisabled(), true);
  assert.equal(await button('验证已保存草稿').isDisabled(), true);
  assert.equal(await button('准备未发布候选').isDisabled(), true);
  assert.equal(requests.some((item) => ['save', 'validate', 'prepare'].includes(item.type)), false);
  await finish();
}

async function runReader(browser, environment) {
  const harness = await createHarness(browser, { canAuthor: false, environment });
  const { page, requests, draftReads, finish } = harness;
  for (const kind of kinds) {
    await page.getByRole('navigation', { name: '资产类型' }).getByRole('button', { name: new RegExp(kind, 'i') }).click();
    await page.getByRole('heading', { name: `${kind} fixture`, exact: true }).waitFor();
  }
  assert.equal(await page.getByRole('button', { name: '保存草稿', exact: true }).count(), 0);
  assert.equal(await page.locator('.author-workspace').count(), 0);
  assert.equal(draftReads.length, 0);
  assert.equal(requests.length, 0);
  await finish();
}

const browser = await chromium.launch({ headless: true, executablePath: chromePath });
try {
  await runEditorCoverage(browser);
  await runPendingAndValidation(browser);
  await runApplicationPendingRecovery(browser);
  await runConflictReload(browser);
  await runBusyAndPublication(browser, 'PRT');
  await runBusyAndPublication(browser, 'ONLINE');
  await runPendingPublicationLockout(browser);
  await runReader(browser, 'PRT');
  await runReader(browser, 'ONLINE');
  console.log(JSON.stringify({ ok: true, evidence: output }));
} finally {
  await browser.close();
}

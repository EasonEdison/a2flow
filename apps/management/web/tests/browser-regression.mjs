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
const emptyServingDigest = 'sha256:74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b';
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
  await page.addInitScript(() => {
    const original = crypto.subtle.digest.bind(crypto.subtle);
    let releases = [];
    Object.defineProperty(globalThis, '__digestTestControl', { value: {
      defer(value) { globalThis.__deferDigest = value; },
      rejectNext() { globalThis.__rejectNextDigest = true; },
      release() { const pending = releases; releases = []; pending.forEach((resolve) => resolve()); },
      pending() { return releases.length; },
    } });
    Object.defineProperty(crypto.subtle, 'digest', { configurable: true, value: async (...args) => {
      if (globalThis.__deferDigest) await new Promise((resolve) => releases.push(resolve));
      if (globalThis.__rejectNextDigest) { globalThis.__rejectNextDigest = false; throw new Error('injected digest failure'); }
      return original(...args);
    } });
  });
  const unexpected = [];
  const expectedHttpErrors = [];
  const requests = [];
  const documents = clone(options.documents ?? drafts);
  const serverDocuments = clone(options.serverDocuments ?? documents);
  const revisions = Object.fromEntries(kinds.map((kind) => [kind, 1]));
  const draftOnly = Object.fromEntries(kinds.map((kind) => [kind, new Set()]));
  const createdKeys = Object.fromEntries(kinds.map((kind) => [kind, new Set()]));
  const createdVersions = Object.fromEntries(kinds.map((kind) => [kind, new Map()]));
  const retained = Object.fromEntries(kinds.map((kind) => [kind, {
    v1: clone(documents[kind]),
    v0: options.distinctVersions ? { ...clone(documents[kind]), fixtureVersion: 0 } : clone(documents[kind]),
  }]));
  const versions = Object.fromEntries(kinds.map((kind) => [kind, ['v1', 'v0']]));
  const draftReads = [];
  const listReads = [];
  const gates = options.gates ?? {};
  let conflictOnce = options.conflictOnce ?? false;
  let reloadFailureOnce = options.reloadFailureOnce ?? false;
  let referenceListFailurePending = options.referenceListError ?? false;
  let referenceListDelayPending = options.referenceListDelay ?? false;
  page.on('pageerror', (error) => unexpected.push(error.message));
  page.on('console', (message) => {
    if (message.type() !== 'error') return;
    const text = message.text();
    if (/Failed to load resource: the server responded with a status of (400|404|409|503)/.test(text)) expectedHttpErrors.push(text);
    else unexpected.push(text);
  });
  await context.route('**/*', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.hostname !== 'localhost') return route.abort();
    const pathname = decodeURIComponent(url.pathname);
    const reply = (value, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(value) });
    if (pathname === '/management/session') return reply({ userId: `${options.environment?.toLowerCase() ?? 'prt'}-${options.canAuthor === false ? 'reader' : 'admin'}`, environment: options.environment ?? 'PRT', registeredKinds: kinds, canAuthor: options.canAuthor !== false });
    if (pathname.startsWith('/management/assets/')) {
      const kind = pathname.split('/')[3];
      const key = pathname.split('/').slice(4, -1).join('/') || `demo/${kind.toLowerCase()}`;
      const defaultKey = `demo/${kind.toLowerCase()}`;
      const activeKey = pathname === `/management/assets/${kind}` ? defaultKey : key;
      const summary = {
        kind, key: defaultKey, assetId: kind.toLowerCase(), versionId: 'v1', contentDigest: digest,
        name: `${kind} fixture`, description: kind === 'ABILITY' ? 'Business lookup capability' : kind === 'APPLICATION' ? 'Interactive confirmation application' : undefined,
      };
      if (pathname === `/management/assets/${kind}`) {
        listReads.push(kind);
        if (referenceListDelayPending && options.referenceListErrorNow && kind === 'ABILITY') {
          gates.references?.markStarted();
          if (gates.references) await gates.references.blocked;
          referenceListDelayPending = false;
        }
        if ((referenceListFailurePending || options.referenceListErrorNow) && kind === 'ABILITY') {
          referenceListFailurePending = false;
          options.referenceListErrorNow = false;
          return reply({ error: { code: 'ABILITY_CATALOG_UNAVAILABLE' } }, 503);
        }
        return reply([
          summary,
          ...(kind === 'ABILITY' ? [{ ...summary, key: 'demo.lookup', assetId: 'ability-lookup', name: 'Order lookup', description: 'Business lookup capability' }] : []),
          ...(kind === 'APPLICATION' ? [{ ...summary, key: 'demo.confirm', assetId: 'application-confirm', name: 'Confirmation UI', description: 'Interactive confirmation application' }] : []),
          ...[...createdKeys[kind]].map((item) => ({
            kind, key: item,
            ...(draftOnly[kind].has(item)
              ? { draftOnly: true, draftRevision: revisions[kind] }
              : { assetId: `${kind.toLowerCase()}-created`, versionId: [...createdVersions[kind].get(item).keys()].at(-1), contentDigest: digest }),
          })),
        ]);
      }
      const versionMatch = pathname.match(/\/versions\/([^/]+)$/);
      if (versionMatch) {
        if (options.missingVersion === versionMatch[1]) return reply({ error: { code: 'VERSION_NOT_FOUND' } }, 404);
        const versionKey = pathname.split('/').slice(4, -2).join('/');
        const created = createdVersions[kind].get(versionKey)?.get(versionMatch[1]);
        const authored = versionKey === defaultKey
          ? clone(retained[kind][versionMatch[1]] ?? documents[kind])
          : clone(created ?? serverDocuments[kind]);
        return reply({ kind, key: versionKey, versionId: versionMatch[1], contentDigest: digest, document: authored });
      }
      if (pathname.endsWith('/versions')) {
        if (options.historyError && kind === 'ABILITY') return reply({ error: { code: 'HISTORY_UNAVAILABLE' } }, 503);
        if (draftOnly[kind].has(activeKey)) return reply({ kind, key: activeKey, versions: [], serving: null, servingDigest: emptyServingDigest });
        const activeVersions = activeKey === defaultKey
          ? versions[kind]
          : [...(createdVersions[kind].get(activeKey)?.keys() ?? [])];
        const firstVersion = activeVersions.at(-1) ?? null;
        return reply({ kind, key: activeKey, versions: activeVersions.map((versionId) => ({ versionId, assetId: summary.assetId, contentDigest: digest })), serving: firstVersion ? { current: firstVersion, stable: firstVersion, gray: null, grayUserIds: [] } : null, servingDigest: firstVersion ? digest : emptyServingDigest });
      }
      if (pathname.endsWith('/comparison-documents')) {
        const comparisonRequest = { type: 'compare', kind, key: activeKey, payload: request.postDataJSON() };
        requests.push(comparisonRequest);
        options.compareErrorOnce = options.compareErrorOnce ?? false;
        if (options.compareErrorOnce) {
          options.compareErrorOnce = false;
          return reply({ error: { code: 'COMPARISON_UNAVAILABLE' } }, 503);
        }
        gates.compare?.markStarted();
        if (gates.compare) await gates.compare.blocked;
        return reply(clone(comparisonRequest.payload.document));
      }
      if (pathname.endsWith('/draft')) {
        assert.equal(options.canAuthor !== false, true);
        if (request.method() === 'POST') {
          requests.push({ type: 'create', kind, key: activeKey });
          if (options.createError || draftOnly[kind].has(activeKey) || activeKey === defaultKey) {
            return reply({ error: { code: options.createError ?? 'ASSET_ALREADY_EXISTS' } }, options.createError ? 400 : 409);
          }
          const templates = {
            SKILL: { metadata: { name: activeKey.split('/').at(-1), description: '待配置' }, skillMd: `---\nname: ${activeKey.split('/').at(-1)}\ndescription: 待配置\n---\n\n`, requiredToolNames: [], abilityBindings: [], applicationBindings: [], resources: [] },
            ABILITY: { abilityKey: activeKey, adapterOperationRef: '', credentialRequirements: [], defaultSuccessPolicyRef: '', inputBindings: [], modelArgumentSchema: {}, outputSchema: {}, resolvedInputSchema: {}, resultInterpretationPolicies: [] },
            APPLICATION: { definition: { asset: { kind: 'APPLICATION', applicationKey: activeKey, protocolProfileRef: '', componentCatalogRef: '' }, renderPolicy: { tool: 'render_application', interactionMode: 'DISPLAY_ONLY', requiresPause: false }, interactionPolicy: { bindingScope: 'NONE', ordinaryChatMayResume: false }, versionAdmissionPolicy: { compareBeforeExecution: true, compareBeforeContinue: true, compareBeforeAction: true, onMismatch: 'RESET_REQUIRED' }, actionPolicies: [], retryPolicy: { allowedReasons: ['RENDER_FAILED'] }, finalizerPolicy: { mayOverrideBusinessFacts: false, mayBypassRequiredInteraction: false }, surfaceTemplate: { surfaceKey: '', rootId: '', inputSchema: {}, components: [] } }, dependencies: [] },
            WORKFLOW: { definitionKey: activeKey, topology: 'SEQUENTIAL', nodes: [] },
          };
          documents[kind] = clone(templates[kind]);
          serverDocuments[kind] = clone(templates[kind]);
          revisions[kind] = 1;
          draftOnly[kind].add(activeKey);
          createdKeys[kind].add(activeKey);
          createdVersions[kind].set(activeKey, new Map());
          return reply({ kind, key: activeKey, revision: 1, document: serverDocuments[kind], contentDigest: digest, updatedBy: 'fixture-admin' });
        }
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
        const normalized = clone(documents[kind]);
        return reply(options.validation ?? { valid: false, issues: [
          { code: 'INVALID_FIELD', path: '/metadata/name', message: 'exact backend message' },
          { code: 'UNKNOWN_EXTENSION', path: '/extension/mystery', message: 'unknown path remains visible' },
        ], normalized });
      }
      if (pathname.endsWith('/publication-plans')) {
        const payload = request.postDataJSON();
        requests.push({ type: 'prepare', kind, key: activeKey, payload });
        return reply({ kind, key: activeKey, draftRevision: revisions[kind], contentDigest: digest, target: payload.target, status: 'PREPARED_NOT_PUBLISHED', published: false, candidate: clone(documents[kind]) });
      }
      if (pathname.endsWith('/publications')) {
        const payload = request.postDataJSON();
        requests.push({ type: 'publish', kind, key: activeKey, payload });
        gates.publish?.markStarted();
        if (gates.publish) await gates.publish.blocked;
        if (draftOnly[kind].has(activeKey) && options.environment === 'ONLINE' && payload.target.channel === 'GRAY') {
          return reply({ error: { code: 'INVALID_ONLINE_TARGET' } }, 400);
        }
        draftOnly[kind].delete(activeKey);
        if (activeKey === defaultKey) {
          retained[kind][payload.target.versionId] = clone(documents[kind]);
          if (!versions[kind].includes(payload.target.versionId)) versions[kind].push(payload.target.versionId);
        } else {
          if (!createdVersions[kind].has(activeKey)) createdVersions[kind].set(activeKey, new Map());
          createdVersions[kind].get(activeKey).set(payload.target.versionId, clone(documents[kind]));
        }
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
  await page.goto('http://localhost/');
  await page.getByRole('heading', { name: '保留版本', exact: true }).waitFor();
  const button = (name) => page.getByRole('button', { name, exact: true });
  const selectKind = async (kind) => {
    await page.getByRole('navigation', { name: '资产类型' }).getByRole('button', { name: new RegExp(kind, 'i') }).click();
    await page.getByRole('heading', { name: `${kind.toUpperCase()} · demo/${kind.toLowerCase()}`, exact: true }).waitFor();
  };
  const finish = async (expectedStatuses = []) => {
    assert.equal(await page.locator('vite-error-overlay').count(), 0);
    assert.deepEqual(unexpected, []);
    assert.deepEqual(expectedHttpErrors.map((text) => Number(text.match(/(400|404|409|503)/)[1])), expectedStatuses);
    await context.close();
  };
  return { context, page, requests, documents, serverDocuments, revisions, draftReads, listReads, button, selectKind, finish };
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

async function runSkillWorkbench(browser) {
  const harness = await createHarness(browser);
  const { page, requests, listReads, button, selectKind, finish } = harness;
  const preview = page.locator('.author-workspace .markdown-preview');
  await preview.waitFor();
  assert.equal(await preview.getByRole('heading', { name: 'Plan', exact: true }).count(), 1);
  assert.equal(await preview.locator('script,img,a').count(), 0);
  assert.equal(await page.evaluate(() => globalThis.pwned), undefined);
  const instruction = page.getByLabel('SKILL.md（不会自动改写 frontmatter）');
  await instruction.fill('---\nname: plan\ndescription: Plan safely\n---\n\n# Updated\n\n- item');
  await preview.getByRole('heading', { name: 'Updated', exact: true }).waitFor();

  const bindings = page.getByRole('group', { name: 'Skill 绑定工作台' });
  await bindings.waitFor();
  assert.match(await bindings.innerText(), /Business abilities.*2 个绑定.*2 个可用/s);
  assert.match(await bindings.innerText(), /A2UI Applications.*1 个绑定.*2 个可用/s);
  assert.equal(await bindings.locator('code').filter({ hasText: /^missing\.ability$/ }).count(), 1);
  assert.equal(await bindings.getByText('当前环境不可用', { exact: true }).count(), 1);
  const bindingListReads = [...listReads];
  await bindings.getByRole('searchbox', { name: '搜索 Business abilities' }).fill('lookup');
  assert.equal(await bindings.locator('code').filter({ hasText: /^demo\.lookup$/ }).count(), 2);
  assert.equal(await bindings.getByRole('button', { name: '绑定 demo.lookup', exact: true }).isDisabled(), true);
  assert.deepEqual(listReads, bindingListReads);
  await bindings.getByRole('button', { name: '查看详情', exact: true }).first().click();
  await page.getByRole('navigation', { name: '资产类型' }).getByRole('button', { name: /Ability/i }).evaluate((element) => {
    if (!element.classList.contains('active')) throw new Error('detail navigation did not activate Ability');
  });
  await selectKind('Skill');
  assert.equal(await page.getByLabel('SKILL.md（不会自动改写 frontmatter）').inputValue(), '---\nname: plan\ndescription: Plan safely\n---\n\n# Updated\n\n- item');
  const reopenedBindings = page.getByRole('group', { name: 'Skill 绑定工作台' });
  await reopenedBindings.getByRole('button', { name: '绑定 demo/ability', exact: true }).click();
  await reopenedBindings.getByRole('button', { name: '绑定 demo/application', exact: true }).click();
  await button('完整 JSON').click();
  const bindingDraft = JSON.parse(await page.getByLabel('结构化草稿 JSON').inputValue());
  assert.deepEqual(bindingDraft.abilityBindings, ['demo.lookup', 'missing.ability', 'demo/ability']);
  assert.deepEqual(bindingDraft.applicationBindings, ['demo.confirm', 'demo/application']);
  assert.deepEqual(bindingDraft.resources, drafts.SKILL.resources);
  await button('表单').click();
  page.once('dialog', (dialog) => dialog.dismiss());
  await bindings.getByRole('button', { name: '解除绑定 missing.ability', exact: true }).click();
  assert.equal(await bindings.locator('code').filter({ hasText: /^missing\.ability$/ }).count(), 1);
  page.once('dialog', (dialog) => dialog.accept());
  await bindings.getByRole('button', { name: '解除绑定 missing.ability', exact: true }).click();
  assert.equal(await bindings.locator('code').filter({ hasText: /^missing\.ability$/ }).count(), 0);
  assert.equal(await page.getByLabel('SKILL.md（不会自动改写 frontmatter）').inputValue(), '---\nname: plan\ndescription: Plan safely\n---\n\n# Updated\n\n- item');
  assert.equal(await button('保存草稿').isDisabled(), false);

  await page.getByRole('navigation', { name: '资源导航' }).getByRole('button', { name: 'guide.md' }).click();
  const resourceText = page.getByLabel('资源文本');
  await resourceText.fill('你好 resource');
  assert.equal(await button('保存草稿').isDisabled(), true);
  await button('完整 JSON').click();
  await selectKind('Ability');
  await selectKind('Skill');
  await button('表单').click();
  assert.equal(await page.getByLabel('资源文本').inputValue(), '你好 resource');
  await button('应用资源文本').click();
  await page.waitForTimeout(100);
  assert.equal(await page.getByText('RESOURCE_CONFLICT', { exact: true }).count(), 0);
  await page.getByLabel('新文本资源路径').fill('../blocked.txt');
  assert.equal(await button('添加文本资源').isDisabled(), true);
  await page.getByLabel('新文本资源路径').fill('notes/new.txt');
  await button('添加文本资源').click();
  await page.waitForTimeout(200);
  assert.match(await page.getByRole('group', { name: '资源工作台' }).innerText(), /notes\/new\.txt/);

  await page.getByLabel('上传资源文件').setInputFiles({ name: 'blocked.exe', mimeType: 'application/octet-stream', buffer: Buffer.from('x') });
  await page.getByText('UNSUPPORTED_FILE_TYPE', { exact: true }).waitFor();
  await page.getByLabel('上传资源文件').setInputFiles({ name: 'upload.txt', mimeType: 'text/plain', buffer: Buffer.from('upload exact', 'utf8') });
  await page.getByRole('navigation', { name: '资源导航' }).getByRole('button', { name: 'upload.txt' }).waitFor();
  page.once('dialog', (dialog) => dialog.dismiss());
  await button('移除资源').click();
  assert.equal(await page.getByRole('navigation', { name: '资源导航' }).getByRole('button', { name: 'upload.txt' }).count(), 1);
  page.once('dialog', (dialog) => dialog.accept());
  await button('移除资源').click();
  assert.equal(await page.getByRole('navigation', { name: '资源导航' }).getByRole('button', { name: 'upload.txt' }).count(), 0);

  await button('保存草稿').click();
  await page.getByText('已同步', { exact: true }).waitFor();
  const saved = requests.filter((item) => item.type === 'save' && item.kind === 'SKILL').at(-1).payload.document;
  assert.equal(Buffer.from(saved.resources[0].base64, 'base64').toString('utf8'), '你好 resource');
  assert.equal(saved.resources[0].byteSize, Buffer.byteLength('你好 resource'));
  assert.match(saved.resources[0].contentDigest, /^sha256:[0-9a-f]{64}$/);
  assert.equal(saved.resources[1].logicalPath, 'notes/new.txt');
  await page.reload();
  await preview.getByRole('heading', { name: 'Updated', exact: true }).waitFor();
  await button('完整 JSON').click();
  const reloadedDraft = JSON.parse(await page.getByLabel('结构化草稿 JSON').inputValue());
  assert.deepEqual(reloadedDraft.abilityBindings, ['demo.lookup', 'demo/ability']);
  assert.deepEqual(reloadedDraft.applicationBindings, ['demo.confirm', 'demo/application']);
  await button('表单').click();
  await page.getByRole('navigation', { name: '资源导航' }).getByRole('button', { name: 'guide.md' }).click();
  assert.equal(await page.getByLabel('资源文本').inputValue(), '你好 resource');
  await page.screenshot({ path: path.join(output, 'skill-workbench-desktop.png'), fullPage: false });
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 2), false);
  await page.screenshot({ path: path.join(output, 'skill-workbench-narrow.png'), fullPage: false });
  await finish();
}

async function runDeferredResourceIntegrity(browser) {
  const documents = clone(drafts);
  documents.SKILL.resources.push({ ...clone(documents.SKILL.resources[0]), logicalPath: 'duplicate.md' });
  const harness = await createHarness(browser, { documents });
  const { page, button, selectKind, finish } = harness;
  const resourceNav = page.getByRole('navigation', { name: '资源导航' });
  await page.getByText('资源身份冲突', { exact: true }).waitFor();
  assert.equal(await page.getByLabel('资源文本').count(), 0);
  assert.equal(await button('移除资源').isDisabled(), true);

  await button('完整 JSON').click();
  const full = page.getByLabel('结构化草稿 JSON');
  const repaired = JSON.parse(await full.inputValue());
  repaired.resources = [repaired.resources[0]];
  await full.fill(JSON.stringify(repaired));
  await button('表单').click();
  await resourceNav.getByRole('button', { name: 'guide.md' }).click();
  const text = page.getByLabel('资源文本');
  await text.fill('first pending');
  await page.evaluate(() => globalThis.__digestTestControl.rejectNext());
  await button('应用资源文本').click();
  await page.getByText('SHA256_DIGEST_FAILED', { exact: true }).waitFor();
  assert.equal(await text.inputValue(), 'first pending');
  await button('完整 JSON').click();
  assert.equal(Buffer.from(JSON.parse(await full.inputValue()).resources[0].base64, 'base64').toString('utf8'), 'secret-bytes');
  await button('表单').click();
  await button('应用资源文本').waitFor({ state: 'visible' });
  await page.waitForFunction(() => {
    const candidate = [...document.querySelectorAll('button')].find((element) => element.textContent === '应用资源文本');
    return candidate && !candidate.disabled;
  });

  await page.evaluate(() => globalThis.__digestTestControl.defer(true));
  void button('应用资源文本').click();
  await page.waitForFunction(() => globalThis.__digestTestControl.pending() === 1);
  await text.fill('newer pending');
  await page.evaluate(() => globalThis.__digestTestControl.release());
  await page.waitForTimeout(50);
  assert.equal(await text.inputValue(), 'newer pending');
  await button('完整 JSON').click();
  assert.equal(Buffer.from(JSON.parse(await full.inputValue()).resources[0].base64, 'base64').toString('utf8'), 'secret-bytes');
  await button('表单').click();

  const upload = page.getByLabel('上传资源文件');
  await upload.setInputFiles({ name: 'stale.txt', mimeType: 'text/plain', buffer: Buffer.from('stale upload') });
  await page.waitForFunction(() => globalThis.__digestTestControl.pending() === 1);
  await selectKind('Ability');
  await page.evaluate(() => { globalThis.__digestTestControl.defer(false); globalThis.__digestTestControl.release(); });
  await selectKind('Skill');
  assert.equal(await resourceNav.getByRole('button', { name: 'stale.txt' }).count(), 0);
  await button('完整 JSON').click();
  const preserved = JSON.parse(await full.inputValue());
  assert.equal(Buffer.from(preserved.resources[0].base64, 'base64').toString('utf8'), 'secret-bytes');
  await finish();
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
  assert.equal(await page.locator('.editor-panel').getByText('{"extension":1}', { exact: true }).count(), 1);
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
  await page.getByLabel('Skill key').last().selectOption('demo/skill');
  assert.match(await page.getByRole('group', { name: '顺序预览' }).innerText(), /three.*demo\/skill/s);
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

  const rollbackV0 = page.locator('.version-row').filter({ hasText: 'v0' }).getByRole('button', { name: '回滚配置到此版本', exact: true });
  page.once('dialog', (dialog) => dialog.dismiss());
  await rollbackV0.click();
  assert.equal(requests.filter((item) => item.type === 'rollback').length, 0);
  page.once('dialog', (dialog) => dialog.accept());
  await rollbackV0.click();
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

async function runBindingCatalogStaleState(browser) {
  const referenceGate = deferred();
  const options = { gates: { references: referenceGate }, referenceListDelay: true, historyError: true };
  const harness = await createHarness(browser, options);
  const { page, button, selectKind, finish } = harness;
  const bindings = page.getByRole('group', { name: 'Skill 绑定工作台' });
  const section = bindings.locator('section[aria-label="Business abilities"]');
  await section.waitFor();
  const bind = section.getByRole('button', { name: '绑定 demo/ability', exact: true });
  await bind.waitFor();
  assert.equal(await bind.isDisabled(), false);
  options.referenceListErrorNow = true;
  const retry = await page.evaluateHandle(() => {
    const root = document.querySelector('#root');
    const key = Object.keys(root ?? {}).find((item) => item.startsWith('__reactContainer'));
    const stack = key ? [root[key]] : [];
    const seen = new Set();
    while (stack.length) {
      const fiber = stack.pop();
      if (!fiber || seen.has(fiber)) continue;
      seen.add(fiber);
      if (fiber.memoizedProps?.references?.retry) return fiber.memoizedProps.references.retry;
      stack.push(fiber.child, fiber.sibling);
    }
    return null;
  });
  await retry.evaluate((callback) => callback());
  await selectKind('Skill');
  const staleBindings = page.getByRole('group', { name: 'Skill 绑定工作台' });
  const staleSection = staleBindings.locator('section[aria-label="Business abilities"]');
  const staleBind = staleSection.getByRole('button', { name: '绑定 demo/ability', exact: true });
  await referenceGate.started;
  assert.equal(await staleBind.count(), 1);
  assert.equal(await staleBind.isDisabled(), true);
  await staleBind.dispatchEvent('click');
  await button('完整 JSON').click();
  const full = page.getByLabel('结构化草稿 JSON');
  assert.equal(JSON.parse(await full.inputValue()).abilityBindings.includes('demo/ability'), false);
  await button('表单').click();
  referenceGate.release();
  await staleSection.getByText(/目录加载失败：ABILITY_CATALOG_UNAVAILABLE · HTTP 503/).waitFor();
  assert.equal(await staleBind.count(), 1);
  assert.equal(await staleBind.isDisabled(), true);
  await staleBind.dispatchEvent('click');
  await button('完整 JSON').click();
  assert.equal(JSON.parse(await full.inputValue()).abilityBindings.includes('demo/ability'), false);
  await finish([503, 503, 503]);
}

async function runBindingCatalogFailure(browser) {
  const harness = await createHarness(browser, { referenceListError: true });
  const { page, button, finish } = harness;
  const bindings = page.getByRole('group', { name: 'Skill 绑定工作台' });
  await bindings.getByText(/目录加载失败：ABILITY_CATALOG_UNAVAILABLE · HTTP 503/).waitFor();
  assert.equal(await bindings.locator('code').filter({ hasText: /^demo\.lookup$/ }).count(), 1);
  assert.equal(await bindings.locator('code').filter({ hasText: /^missing\.ability$/ }).count(), 1);
  assert.equal(await bindings.getByText('未知（目录错误）', { exact: true }).count(), 2);
  assert.equal(await bindings.getByText('当前环境不可用', { exact: true }).count(), 0);
  assert.equal(await bindings.getByRole('group', { name: 'Business abilities' }).getByRole('button', { name: /^绑定 / }).count(), 0);
  assert.equal(await button('保存草稿').isDisabled(), true);
  await finish([503]);
}

async function runReader(browser, environment) {
  const harness = await createHarness(browser, { canAuthor: false, environment });
  const { page, requests, draftReads, finish } = harness;
  for (const kind of kinds) {
    await page.getByRole('navigation', { name: '资产类型' }).getByRole('button', { name: new RegExp(kind, 'i') }).click();
    await page.getByRole('heading', { name: `${kind} fixture`, exact: true }).waitFor();
  }
  assert.equal(await page.getByRole('button', { name: '保存草稿', exact: true }).count(), 0);
  assert.equal(await page.getByRole('button', { name: '新建', exact: true }).count(), 0);
  assert.equal(await page.locator('.author-workspace').count(), 0);
  assert.equal(draftReads.length, 0);
  assert.equal(requests.length, 0);
  await finish();
}

async function runCreateDraftFlows(browser) {
  const harness = await createHarness(browser);
  const { page, requests, button, selectKind, finish } = harness;
  for (const kind of kinds) {
    await selectKind(kind);
    await button('新建').click();
    const dialog = page.getByRole('dialog', { name: `新建 ${kind}` });
    const key = `new/${kind.toLowerCase()}`;
    await dialog.getByRole('textbox', { name: '不可变 Key' }).fill(key);
    await dialog.getByRole('button', { name: '取消' }).click();
    assert.equal(requests.filter((item) => item.type === 'create' && item.kind === kind).length, 0);
    await button('新建').click();
    await page.getByRole('dialog', { name: `新建 ${kind}` }).getByRole('textbox', { name: '不可变 Key' }).fill(key);
    await page.getByRole('dialog', { name: `新建 ${kind}` }).getByRole('button', { name: '创建草稿' }).click();
    await page.getByText('仅草稿', { exact: true }).first().waitFor();
    await page.getByText('该资产尚无已发布版本，无法比较。', { exact: true }).waitFor();
    await page.reload();
    await page.getByRole('button', { name: new RegExp(kind, 'i') }).click();
    await page.getByText(key, { exact: true }).click();
    await page.getByText('仅草稿', { exact: true }).first().waitFor();
  }
  await button('新建').click();
  await page.getByRole('dialog').getByRole('textbox', { name: '不可变 Key' }).fill('demo/workflow');
  await page.getByRole('dialog').getByRole('button', { name: '创建草稿' }).click();
  await page.getByText('ASSET_ALREADY_EXISTS · HTTP 409', { exact: true }).waitFor();
  assert.equal(await page.getByRole('dialog').getByRole('textbox', { name: '不可变 Key' }).inputValue(), 'demo/workflow');
  await finish([409]);
}

async function runFirstPublishFlows(browser, environment) {
  const harness = await createHarness(browser, {
    environment,
    validation: { valid: true, issues: [] },
  });
  const { page, requests, listReads, button, selectKind, finish } = harness;
  for (const kind of kinds) {
    await selectKind(kind);
    await button('新建').click();
    const key = `first/${environment.toLowerCase()}/${kind.toLowerCase()}`;
    const dialog = page.getByRole('dialog', { name: `新建 ${kind}` });
    await dialog.getByRole('textbox', { name: '不可变 Key' }).fill(key);
    await dialog.getByRole('button', { name: '创建草稿' }).click();
    await page.getByText('该资产尚无已发布版本，无法比较。', { exact: true }).waitFor();
    await button('完整 JSON').click();
    await page.getByLabel('结构化草稿 JSON').fill(JSON.stringify(drafts[kind]));
    await button('保存草稿').click();
    await page.getByText('已同步', { exact: true }).waitFor();
    await button('验证已保存草稿').click();
    await page.getByText('草稿验证通过', { exact: true }).waitFor();
    const versionId = `first-${kind.toLowerCase()}`;
    await page.getByLabel('候选版本标识').fill(versionId);
    if (environment === 'ONLINE') {
      await page.getByLabel('目标通道').selectOption('GRAY');
      await page.getByLabel('灰度用户 ID').fill('first-user');
      await button('准备未发布候选').click();
      await page.getByText('候选已准备，但尚未发布', { exact: true }).waitFor();
      page.once('dialog', (dialogEvent) => dialogEvent.accept());
      await button('确认并显式发布').click();
      await page.getByText('INVALID_ONLINE_TARGET · HTTP 400', { exact: true }).waitFor();
      assert.equal(await page.getByText('仅草稿', { exact: true }).count() > 0, true);
      await page.getByLabel('目标通道').selectOption('STABLE');
      await button('准备未发布候选').click();
      await page.getByText('候选已准备，但尚未发布', { exact: true }).waitFor();
    } else {
      await button('准备未发布候选').click();
      await page.getByText('候选已准备，但尚未发布', { exact: true }).waitFor();
    }
    const prepare = requests.filter((item) => item.type === 'prepare' && item.kind === kind && item.key === key).at(-1);
    assert.equal(prepare.payload.expectedRevision, 2);
    assert.deepEqual(prepare.payload.target, {
      environment,
      versionId,
      channel: environment === 'PRT' ? 'CURRENT' : 'STABLE',
      grayUserIds: [],
    });
    page.once('dialog', (dialogEvent) => dialogEvent.accept());
    await button('确认并显式发布').click();
    await page.locator('.version-row').filter({ hasText: versionId }).waitFor();
    const publish = requests.filter((item) => item.type === 'publish' && item.kind === kind && item.key === key).at(-1);
    assert.equal(publish.payload.expectedServingDigest, emptyServingDigest);
    assert.deepEqual(publish.payload.candidate, drafts[kind]);
    assert.equal(await page.getByText('仅草稿', { exact: true }).count(), 0);
    await page.locator('.version-row').filter({ hasText: versionId }).waitFor();
    assert.equal(listReads.filter((item) => item === kind).length >= 2, true);
    await page.reload();
    await page.getByRole('button', { name: new RegExp(kind, 'i') }).click();
    await page.getByText(key, { exact: true }).click();
    await page.locator('.version-row').filter({ hasText: versionId }).waitFor();
    assert.equal(await page.getByText('仅草稿', { exact: true }).count(), 0);
  }
  await page.screenshot({ path: path.join(output, `${environment.toLowerCase()}-first-publication-desktop.png`), fullPage: false });
  await finish(environment === 'ONLINE' ? [400, 400, 400, 400] : []);
}

async function runComparisonAndReferenceCoverage(browser) {
  const harness = await createHarness(browser);
  const { page, requests, button, selectKind, finish } = harness;
  await button('比较当前草稿').click();
  await page.getByText('没有差异。', { exact: true }).waitFor();
  assert.equal(requests.filter((item) => item.type === 'compare').length, 1);
  await page.getByLabel('描述').fill('changed comparison value');
  assert.equal(requests.filter((item) => item.type === 'compare').length, 1);
  await page.getByText('比较内容已过时，请显式刷新后再查看当前 canonical 草稿。', { exact: true }).waitFor();
  await button('刷新过时比较').click();
  await page.getByText('/metadata/description', { exact: true }).waitFor();
  await page.getByLabel('比较右侧').selectOption('v0');
  await page.getByText('没有差异。', { exact: true }).waitFor();

  await selectKind('Workflow');
  await page.getByLabel('Skill key').first().selectOption('demo/skill');
  assert.equal(await page.getByLabel('Skill key').first().inputValue(), 'demo/skill');
  await selectKind('Application');
  assert.equal(await page.getByLabel('abilityReleaseRef key').first().inputValue(), 'demo.confirm');
  assert.equal(await page.getByLabel('abilityReleaseRef version').first().inputValue(), 'v1');
  await button('完整 JSON').click();
  const malformed = JSON.parse(await page.getByLabel('结构化草稿 JSON').inputValue());
  malformed.definition.actionPolicies[0].abilityReleaseRef = { malformed: true };
  await page.getByLabel('结构化草稿 JSON').fill(JSON.stringify(malformed));
  await button('表单').click();
  assert.equal(await page.getByText(/当前值类型不受支持.*malformed.*原值已保留/).count(), 1);
  assert.equal(await page.getByLabel('abilityReleaseRef key').isDisabled(), true);
  await finish();
}

async function runDeferredComparison(browser) {
  const compareGate = deferred();
  const harness = await createHarness(browser, { gates: { compare: compareGate }, distinctVersions: true });
  const { page, requests, button, selectKind, finish } = harness;
  void button('比较当前草稿').click();
  await compareGate.started;
  await page.getByLabel('描述').fill('edited while comparing');
  compareGate.release();
  await page.getByText('比较内容已过时，请显式刷新后再查看当前 canonical 草稿。', { exact: true }).waitFor();
  assert.equal(requests.filter((item) => item.type === 'compare').length, 1);
  await button('刷新过时比较').click();
  await page.getByText('/metadata/description', { exact: true }).waitFor();
  assert.equal(await page.getByText(/比较内容已过时/).count(), 0);
  for (const kind of kinds) {
    await selectKind(kind);
    await page.getByLabel('比较右侧').selectOption('v0');
    await page.getByText('/fixtureVersion', { exact: true }).waitFor();
  }
  await finish();
}

async function runFourKindComparisons(browser) {
  const harness = await createHarness(browser, { distinctVersions: true });
  const { page, requests, button, selectKind, finish } = harness;
  for (const kind of kinds) {
    await selectKind(kind);
    await button('比较当前草稿').click();
    await page.getByText('没有差异。', { exact: true }).waitFor();
    assert.equal(requests.filter((item) => item.type === 'compare' && item.kind === kind).length, 1);
    await page.getByLabel('比较右侧').selectOption('v0');
    await page.getByText('/fixtureVersion', { exact: true }).waitFor();
  }
  await finish();
}

async function runDeferredAssetSwitch(browser) {
  const compareGate = deferred();
  const harness = await createHarness(browser, { gates: { compare: compareGate } });
  const { page, button, selectKind, finish } = harness;
  void button('比较当前草稿').click();
  await compareGate.started;
  await selectKind('Workflow');
  compareGate.release();
  await page.getByRole('heading', { name: 'WORKFLOW · demo/workflow', exact: true }).waitFor();
  assert.equal(await page.locator('.diff-view').count(), 0);
  assert.equal(await page.getByText(/比较内容已过时/).count(), 0);
  await finish();
}

async function runComparisonErrorSwitch(browser) {
  const harness = await createHarness(browser, { compareErrorOnce: true });
  const { page, button, finish } = harness;
  await button('比较当前草稿').click();
  await page.getByText('COMPARISON_UNAVAILABLE · HTTP 503', { exact: true }).waitFor();
  await page.getByLabel('比较右侧').selectOption('v0');
  await page.getByText('没有差异。', { exact: true }).waitFor();
  assert.equal(await page.getByText('COMPARISON_UNAVAILABLE · HTTP 503', { exact: true }).count(), 0);
  await finish([503]);
}

async function runReferenceHistoryError(browser) {
  const documents = clone(drafts);
  documents.APPLICATION.definition.actionPolicies[0].abilityReleaseRef = 'demo/ability@v1';
  const harness = await createHarness(browser, { historyError: true, documents });
  const { page, selectKind, finish } = harness;
  await selectKind('Application');
  await page.getByText(/版本历史加载失败：HISTORY_UNAVAILABLE/).first().waitFor();
  assert.equal(await page.getByRole('button', { name: '重试', exact: true }).count() > 0, true);
  await finish([503, 503]);
}

async function runDirtyBeforeUnload(browser) {
  const canonical = await createHarness(browser);
  await canonical.page.getByLabel('描述').fill('dirty');
  canonical.page.once('dialog', (dialog) => dialog.dismiss());
  await canonical.page.reload({ waitUntil: 'commit' }).catch(() => {});
  assert.equal(canonical.page.url(), 'http://localhost/');
  await canonical.finish();

  const pending = await createHarness(browser);
  await pending.selectKind('Ability');
  await pending.page.getByLabel('Model argument schema').fill('{pending');
  pending.page.once('dialog', (dialog) => dialog.dismiss());
  await pending.page.reload({ waitUntil: 'commit' }).catch(() => {});
  assert.equal(pending.page.url(), 'http://localhost/');
  await pending.finish();
}

async function runApplicationWorkbench(browser) {
  const harness = await createHarness(browser);
  const { page, requests, button, selectKind, finish } = harness;
  await selectKind('Application');
  const children = page.getByLabel('Children IDs');
  await children.focus();
  await children.pressSequentially('x');
  assert.match(await children.inputValue(), /x$/);
  await selectKind('Skill');
  await selectKind('Application');
  assert.match(await page.getByLabel('Children IDs').inputValue(), /x$/);
  page.once('dialog', (dialog) => dialog.accept());
  await button('丢弃字段编辑').click();
  await page.getByLabel('Children IDs').focus();
  await page.getByLabel('Children IDs').press(process.platform === 'darwin' ? 'Meta+A' : 'Control+A');
  await page.getByLabel('Children IDs').pressSequentially('["prompt","selection","button"]');
  await button('应用 JSON').click();
  await page.getByRole('button', { name: /prompt · Text/ }).click();
  await page.getByLabel('Text binding path').fill('/headline');
  await page.getByLabel('Preview sample JSON').fill(JSON.stringify({ headline: 'Preview changed', options: [{ label: 'One', value: 'one' }], selection: 'one', prompt: 'legacy' }));
  await button('更新本地预览').click();
  await page.getByText('Preview changed', { exact: true }).waitFor();
  await page.getByRole('button', { name: /prompt · Text/ }).click();
  await button('完整 JSON').click();
  const malformedPreview = JSON.parse(await page.getByLabel('结构化草稿 JSON').inputValue());
  malformedPreview.definition.surfaceTemplate.components[1].text = null;
  await page.getByLabel('结构化草稿 JSON').fill(JSON.stringify(malformedPreview));
  await button('表单').click();
  await page.getByText(/INVALID_TEXT_BINDING/).waitFor();
  await page.getByRole('button', { name: /prompt · Text/ }).click();
  assert.equal(await page.getByLabel('Text binding path').isDisabled(), true);
  assert.equal(await page.getByText(/完整 JSON 模式修正/).count() > 0, true);
  assert.equal(await page.getByText('Preview changed', { exact: true }).count(), 0);
  assert.equal(await page.locator('vite-error-overlay').count(), 0);
  await page.getByLabel('Preview sample JSON').fill('');
  await button('更新本地预览').click();
  await page.getByText(/INVALID_SAMPLE_JSON/).waitFor();
  assert.equal(await page.getByLabel('Preview sample JSON').inputValue(), '');
  await button('完整 JSON').click();
  const repairedPreview = JSON.parse(await page.getByLabel('结构化草稿 JSON').inputValue());
  repairedPreview.definition.surfaceTemplate.components[1].text = { path: '/headline' };
  await page.getByLabel('结构化草稿 JSON').fill(JSON.stringify(repairedPreview));
  await button('表单').click();
  await page.getByLabel('Preview sample JSON').fill(JSON.stringify({ headline: 'Preview changed', options: [{ label: 'One', value: 'one' }], selection: 'one', prompt: 'legacy' }));
  await button('更新本地预览').click();
  await page.getByText('Preview changed', { exact: true }).waitFor();
  assert.equal(requests.some((item) => item.type === 'action'), false);
  await page.getByRole('button', { name: 'Confirm', exact: true }).click();
  await page.getByText(/"simulated": true/).waitFor();
  assert.equal(requests.some((item) => item.type === 'action'), false);
  await page.screenshot({ path: path.join(output, 'a2ui-workbench-desktop.png'), fullPage: false });
  await page.getByRole('button', { name: '窄屏', exact: true }).click();
  assert.equal(await page.locator('.a2ui-preview-frame.narrow').count(), 1);
  await page.screenshot({ path: path.join(output, 'a2ui-workbench-narrow.png'), fullPage: false });
  await button('完整 JSON').click();
  const full = page.getByLabel('结构化草稿 JSON');
  const edited = JSON.parse(await full.inputValue());
  assert.equal(edited.definition.surfaceTemplate.components[1].extension, 'keep');
  assert.equal(edited.definition.surfaceTemplate.extension.keep, true);
  edited.definition.surfaceTemplate.components.push({ id: 'prompt', component: 'FutureCard', payload: { keep: true } });
  await full.fill(JSON.stringify(edited));
  await button('表单').click();
  await page.getByText(/组件 ID prompt 重复/).waitFor();
  await page.getByText(/不支持的组件类型 FutureCard/).waitFor();
  await button('完整 JSON').click();
  assert.deepEqual(JSON.parse(await full.inputValue()).definition.surfaceTemplate.components.at(-1).payload, { keep: true });
  await finish();
}

async function runApplicationPreviewIsolation(browser) {
  const documents = clone(drafts);
  const second = clone(drafts.APPLICATION);
  second.definition.asset.applicationKey = 'second/app';
  const harness = await createHarness(browser, { documents });
  const { page, button, selectKind, finish } = harness;
  await selectKind('Application');
  await page.getByLabel('Preview sample JSON').fill('{pending sample');
  await selectKind('Skill');
  await selectKind('Application');
  assert.equal(await page.getByLabel('Preview sample JSON').inputValue(), '{pending sample');
  await button('完整 JSON').click();
  assert.deepEqual(JSON.parse(await page.getByLabel('结构化草稿 JSON').inputValue()), documents.APPLICATION);
  await finish();
}

const browser = await chromium.launch({ headless: true, executablePath: chromePath });
try {
  await runSkillWorkbench(browser);
  await runDeferredResourceIntegrity(browser);
  await runApplicationWorkbench(browser);
  await runApplicationPreviewIsolation(browser);
  await runEditorCoverage(browser);
  await runCreateDraftFlows(browser);
  await runFirstPublishFlows(browser, 'PRT');
  await runFirstPublishFlows(browser, 'ONLINE');
  await runComparisonAndReferenceCoverage(browser);
  await runDeferredComparison(browser);
  await runFourKindComparisons(browser);
  await runDeferredAssetSwitch(browser);
  await runComparisonErrorSwitch(browser);
  await runReferenceHistoryError(browser);
  await runBindingCatalogStaleState(browser);
  await runBindingCatalogFailure(browser);
  await runDirtyBeforeUnload(browser);
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
